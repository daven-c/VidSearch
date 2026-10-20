from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIDSEARCH_", env_file=".env")

    model_name: str = "google/siglip2-base-patch16-256"
    device: str | None = None  # auto: cuda > mps > cpu
    vision_backend: str = "auto"  # auto: coreml on Apple Silicon for SigLIP models, else torch
    coreml_batch_size: int = 16  # ANE throughput is flat from 8-32 and drops at 64 on an M4
    sample_fps: float = 1.0
    max_frames: int = 600
    batch_size: int = 32
    data_dir: Path = BACKEND_DIR / "data"

    @property
    def db_dir(self) -> Path:
        return self.data_dir / "lancedb"

    @property
    def video_dir(self) -> Path:
        return self.data_dir / "videos"


settings = Settings()
