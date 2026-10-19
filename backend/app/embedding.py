from functools import lru_cache

import numpy as np
import torch
from PIL import Image
from transformers import AutoModel, AutoProcessor

from app.config import settings


def pick_device(requested: str | None = None) -> str:
    if requested:
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _pooled(out) -> torch.Tensor:
    # transformers>=5 returns a ModelOutput from get_*_features; older versions return a tensor
    return out if isinstance(out, torch.Tensor) else out.pooler_output


class Encoder:
    """SigLIP 2 dual encoder producing L2-normalised image and text embeddings in a shared space."""

    def __init__(self, model_name: str = settings.model_name, device: str | None = settings.device):
        self.model_name = model_name
        self.device = pick_device(device)
        # bf16 is fastest on Apple GPUs; fp16 for CUDA so pre-Ampere cards (no fast bf16) still work
        self.dtype = {"cpu": torch.float32, "mps": torch.bfloat16}.get(self.device, torch.float16)
        self.model = AutoModel.from_pretrained(model_name, dtype=self.dtype).to(self.device).eval()
        self.processor = AutoProcessor.from_pretrained(model_name)
        self.dim = int(self.encode_texts(["probe"]).shape[1])

    @torch.inference_mode()
    def encode_images(self, images: list[Image.Image], batch_size: int = settings.batch_size) -> np.ndarray:
        chunks = []
        for i in range(0, len(images), batch_size):
            inputs = self.processor(images=images[i : i + batch_size], return_tensors="pt")
            inputs = {"pixel_values": inputs["pixel_values"].to(self.device, self.dtype)}
            feats = _pooled(self.model.get_image_features(**inputs))
            chunks.append(torch.nn.functional.normalize(feats.float(), dim=-1).cpu().numpy())
        return np.concatenate(chunks) if chunks else np.zeros((0, self.dim), dtype=np.float32)

    @torch.inference_mode()
    def encode_texts(self, texts: list[str], batch_size: int = 256) -> np.ndarray:
        chunks = []
        for i in range(0, len(texts), batch_size):
            # SigLIP 2 was trained on lowercased text padded to 64 tokens
            batch = [t.lower() for t in texts[i : i + batch_size]]
            inputs = self.processor(
                text=batch, padding="max_length", max_length=64, truncation=True, return_tensors="pt"
            ).to(self.device)
            feats = _pooled(self.model.get_text_features(**inputs))
            chunks.append(torch.nn.functional.normalize(feats.float(), dim=-1).cpu().numpy())
        return np.concatenate(chunks)


@lru_cache(maxsize=1)
def get_encoder() -> Encoder:
    return Encoder()
