import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from app.config import settings
from app.database import VideoStore
from app.embedding import Encoder
from app.models import Moment, SearchHit, SearchResponse
from app.utilities import group_moments, sample_frames


def index_video(encoder: Encoder, store: VideoStore, path: Path, video_id: str, filename: str) -> dict:
    times, frames, duration = sample_frames(path, settings.sample_fps, settings.max_frames)
    if not frames:
        raise ValueError(f"no decodable frames in {filename}")
    vectors = encoder.encode_images(frames)
    store.add_video(video_id, filename, duration, times, vectors)
    store.optimize()
    return {"video_id": video_id, "filename": filename, "duration": duration, "num_frames": len(times)}


def search(
    encoder: Encoder,
    store: VideoStore,
    query: str,
    k: int = 10,
    frame_pool: int = 500,
    min_rel_score: float = 0.5,
) -> SearchResponse:
    start = time.perf_counter()
    q = encoder.encode_texts([query])[0]
    rows = store.search_frames(q, frame_pool)

    by_video: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for r in rows:
        # LanceDB returns cosine distance; convert back to similarity
        by_video[r["video_id"]].append((r["t"], 1.0 - r["_distance"]))

    meta = store.video_meta()
    hits = []
    for vid, pts in by_video.items():
        if vid not in meta:
            continue
        arr = np.array(pts)
        moments = group_moments(arr[:, 0], arr[:, 1])[:3]
        hits.append(
            SearchHit(
                video_id=vid,
                filename=meta[vid]["filename"],
                duration=meta[vid]["duration"],
                score=moments[0]["score"],
                moments=[Moment(**m) for m in moments],
            )
        )
    hits.sort(key=lambda h: h.score, reverse=True)
    # Cosine scores are only meaningful relative to each other, so drop hits far below the best one
    # rather than padding results with unrelated videos.
    if hits and hits[0].score > 0:
        hits = [h for h in hits if h.score >= min_rel_score * hits[0].score]
    return SearchResponse(query=query, took_ms=(time.perf_counter() - start) * 1000, hits=hits[:k])
