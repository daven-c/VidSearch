import json
import re
import shutil
import uuid

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import BACKEND_DIR, settings
from app.database import get_store
from app.embedding import get_encoder
from app.models import SearchResponse, VideoInfo
from app.search import index_video, search

app = FastAPI(title="VidSearch")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ALLOWED_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


@app.get("/health")
def health():
    return {"status": "ok", "model": settings.model_name}


@app.get("/videos", response_model=list[VideoInfo])
def list_videos():
    return get_store().list_videos()


@app.post("/videos", response_model=VideoInfo)
async def upload_video(file: UploadFile = File(...)):
    name = file.filename or "video.mp4"
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"unsupported file type {ext!r}")
    video_id = uuid.uuid4().hex[:12]
    settings.video_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.video_dir / f"{video_id}{ext}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    try:
        return await run_in_threadpool(index_video, get_encoder(), get_store(), dest, video_id, name)
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, f"could not index video: {e}") from e


@app.delete("/videos/{video_id}")
def delete_video(video_id: str):
    get_store().delete_video(video_id)
    for p in settings.video_dir.glob(f"{video_id}.*"):
        p.unlink()
    return {"deleted": video_id}


@app.get("/videos/{video_id}/file")
def video_file(video_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", video_id):
        raise HTTPException(400, "bad id")
    matches = list(settings.video_dir.glob(f"{video_id}.*"))
    if not matches:
        raise HTTPException(404, "not found")
    return FileResponse(matches[0])


@app.get("/benchmarks")
def benchmarks():
    """Committed eval results (eval/results/*.json), so the UI shows exactly what the repo claims."""
    results_dir = BACKEND_DIR / "eval" / "results"
    return [json.loads(p.read_text()) | {"file": p.name} for p in sorted(results_dir.glob("*.json"))]


@app.get("/search", response_model=SearchResponse)
async def search_videos(q: str = Query(..., min_length=1), k: int = Query(10, ge=1, le=100)):
    return await run_in_threadpool(search, get_encoder(), get_store(), q, k)
