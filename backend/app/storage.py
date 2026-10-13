import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from .config import Settings
from .models import JobRequestOptions, JobStatus, utc_now_iso


class JobStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.jobs_dir = settings.data_dir / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def create_job(self, *, original_filename: str | None, options: JobRequestOptions) -> JobStatus:
        job_id = uuid.uuid4().hex[:16]
        job_dir = self.job_dir(job_id)
        for child in ["input", "segments", "clips", "scripts", "tmp"]:
            (job_dir / child).mkdir(parents=True, exist_ok=True)
        now = utc_now_iso()
        status = JobStatus(
            job_id=job_id,
            status="queued",
            progress=0.0,
            message="Job created.",
            created_at=now,
            updated_at=now,
            input_filename=original_filename,
            input_mode=options.input_mode,
            input_text=options.input_text,
            genre=options.genre,
            clip_length_seconds=options.clip_length_seconds,
            video_provider=options.video_provider,
            logs=["Job created."],
        )
        self.write_status(status)
        self.write_json(job_id, "job_options.json", options.model_dump(mode="json"))
        if options.input_text:
            (job_dir / "input" / "prompt.txt").write_text(options.input_text, encoding="utf-8")
        return status

    def job_dir(self, job_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{16}", job_id):
            raise ValueError("Invalid job ID.")
        return self.jobs_dir / job_id

    def status_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "job.json"

    def graph_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "graph.json"

    def read_status(self, job_id: str) -> JobStatus:
        path = self.status_path(job_id)
        if not path.exists():
            raise FileNotFoundError(f"Job not found: {job_id}")
        return JobStatus.model_validate_json(path.read_text(encoding="utf-8"))

    def read_options(self, job_id: str) -> JobRequestOptions:
        path = self.job_dir(job_id) / "job_options.json"
        if path.exists():
            return JobRequestOptions.model_validate_json(path.read_text(encoding="utf-8"))
        status = self.read_status(job_id)
        return JobRequestOptions(
            input_mode=status.input_mode,
            input_text=status.input_text,
            genre=status.genre,
            clip_length_seconds=15 if status.clip_length_seconds not in {15, 60} else status.clip_length_seconds,
            video_provider=status.video_provider,
        )

    def write_status(self, status: JobStatus) -> None:
        status.updated_at = utc_now_iso()
        path = self.status_path(status.job_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(status.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)

    def update_status(self, job_id: str, **changes: Any) -> JobStatus:
        status = self.read_status(job_id)
        for key, value in changes.items():
            setattr(status, key, value)
        self.write_status(status)
        return status

    def append_log(self, job_id: str, message: str) -> None:
        status = self.read_status(job_id)
        status.logs.append(message)
        status.message = message
        self.write_status(status)

    def save_upload(self, job_id: str, file_obj, filename: str) -> Path:
        suffix = Path(filename).suffix or ".mp4"
        dst = self.job_dir(job_id) / "input" / f"original{suffix}"
        with dst.open("wb") as out:
            shutil.copyfileobj(file_obj, out)
        return dst

    def find_input_video(self, job_id: str) -> Path | None:
        input_dir = self.job_dir(job_id) / "input"
        for path in input_dir.glob("original.*"):
            if path.is_file() and path.stat().st_size > 0:
                return path
        return None

    def write_json(self, job_id: str, relative_path: str, payload: Any) -> Path:
        job_dir = self.job_dir(job_id).resolve()
        path = (job_dir / relative_path).resolve()
        if not path.is_relative_to(job_dir):
            raise ValueError("Job file path must stay inside its job directory.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def list_jobs(self, limit: int = 30) -> list[JobStatus]:
        jobs: list[JobStatus] = []
        for path in self.jobs_dir.glob("*/job.json"):
            try:
                jobs.append(JobStatus.model_validate_json(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]
