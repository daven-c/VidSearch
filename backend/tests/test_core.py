import io
import time

import av
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.main as main
from app.database import VideoStore
from app.search import search
from app.utilities import group_moments, sample_frames
from eval.metrics import retrieval_metrics

COLORS = {"red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255)}


class FakeEncoder:
    """Embeds frames by mean colour and maps colour words to the same axes."""

    dim = 3
    vision_backend = "fake"

    def preprocess(self, images):
        return np.array([np.asarray(im, dtype=np.float32).mean((0, 1)) for im in images])

    def embed_pixels(self, pixels):
        v = pixels + 1e-3
        return v / np.linalg.norm(v, axis=1, keepdims=True)

    def encode_images(self, images):
        return self.embed_pixels(self.preprocess(images))

    def encode_texts(self, texts):
        v = np.array([COLORS[t] for t in texts], dtype=np.float32) + 1e-3
        return v / np.linalg.norm(v, axis=1, keepdims=True)


def make_video(path, segments, fps=10):
    """Write an mp4 made of solid-colour segments: [(colour, seconds), ...]."""
    with av.open(str(path), "w") as out:
        stream = out.add_stream("mpeg4", rate=fps)
        stream.width, stream.height, stream.pix_fmt = 64, 64, "yuv420p"
        for color, secs in segments:
            img = np.zeros((64, 64, 3), np.uint8)
            img[:] = COLORS[color]
            for _ in range(int(secs * fps)):
                out.mux(stream.encode(av.VideoFrame.from_ndarray(img, format="rgb24")))
        out.mux(stream.encode())


def test_retrieval_metrics_perfect_and_ties():
    m = retrieval_metrics(np.eye(4))
    assert m["R@1"] == 100 and m["MdR"] == 1
    # a constant model must not get credit from ties
    assert retrieval_metrics(np.ones((4, 4)))["R@1"] == 0


def test_group_moments_merges_adjacent_hits():
    t = np.array([10.0, 1.0, 2.0, 3.0, 11.0])
    s = np.array([0.9, 0.2, 0.5, 0.3, 0.4])
    moments = group_moments(t, s, gap=2.5, pad=0, rel_threshold=0)
    assert [(m["start"], m["end"], m["best_t"]) for m in moments] == [(10, 11, 10), (1, 3, 2)]
    # with the default threshold only frames near the best score survive
    assert [(m["start"], m["end"]) for m in group_moments(t, s, pad=0)] == [(10, 10)]


def test_sample_frames_rate(tmp_path):
    p = tmp_path / "v.mp4"
    make_video(p, [("red", 5)])
    times, frames, duration = sample_frames(p, fps=1.0)
    assert len(frames) == 5 and times[0] == 0 and duration == pytest.approx(5, abs=0.2)


def test_bulk_ingest_batches_across_videos_and_resumes(tmp_path, monkeypatch):
    from app import ingest

    monkeypatch.setattr(ingest.settings, "data_dir", tmp_path / "lib")
    clips = tmp_path / "clips"
    clips.mkdir()
    for name, color in [("a", "red"), ("b", "green"), ("c", "blue")]:
        make_video(clips / f"{name}.mp4", [(color, 3)])
    (clips / "notes.txt").write_text("not a video")

    enc = FakeEncoder()
    store = VideoStore(tmp_path / "db", enc.dim)
    sources = ingest.folder_sources(clips)
    assert len(sources) == 3
    ingest.ingest(sources, enc, store, workers=2, flush_every=2)

    meta = store.video_meta()
    assert sorted(m["filename"] for m in meta.values()) == ["a.mp4", "b.mp4", "c.mp4"]
    # frames embedded in one cross-video batch must still land on the right video
    hit = search(enc, store, "green").hits[0]
    assert hit.filename == "b.mp4" and len(hit.moments) == 1

    n_rows = store.frames.count_rows()
    ingest.ingest(ingest.folder_sources(clips), enc, store, workers=2, flush_every=2)
    assert store.frames.count_rows() == n_rows  # second run skips everything


def test_store_sees_writes_from_another_process(tmp_path):
    # e.g. the API server's store while a bulk ingest writes to the same library
    server, ingester = VideoStore(tmp_path, 3), VideoStore(tmp_path, 3)
    assert server.video_meta() == {}
    ingester.add_video("v1", "v1.mp4", 2.0, [0.0, 1.0], np.eye(3, dtype=np.float32)[:2])
    time.sleep(2.1)  # read_consistency_interval
    assert list(server.video_meta()) == ["v1"]
    assert {r["video_id"] for r in server.search_frames(np.array([1, 0, 0], np.float32), 5)} == {"v1"}


def test_upload_and_search_finds_the_right_moment(tmp_path, monkeypatch):
    enc = FakeEncoder()
    store = VideoStore(tmp_path / "db", enc.dim)
    monkeypatch.setattr(main, "get_encoder", lambda: enc)
    monkeypatch.setattr(main, "get_store", lambda: store)
    monkeypatch.setattr(main.settings, "data_dir", tmp_path)
    client = TestClient(main.app)

    clip = tmp_path / "clip.mp4"
    make_video(clip, [("red", 4), ("blue", 4), ("red", 2)])
    with clip.open("rb") as f:
        info = client.post("/videos", files={"file": ("clip.mp4", f, "video/mp4")}).json()
    assert info["num_frames"] == 10

    res = client.get("/search", params={"q": "blue"}).json()
    hit = res["hits"][0]
    assert hit["video_id"] == info["video_id"]
    best = hit["moments"][0]
    assert 4 <= best["best_t"] < 8 and best["start"] >= 2.5 and best["end"] <= 9.5

    assert client.get(f"/videos/{info['video_id']}/file").status_code == 200
    thumb = client.get(f"/videos/{info['video_id']}/thumbnail", params={"t": 5})
    assert thumb.headers["content-type"] == "image/jpeg"
    r, g, b = Image.open(io.BytesIO(thumb.content)).convert("RGB").getpixel((32, 32))
    assert b > 200 and r < 60  # the frame at t=5 is in the blue segment
    assert client.delete(f"/videos/{info['video_id']}").status_code == 200
    assert client.get("/videos").json() == []
