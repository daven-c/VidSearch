import io
from pathlib import Path

import av
import numpy as np
from PIL import Image


def sample_frames(
    path: str | Path, fps: float = 1.0, max_frames: int = 600
) -> tuple[list[float], list[Image.Image], float]:
    """Decode a video and return (timestamps, frames, duration) sampled at roughly `fps`.

    Long videos are thinned so at most `max_frames` frames are kept. Returns at least one frame
    for any decodable video, however short.
    """
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        duration = (
            float(stream.duration * stream.time_base)
            if stream.duration
            else (container.duration / av.time_base if container.duration else 0.0)
        )
        step = 1.0 / fps
        if duration > 0 and duration * fps > max_frames:
            step = duration / max_frames

        times: list[float] = []
        frames: list[Image.Image] = []
        next_t = 0.0
        last = None
        for frame in container.decode(stream):
            if frame.time is None:
                continue
            last = frame
            if frame.time + 1e-6 >= next_t:
                times.append(float(frame.time))
                frames.append(frame.to_image())
                next_t += step
                while next_t <= frame.time:
                    next_t += step
        if not frames and last is not None:
            times.append(float(last.time))
            frames.append(last.to_image())
        duration = max(duration, times[-1] if times else 0.0)
    return times, frames, duration


def thumbnail_jpeg(path: str | Path, t: float, width: int = 320) -> bytes:
    """Encode the first frame at or after `t` seconds (or the last frame) as a small JPEG."""
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        if t > 0 and stream.time_base:
            container.seek(int(t / stream.time_base), stream=stream)  # seeks to the keyframe before t
        frame = None
        for frame in container.decode(stream):
            if frame.time is not None and frame.time + 1e-6 >= t:
                break
        if frame is None:
            raise ValueError("no decodable frames")
        img = frame.to_image()
    img.thumbnail((width, width * 2))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def group_moments(
    times: np.ndarray, scores: np.ndarray, gap: float = 2.5, pad: float = 1.0, rel_threshold: float = 0.75
) -> list[dict]:
    """Merge hit frames whose timestamps are within `gap` seconds into contiguous moments.

    `times` and `scores` describe the matching frames of a single video. Frames scoring below
    `rel_threshold` of the way from the video's worst to best frame are dropped first, so weak
    neighbours don't stretch a moment. Each moment is scored by its best frame. Returned moments
    are sorted best-first.
    """
    if len(times) == 0:
        return []
    lo, hi = scores.min(), scores.max()
    keep = scores >= lo + rel_threshold * (hi - lo)
    times, scores = times[keep], scores[keep]
    order = np.argsort(times)
    times, scores = times[order], scores[order]
    moments = []
    start = 0
    for i in range(1, len(times) + 1):
        if i == len(times) or times[i] - times[i - 1] > gap:
            seg_t, seg_s = times[start:i], scores[start:i]
            best = int(np.argmax(seg_s))
            moments.append(
                {
                    "start": max(0.0, float(seg_t[0]) - pad),
                    "end": float(seg_t[-1]) + pad,
                    "best_t": float(seg_t[best]),
                    "score": float(seg_s[best]),
                }
            )
            start = i
    return sorted(moments, key=lambda m: m["score"], reverse=True)
