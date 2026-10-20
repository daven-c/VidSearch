import sys
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


def pick_vision_backend(requested: str, model_name: str) -> str:
    if requested != "auto":
        return requested
    # The Core ML export targets SigLIP's attention-pooling head; CLIP etc. stay on PyTorch
    if sys.platform == "darwin" and "siglip" in model_name.lower():
        try:
            import coremltools  # noqa: F401

            return "coreml"
        except ImportError:
            pass
    return "torch"


class Encoder:
    """SigLIP 2 dual encoder producing L2-normalised image and text embeddings in a shared space.

    Text always runs in PyTorch. Images run either in PyTorch or, on Apple Silicon, as a Core ML
    model on the Neural Engine (~4x faster than MPS; see app/coreml.py).
    """

    def __init__(
        self,
        model_name: str = settings.model_name,
        device: str | None = settings.device,
        vision_backend: str = settings.vision_backend,
    ):
        self.model_name = model_name
        self.device = pick_device(device)
        # bf16 is fastest on Apple GPUs; fp16 for CUDA so pre-Ampere cards (no fast bf16) still work
        self.dtype = {"cpu": torch.float32, "mps": torch.bfloat16}.get(self.device, torch.float16)
        self.model = AutoModel.from_pretrained(model_name, dtype=self.dtype).to(self.device).eval()
        self.processor = AutoProcessor.from_pretrained(model_name)
        self.vision_backend = pick_vision_backend(vision_backend, model_name)
        self._coreml = None
        if self.vision_backend == "coreml":
            from app.coreml import CoreMLVision

            size = self.processor.image_processor.size
            self._coreml = CoreMLVision(model_name, settings.coreml_batch_size, size["height"])
        self.dim = int(self.encode_texts(["probe"]).shape[1])

    def preprocess(self, images: list[Image.Image]) -> np.ndarray:
        """Resize + normalise frames. Thread-safe and model-free, so it can run in worker threads."""
        return self.processor(images=images, return_tensors="np")["pixel_values"]

    @torch.inference_mode()
    def embed_pixels(self, pixels: np.ndarray, batch_size: int = settings.batch_size) -> np.ndarray:
        if len(pixels) == 0:
            return np.zeros((0, self.dim), dtype=np.float32)
        if self._coreml is not None:
            return self._coreml(pixels)
        chunks = []
        for i in range(0, len(pixels), batch_size):
            x = torch.from_numpy(pixels[i : i + batch_size]).to(self.device, self.dtype)
            feats = _pooled(self.model.get_image_features(pixel_values=x))
            chunks.append(torch.nn.functional.normalize(feats.float(), dim=-1).cpu().numpy())
        return np.concatenate(chunks)

    def encode_images(self, images: list[Image.Image]) -> np.ndarray:
        if not images:
            return np.zeros((0, self.dim), dtype=np.float32)
        return self.embed_pixels(self.preprocess(images))

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
