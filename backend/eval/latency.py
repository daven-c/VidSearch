"""Query latency of the production search path over the MSR-VTT 1k-A index.

    uv run python -m eval.latency          # run after eval.msrvtt has cached frame embeddings

Builds a fresh LanceDB index from the cached frame embeddings, then times the same `search()`
the API serves, broken down into text encoding and vector search. Results go to eval/results/.
"""

import argparse
import json
import platform
import tempfile
import time
from pathlib import Path

import numpy as np

from app.config import settings
from app.database import VideoStore
from app.embedding import Encoder
from app.search import search
from eval.msrvtt import RESULTS_DIR, load_split


def pct(xs: list[float]) -> dict[str, float]:
    a = np.array(xs)
    return {"p50": float(np.percentile(a, 50)), "p95": float(np.percentile(a, 95)), "mean": float(a.mean())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=settings.model_name)
    ap.add_argument("--fps", type=float, default=settings.sample_fps)
    ap.add_argument("--queries", type=int, default=200)
    args = ap.parse_args()

    slug = args.model.replace("/", "__")
    cache_dir = settings.data_dir / "msrvtt" / "cache" / f"{slug}_fps{args.fps}"
    items = [it for it in load_split(None) if (cache_dir / f"{it['video_id']}.npy").exists()]
    if not items:
        raise SystemExit(f"no cached embeddings in {cache_dir}; run eval.msrvtt first")

    encoder = Encoder(args.model)
    with tempfile.TemporaryDirectory() as tmp:
        store = VideoStore(Path(tmp), encoder.dim)
        t0 = time.perf_counter()
        n_frames = 0
        for it in items:
            emb = np.load(cache_dir / f"{it['video_id']}.npy")
            n_frames += len(emb)
            store.add_video(
                it["video_id"], it["video"], float(len(emb)), list(map(float, range(len(emb)))), emb
            )
        store.optimize()
        build_s = time.perf_counter() - t0

        queries = [it["caption"] for it in items[: args.queries]]
        for q in queries[:10]:  # warm up kernels and caches
            search(encoder, store, q)

        enc_ms, vec_ms, e2e_ms = [], [], []
        for q in queries:
            t0 = time.perf_counter()
            qv = encoder.encode_texts([q])[0]
            t1 = time.perf_counter()
            store.search_frames(qv, 500)
            t2 = time.perf_counter()
            search(encoder, store, q)
            t3 = time.perf_counter()
            enc_ms.append((t1 - t0) * 1000)
            vec_ms.append((t2 - t1) * 1000)
            e2e_ms.append((t3 - t2) * 1000)

    results = {
        "benchmark": "search latency, MSR-VTT 1k-A index (exact cosine, no ANN index)",
        "model": args.model,
        "videos": len(items),
        "frames": n_frames,
        "queries": len(queries),
        "index_build_s": build_s,
        "latency_ms": {"text_encode": pct(enc_ms), "vector_search": pct(vec_ms), "end_to_end": pct(e2e_ms)},
        "env": {"device": encoder.device, "platform": platform.platform()},
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"latency_{slug}.json"
    out.write_text(json.dumps(results, indent=2) + "\n")

    print(f"\n{len(items)} videos / {n_frames} frames on {encoder.device}")
    for k, v in results["latency_ms"].items():
        print(f"{k:<14} p50 {v['p50']:7.1f} ms   p95 {v['p95']:7.1f} ms")
    print(f"-> {out.name}")


if __name__ == "__main__":
    main()
