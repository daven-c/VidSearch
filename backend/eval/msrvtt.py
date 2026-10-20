"""Zero-shot text-to-video retrieval on MSR-VTT 1k-A (JSFusion test split).

    uv run python -m eval.msrvtt                      # full 1000-video eval
    uv run python -m eval.msrvtt --limit 100          # quick smoke run
    uv run python -m eval.msrvtt --model google/siglip2-so400m-patch16-256

Videos and annotations are pulled from the public `friedrichor/MSR-VTT` HF dataset. Frame
embeddings are cached per (model, fps), so re-runs only re-score. Results are written to
eval/results/ as JSON together with the environment they were produced on.
"""

import argparse
import json
import platform
import subprocess
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import torch
import transformers
from huggingface_hub import hf_hub_download
from tqdm import tqdm

from app.config import settings
from app.embedding import Encoder
from app.utilities import sample_frames
from eval.metrics import retrieval_metrics

REPO = "friedrichor/MSR-VTT"
EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_DIR / "results"


def load_split(limit: int | None) -> list[dict]:
    ann = json.loads(Path(hf_hub_download(REPO, "msrvtt_test_1k.json", repo_type="dataset")).read_text())
    return ann[:limit] if limit else ann


def ensure_videos(items: list[dict], out_dir: Path) -> None:
    missing = [it for it in items if not (out_dir / it["video"]).exists()]
    if not missing:
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    zpath = hf_hub_download(REPO, "MSRVTT_Videos.zip", repo_type="dataset")
    with zipfile.ZipFile(zpath) as z:
        for it in tqdm(missing, desc="extract"):
            (out_dir / it["video"]).write_bytes(z.read(f"video/{it['video']}"))


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "describe", "--always", "--dirty"], text=True).strip()
    except Exception:
        return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=settings.model_name)
    ap.add_argument("--fps", type=float, default=settings.sample_fps)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--device", default=None)
    ap.add_argument("--backend", default=settings.vision_backend, choices=["auto", "torch", "coreml"])
    args = ap.parse_args()

    items = load_split(args.limit)
    video_dir = settings.data_dir / "msrvtt" / "videos"
    ensure_videos(items, video_dir)

    encoder = Encoder(args.model, args.device, args.backend)
    # torch results keep the original filenames; other backends are tagged so they sit side by side
    tag = "" if encoder.vision_backend == "torch" else f"_{encoder.vision_backend}"
    slug = args.model.replace("/", "__")
    cache_dir = settings.data_dir / "msrvtt" / "cache" / f"{slug}_fps{args.fps}{tag}"
    cache_dir.mkdir(parents=True, exist_ok=True)

    frame_embs: list[np.ndarray] = []
    n_frames = decode_s = encode_s = 0.0
    for it in tqdm(items, desc="embed"):
        cached = cache_dir / f"{it['video_id']}.npy"
        if cached.exists():
            emb = np.load(cached)
        else:
            t0 = time.perf_counter()
            _, frames, _ = sample_frames(video_dir / it["video"], args.fps, settings.max_frames)
            t1 = time.perf_counter()
            emb = encoder.encode_images(frames)
            t2 = time.perf_counter()
            decode_s += t1 - t0
            encode_s += t2 - t1
            n_frames += len(frames)
            np.save(cached, emb)
        frame_embs.append(emb)

    t0 = time.perf_counter()
    text = encoder.encode_texts([it["caption"] for it in items])
    text_s = time.perf_counter() - t0

    # Two pooling strategies over frames: mean-pooled video embedding (what the index stores in
    # the `videos` table) and max over frames (what moment search effectively ranks by).
    mean_pool = np.stack([e.mean(0) / np.linalg.norm(e.mean(0)) for e in frame_embs])
    sim_mean = text @ mean_pool.T
    sim_max = np.stack([(text @ e.T).max(1) for e in frame_embs], axis=1)

    results = {
        "benchmark": "MSR-VTT 1k-A text-to-video (zero-shot)",
        "model": args.model,
        "fps": args.fps,
        "vision_backend": encoder.vision_backend,
        "num_queries": len(items),
        "metrics": {
            "t2v_mean_pool": retrieval_metrics(sim_mean),
            "t2v_max_frame": retrieval_metrics(sim_max),
            "v2t_mean_pool": retrieval_metrics(sim_mean.T),
        },
        "throughput": {
            "frames_encoded_this_run": int(n_frames),
            "decode_fps": n_frames / decode_s if decode_s else None,
            "encode_fps": n_frames / encode_s if encode_s else None,
            "text_queries_per_s": len(items) / text_s,
        },
        "env": {
            "device": encoder.device,
            "platform": platform.platform(),
            "processor": platform.processor(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "git_commit": git_commit(),
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        },
    }

    RESULTS_DIR.mkdir(exist_ok=True)
    suffix = f"_n{args.limit}" if args.limit else ""
    out = RESULTS_DIR / f"msrvtt1k_{slug}_fps{args.fps}{tag}{suffix}.json"
    out.write_text(json.dumps(results, indent=2) + "\n")

    print(f"\n{args.model}  fps={args.fps}  n={len(items)}  vision={encoder.vision_backend}")
    print(f"{'protocol':<16}{'R@1':>7}{'R@5':>7}{'R@10':>7}{'MdR':>6}{'MnR':>8}")
    for name, m in results["metrics"].items():
        print(f"{name:<16}{m['R@1']:>7.1f}{m['R@5']:>7.1f}{m['R@10']:>7.1f}{m['MdR']:>6.0f}{m['MnR']:>8.1f}")
    print(f"-> {out.relative_to(EVAL_DIR.parent)}")


if __name__ == "__main__":
    main()
