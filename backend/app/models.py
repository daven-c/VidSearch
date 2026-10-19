from pydantic import BaseModel


class VideoInfo(BaseModel):
    video_id: str
    filename: str
    duration: float
    num_frames: int


class Moment(BaseModel):
    start: float
    end: float
    best_t: float
    score: float


class SearchHit(BaseModel):
    video_id: str
    filename: str
    duration: float
    score: float
    moments: list[Moment]


class SearchResponse(BaseModel):
    query: str
    took_ms: float
    hits: list[SearchHit]
