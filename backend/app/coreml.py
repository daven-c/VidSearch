"""Core ML export of the SigLIP / SigLIP 2 vision tower so it can run on the Apple Neural Engine.

The ANE is ~4x faster than PyTorch's MPS backend for this model on an M4, but only if the graph
converts faithfully. SigLIP's attention-pooling head is an `nn.MultiheadAttention` with a learned
probe query, which coremltools mistranslates (cosine to the reference drops to ~0.45). The wrapper
below re-expresses that head with explicit linear/matmul/softmax ops using the same weights, which
converts correctly (mean cosine to fp32 PyTorch ~0.999).
"""

import hashlib
from pathlib import Path

import numpy as np
import torch

from app.config import settings


class _VisionEmbedder(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.vm = model.vision_model
        self.num_heads = self.vm.head.attention.num_heads

    def forward(self, pixel_values):
        vm, head = self.vm, self.vm.head
        enc = vm.encoder(vm.embeddings(pixel_values))
        h = vm.post_layernorm(enc[0] if isinstance(enc, tuple) else enc.last_hidden_state)

        attn = head.attention
        b, n, d = h.shape
        dh = d // self.num_heads
        wq, wk, wv = attn.in_proj_weight.chunk(3)
        bq, bk, bv = attn.in_proj_bias.chunk(3)
        q = torch.nn.functional.linear(head.probe, wq, bq).reshape(1, 1, self.num_heads, dh).transpose(1, 2)
        k = torch.nn.functional.linear(h, wk, bk).reshape(b, n, self.num_heads, dh).transpose(1, 2)
        v = torch.nn.functional.linear(h, wv, bv).reshape(b, n, self.num_heads, dh).transpose(1, 2)
        weights = torch.softmax(torch.matmul(q, k.transpose(-1, -2)) * dh**-0.5, dim=-1)
        pooled = attn.out_proj(torch.matmul(weights, v).transpose(1, 2).reshape(b, 1, d))
        pooled = pooled + head.mlp(head.layernorm(pooled))
        f = pooled[:, 0]
        return f / f.norm(dim=-1, keepdim=True)


def export(model_name: str, batch_size: int, image_size: int, out: Path) -> Path:
    import coremltools as ct
    from transformers import AutoModel

    model = AutoModel.from_pretrained(model_name, dtype=torch.float32, attn_implementation="eager").eval()
    wrapper = _VisionEmbedder(model).eval()
    example = torch.zeros(batch_size, 3, image_size, image_size)
    with torch.no_grad():
        program = torch.export.export(wrapper, (example,)).run_decompositions({})
    mlmodel = ct.convert(
        program,
        outputs=[ct.TensorType(name="embedding")],
        compute_precision=ct.precision.FLOAT16,
        minimum_deployment_target=ct.target.macOS15,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    mlmodel.save(str(out))
    return out


class CoreMLVision:
    """Fixed-batch Core ML vision encoder. Pads the last partial batch."""

    def __init__(self, model_name: str, batch_size: int, image_size: int, compute_units: str = "CPU_AND_NE"):
        import coremltools as ct

        key = hashlib.sha1(f"{model_name}-{batch_size}-{image_size}".encode()).hexdigest()[:10]
        path = settings.data_dir / "coreml" / f"{model_name.replace('/', '__')}_b{batch_size}_{key}.mlpackage"
        if not path.exists():
            export(model_name, batch_size, image_size, path)
        self.model = ct.models.MLModel(str(path), compute_units=getattr(ct.ComputeUnit, compute_units))
        self.input_name = self.model.get_spec().description.input[0].name
        self.batch_size = batch_size

    def __call__(self, pixel_values: np.ndarray) -> np.ndarray:
        n = len(pixel_values)
        out = []
        for i in range(0, n, self.batch_size):
            chunk = pixel_values[i : i + self.batch_size]
            pad = self.batch_size - len(chunk)
            if pad:
                chunk = np.concatenate([chunk, np.zeros((pad, *chunk.shape[1:]), chunk.dtype)])
            emb = self.model.predict({self.input_name: chunk.astype(np.float32)})["embedding"]
            out.append(emb[: self.batch_size - pad])
        return np.concatenate(out) if out else np.zeros((0, 0), np.float32)
