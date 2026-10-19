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
        self.db = lancedb.connect(str(db_dir))
        self.dim = dim
        self._meta: dict[str, dict] | None = None
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
        self.delete_video(video_id)
        self.frames.add(
            [
                {"video_id": video_id, "t": t, "vector": v}
                for t, v in zip(times, vectors.astype(np.float32), strict=True)
            ]
        )
        pooled = vectors.mean(axis=0)
        pooled /= np.linalg.norm(pooled) + 1e-12
        self.videos.add(
            [
                {
                    "video_id": video_id,
                    "filename": filename,
                    "duration": duration,
                    "num_frames": len(times),
                    "vector": pooled.astype(np.float32),
                }
            ]
        )

        self._meta = None

    def delete_video(self, video_id: str):
        cond = f"video_id = '{video_id.replace(chr(39), chr(39) * 2)}'"
        self.frames.delete(cond)
        self.videos.delete(cond)
        self._meta = None

    def optimize(self):
        """Compact the small fragments each add() creates; search slows down noticeably without it."""
        self.frames.optimize()
        self.videos.optimize()

    def video_meta(self) -> dict[str, dict]:
        # Cached because search needs it on every query; invalidated by add/delete
        if self._meta is None:
            rows = self.videos.to_arrow().drop_columns(["vector"]).to_pylist()
            self._meta = {r["video_id"]: r for r in rows}
        return self._meta

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
