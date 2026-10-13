from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


VideoProvider = Literal["mock", "fal", "veo", "veo_lite", "veo_fast", "veo_standard"]
InputMode = Literal["video", "text"]


class JobRequestOptions(BaseModel):
    input_mode: InputMode = "video"
    input_text: str | None = None
    genre: str = "absurd_comedy"
    clip_length_seconds: int = 15
    video_provider: VideoProvider = "mock"


class SegmentPlan(BaseModel):
    index: int
    prompt: str
    duration: int = Field(default=8, ge=4, le=15)
    filename: str | None = None
    generated_url: str | None = None


class NodePlan(BaseModel):
    id: str
    option: str
    title: str | None = None
    description: str | None = None
    filename: str | None = None
    segments: list[SegmentPlan] = Field(default_factory=list)


class EdgePlan(BaseModel):
    source: str
    target: str
    label: str | None = None


class StoryGraphPlan(BaseModel):
    root_id: str = "clip1"
    style_summary: str = ""
    character_and_object_memory: str = ""
    genre: str = ""
    nodes: list[NodePlan]
    edges: list[EdgePlan]


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "analyzing", "generating", "concatenating", "completed", "failed"]
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    message: str = ""
    created_at: str
    updated_at: str
    input_filename: str | None = None
    input_mode: InputMode = "video"
    input_text: str | None = None
    genre: str = "absurd_comedy"
    clip_length_seconds: int = 15
    video_provider: VideoProvider = "mock"
    graph_url: str | None = None
    error: str | None = None
    logs: list[str] = Field(default_factory=list)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
