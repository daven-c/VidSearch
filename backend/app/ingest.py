"""Bulk-index videos into the VidSearch library.

    uv run python -m app.ingest folder ~/Movies/clips       # every video under a folder (symlinked)
    uv run python -m app.ingest msrvtt                      # all 10k MSR-VTT clips from the HF dataset
    uv run python -m app.ingest msrvtt --limit 500

Throughput comes from overlapping work rather than doing it per video: worker threads decode and
preprocess videos while the main thread keeps the vision encoder busy with batches drawn across
videos, and rows are written to LanceDB in bulk and compacted once at the end. Already-indexed
videos are skipped, so an interrupted run resumes where it stopped.
"""

import argparse
import re
import time
import zipfile
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from tqdm import tqdm

from app.config import settings
from app.database import VideoStore
from app.embedding import Encoder
from app.utilities import sample_frames

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


@dataclass
class Source:
    video_id: str
    filename: str
    path: Path


@dataclass
class Decoded:
    source: Source
    times: list[float]
    pixels: np.ndarray
    duration: float


def safe_id(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-")[:80]


def folder_sources(root: Path) -> list[Source]:
    """Symlink each video into the library so the API can stream it without copying."""
    settings.video_dir.mkdir(parents=True, exist_ok=True)
    sources = []
    for p in sorted(root.expanduser().rglob("*")):
        if p.suffix.lower() not in VIDEO_EXT or not p.is_file():
            continue
        vid = safe_id(f"{root.name}-{p.relative_to(root).with_suffix('')}")
        link = settings.video_dir / f"{vid}{p.suffix.lower()}"
        if not link.exists():
            link.symlink_to(p.resolve())
        sources.append(Source(vid, p.name, link))
    return sources


def msrvtt_sources(limit: int | None) -> list[Source]:
    """Extract MSR-VTT clips from the public HF zip into the library (once)."""
    from huggingface_hub import hf_hub_download

    settings.video_dir.mkdir(parents=True, exist_ok=True)
    zpath = hf_hub_download("friedrichor/MSR-VTT", "MSRVTT_Videos.zip", repo_type="dataset")
    sources = []
    with zipfile.ZipFile(zpath) as z:
        names = sorted(n for n in z.namelist() if n.endswith(".mp4"))[:limit]
        for name in tqdm(names, desc="extract", leave=False):
            stem = Path(name).stem
            dest = settings.video_dir / f"msrvtt-{stem}.mp4"
            if not dest.exists():
                dest.write_bytes(z.read(name))
            sources.append(Source(f"msrvtt-{stem}", f"{stem}.mp4", dest))
    return sources


def decode(encoder: Encoder, src: Source) -> Decoded | None:
    try:
        times, frames, duration = sample_frames(src.path, settings.sample_fps, settings.max_frames)
        if not frames:
            return None
        return Decoded(src, times, encoder.preprocess(frames), duration)
    except Exception as e:  # corrupt or unsupported files shouldn't stop a 10k-video run
        tqdm.write(f"skip {src.filename}: {e}")
        return None


def decoded_stream(encoder: Encoder, sources: list[Source], workers: int) -> Iterator[Decoded | None]:
    """Decode ahead of the encoder, keeping a bounded number of videos in flight to cap memory."""
    with ThreadPoolExecutor(workers) as pool:
        in_flight = []
        for src in sources:
            in_flight.append(pool.submit(decode, encoder, src))
            if len(in_flight) >= workers * 4:
                yield in_flight.pop(0).result()
        for fut in in_flight:
            yield fut.result()


def ingest(sources: list[Source], encoder: Encoder, store: VideoStore, workers: int, flush_every: int):
    done = set(store.video_meta())
    todo = [s for s in sources if s.video_id not in done]
    print(f"{len(sources)} videos found, {len(sources) - len(todo)} already indexed, {len(todo)} to index")
    if not todo:
        return

    batch_frames = settings.coreml_batch_size * 8
    pending: list[Decoded] = []  # decoded, waiting to be embedded together
    ready: list[tuple] = []  # embedded, waiting to be written
    n_frames = 0
    start = time.perf_counter()

    def embed_pending():
        nonlocal n_frames
        if not pending:
            return
        emb = encoder.embed_pixels(np.concatenate([d.pixels for d in pending]))
        offset = 0
        for d in pending:
            n = len(d.times)
            ready.append(
                (d.source.video_id, d.source.filename, d.duration, d.times, emb[offset : offset + n])
            )
            offset += n
        n_frames += offset
        pending.clear()

    bar = tqdm(total=len(todo), desc="index", unit="video")
    for d in decoded_stream(encoder, todo, workers):
        bar.update(1)
        if d is None:
            continue
        pending.append(d)
        if sum(len(x.times) for x in pending) >= batch_frames:
            embed_pending()
            bar.set_postfix(fps=f"{n_frames / (time.perf_counter() - start):.0f}")
        if len(ready) >= flush_every:
            store.add_videos(ready)
            ready.clear()
    embed_pending()
    store.add_videos(ready)
    bar.close()

    store.optimize()
    elapsed = time.perf_counter() - start
    rate = n_frames / elapsed
    print(f"indexed {len(todo)} videos / {n_frames} frames in {elapsed:.0f}s ({rate:.1f} frames/s)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", choices=["folder", "msrvtt"])
    ap.add_argument("path", nargs="?", help="folder to index (for `folder`)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=4, help="decode/preprocess threads")
    ap.add_argument("--flush-every", type=int, default=250, help="videos per LanceDB write")
    args = ap.parse_args()

    if args.source == "folder":
        if not args.path:
            ap.error("folder source needs a path")
        sources = folder_sources(Path(args.path))[: args.limit]
    else:
        sources = msrvtt_sources(args.limit)

    encoder = Encoder()
    print(f"vision backend: {encoder.vision_backend}  ·  library: {settings.data_dir}")
    store = VideoStore(settings.db_dir, encoder.dim)
    ingest(sources, encoder, store, args.workers, args.flush_every)


if __name__ == "__main__":
    main()
