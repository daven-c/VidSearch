import numpy as np


def retrieval_metrics(sim: np.ndarray) -> dict[str, float]:
    """Standard retrieval metrics for a square query x candidate similarity matrix whose
    ground truth is the diagonal (query i matches candidate i).

    Ties are broken pessimistically: a candidate scoring equal to the ground truth counts as
    ranked above it, so a degenerate constant model cannot score well.
    """
    assert sim.shape[0] == sim.shape[1], "expects one ground-truth candidate per query"
    gt = np.diag(sim)[:, None]
    ranks = (sim >= gt).sum(axis=1)  # 1-based rank of the ground truth
    return {
        "R@1": float(np.mean(ranks <= 1) * 100),
        "R@5": float(np.mean(ranks <= 5) * 100),
        "R@10": float(np.mean(ranks <= 10) * 100),
        "MdR": float(np.median(ranks)),
        "MnR": float(np.mean(ranks)),
    }
