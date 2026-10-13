import json
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Path as PathParam, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .models import JobRequestOptions, JobStatus
from .storage import JobStore
from .services.pipeline import GenerationPipeline

settings = get_settings()
store = JobStore(settings)
app = FastAPI(title=settings.app_name)

JobId = PathParam(pattern=r"^[a-f0-9]{16}$")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serves final videos and other job assets.
app.mount("/media", StaticFiles(directory=settings.data_dir / "jobs"), name="media")


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "app": settings.app_name,
        "default_video_provider": settings.video_provider,
        "default_veo_model_id": settings.veo_model_id,
    }


@app.get("/api/jobs", response_model=list[JobStatus])
def list_jobs(limit: int = Query(default=30, ge=1, le=100)) -> list[JobStatus]:
    return store.list_jobs(limit=limit)


@app.post("/api/jobs", response_model=JobStatus)
async def create_job(
    background_tasks: BackgroundTasks,
    video: UploadFile | None = File(default=None),
    input_text: str | None = Form(default=None),
    input_mode: str = Form(default="video"),
    genre: str = Form(default="absurd_comedy"),
    clip_length_seconds: str = Form(default="15"),
    video_provider: str | None = Form(default=None),
) -> JobStatus:
    input_text = (input_text or "").strip() or None
    video_provider = video_provider or settings.video_provider

    if input_mode not in {"video", "text"}:
        raise HTTPException(status_code=422, detail="input_mode must be video or text.")

    try:
        clip_length_value = int(str(clip_length_seconds).strip())
    except ValueError:
        raise HTTPException(status_code=422, detail="clip_length_seconds must be 15 or 60.")
    if clip_length_value not in {15, 60}:
        raise HTTPException(status_code=422, detail="clip_length_seconds must be 15 or 60.")

    allowed_providers = {"mock", "fal", "veo", "veo_lite", "veo_fast", "veo_standard"}
    if video_provider not in allowed_providers:
        raise HTTPException(status_code=422, detail=f"video_provider must be one of: {', '.join(sorted(allowed_providers))}.")

    if video_provider.startswith("veo") and not settings.gemini_api_key:
        raise HTTPException(status_code=400, detail="Set GEMINI_API_KEY in backend/.env before selecting Veo, or use mock mode.")
    if video_provider == "fal" and not settings.fal_key:
        raise HTTPException(status_code=400, detail="Set FAL_KEY in backend/.env before selecting fal, or use mock mode.")

    if input_mode == "video":
        if video is None or not video.filename:
            raise HTTPException(status_code=400, detail="Please upload a video file or switch to text input mode.")
        if not (video.content_type or "").startswith("video/"):
            raise HTTPException(status_code=400, detail="Please upload a video file.")
    else:
        if not input_text:
            raise HTTPException(status_code=400, detail="Please enter a text concept or switch to video input mode.")
        video = None

    options = JobRequestOptions(
        input_mode=input_mode,
        input_text=input_text,
        genre=genre,
        clip_length_seconds=clip_length_value,
        video_provider=video_provider,
    )

    status = store.create_job(original_filename=video.filename if video else None, options=options)
    input_path = None
    if video is not None:
        input_path = store.save_upload(status.job_id, video.file, video.filename)
        store.append_log(status.job_id, f"Uploaded source video: {video.filename}")
    else:
        store.append_log(status.job_id, f"Using text-only concept: {input_text[:160]}")

    if video_provider.startswith("veo"):
        store.append_log(status.job_id, "Using Google Veo 3.1 text-to-video. Uploaded video, if any, is used only for Gemini story planning, not as Veo video input.")

    pipeline = GenerationPipeline(settings, store)
    background_tasks.add_task(pipeline.run, status.job_id, input_path, options)
    return store.read_status(status.job_id)


@app.get("/api/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str = JobId) -> JobStatus:
    try:
        return store.read_status(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found.")




@app.post("/api/jobs/{job_id}/retry", response_model=JobStatus)
def retry_job(background_tasks: BackgroundTasks, job_id: str = JobId) -> JobStatus:
    try:
        status = store.read_status(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found.")

    if status.status in {"queued", "analyzing", "generating", "concatenating"}:
        raise HTTPException(status_code=409, detail="Job is already running.")

    if status.status == "completed":
        return status

    options = store.read_options(job_id)
    if options.input_mode == "video" and store.find_input_video(job_id) is None:
        raise HTTPException(status_code=400, detail="Cannot retry this video job because the original uploaded video file is missing.")

    store.update_status(
        job_id,
        status="queued",
        progress=0.0,
        message="Retry queued. The backend will reuse saved story plans and finished segments when possible.",
        error=None,
    )
    store.append_log(job_id, "Retry requested from UI/API. Reusing saved script plan and finished segment files when possible.")
    pipeline = GenerationPipeline(settings, store)
    background_tasks.add_task(pipeline.resume, job_id)
    return store.read_status(job_id)


@app.get("/api/jobs/{job_id}/graph")
def get_graph(job_id: str = JobId) -> dict:
    graph_path = store.graph_path(job_id)
    if not graph_path.exists():
        raise HTTPException(status_code=404, detail="Graph is not ready yet.")
    return json.loads(graph_path.read_text(encoding="utf-8"))


@app.get("/api/jobs/{job_id}/file/{asset_path:path}")
def get_job_file(asset_path: str, job_id: str = JobId) -> FileResponse:
    job_dir = store.job_dir(job_id).resolve()
    path = (job_dir / asset_path).resolve()
    if not path.is_relative_to(job_dir) or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(path)


def media_url(job_id: str, filename: str) -> str:
    return f"/media/{job_id}/{filename.lstrip('/')}"
