from datetime import timedelta
from functools import lru_cache
from pathlib import Path

import lancedb
import numpy as np
import pyarrow as pa

from app.config import settings


class VideoStore:
    """Embedded LanceDB store: one row per sampled frame, plus one mean-pooled row per video."""

    def __init__(self, db_dir: Path, dim: int):
        db_dir.mkdir(parents=True, exist_ok=True)
        # Re-check for other processes' writes (e.g. a bulk ingest while the API is serving)
        self.db = lancedb.connect(str(db_dir), read_consistency_interval=timedelta(seconds=2))
        self.dim = dim
        self._meta: tuple[int, dict[str, dict]] | None = None
        vec = pa.list_(pa.float32(), dim)
        self.frames = self._table(
            "frames", pa.schema([("video_id", pa.string()), ("t", pa.float32()), ("vector", vec)])
        )
        self.videos = self._table(
            "videos",
            pa.schema(
                [
                    ("video_id", pa.string()),
                    ("filename", pa.string()),
                    ("duration", pa.float32()),
                    ("num_frames", pa.int32()),
                    ("vector", vec),
                ]
            ),
        )

    def _table(self, name: str, schema: pa.Schema):
        return self.db.create_table(name, schema=schema, exist_ok=True)

    def add_video(
        self, video_id: str, filename: str, duration: float, times: list[float], vectors: np.ndarray
    ):
        self.add_videos([(video_id, filename, duration, times, vectors)])

    def add_videos(self, items: list[tuple[str, str, float, list[float], np.ndarray]]):
        """Bulk insert as one Arrow write per table: far fewer fragments than per-video adds."""
        if not items:
            return
        existing = self.video_meta()
        for video_id, *_ in items:
            if video_id in existing:
                self.delete_video(video_id)

        frame_vecs = np.concatenate([v for *_, v in items]).astype(np.float32)
        if len(frame_vecs) != sum(len(t) for _, _, _, t, _ in items):
            raise ValueError("each video needs exactly one vector per timestamp")
        pooled = np.stack([v.mean(axis=0) for *_, v in items])
        pooled /= np.linalg.norm(pooled, axis=1, keepdims=True) + 1e-12

        self.frames.add(
            pa.table(
                {
                    "video_id": [vid for vid, _, _, t, _ in items for _ in t],
                    "t": pa.array([x for _, _, _, t, _ in items for x in t], pa.float32()),
                    "vector": pa.FixedSizeListArray.from_arrays(frame_vecs.ravel(), self.dim),
                },
                schema=self.frames.schema,
            )
        )
        self.videos.add(
            pa.table(
                {
                    "video_id": [vid for vid, *_ in items],
                    "filename": [fn for _, fn, *_ in items],
                    "duration": pa.array([d for _, _, d, _, _ in items], pa.float32()),
                    "num_frames": pa.array([len(t) for _, _, _, t, _ in items], pa.int32()),
                    "vector": pa.FixedSizeListArray.from_arrays(pooled.astype(np.float32).ravel(), self.dim),
                },
                schema=self.videos.schema,
            )
        )

    def delete_video(self, video_id: str):
        cond = f"video_id = '{video_id.replace(chr(39), chr(39) * 2)}'"
        self.frames.delete(cond)
        self.videos.delete(cond)

    def optimize(self):
        """Compact the small fragments each add() creates; search slows down noticeably without it."""
        self.frames.optimize()
        self.videos.optimize()

    def video_meta(self) -> dict[str, dict]:
        # Cached because search needs it on every query. Keyed on the table version, so writes from
        # this process or any other (picked up via read_consistency_interval) invalidate it.
        version = self.videos.version
        if self._meta is None or self._meta[0] != version:
            rows = self.videos.to_arrow().drop_columns(["vector"]).to_pylist()
            self._meta = (version, {r["video_id"]: r for r in rows})
        return self._meta[1]

    def list_videos(self) -> list[dict]:
        return list(self.video_meta().values())

    def search_frames(self, query: np.ndarray, limit: int) -> list[dict]:
        return (
            self.frames.search(query.astype(np.float32))
            .metric("cosine")
            .select(["video_id", "t", "_distance"])
            .limit(limit)
            .to_list()
        )


@lru_cache(maxsize=1)
def get_store() -> VideoStore:
    from app.embedding import get_encoder

    return VideoStore(settings.db_dir, get_encoder().dim)
