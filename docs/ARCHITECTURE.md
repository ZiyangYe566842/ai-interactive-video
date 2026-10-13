# Architecture and API

## Pipeline

1. FastAPI accepts a text concept or upload and stores job options.
2. The planner produces a directed story graph and segment prompts. Mock mode uses local fallback beats; live planning can use Gemini.
3. The selected provider creates each segment sequentially. Global style and character memory are included in prompts.
4. FFmpeg concatenates each node's segments into a playable clip.
5. The backend writes the graph and marks the job completed. React polls status and lets viewers choose outgoing edges.

Every node is generated upfront. Graph traversal does not issue additional generation requests.

## Source map

| Path | Responsibility |
| --- | --- |
| `backend/app/main.py` | FastAPI routes, validation, static media |
| `backend/app/config.py` | Environment settings |
| `backend/app/models.py` | Job and graph schemas |
| `backend/app/storage.py` | Job files/status, guarded job paths |
| `backend/app/services/llm_client.py` | Story planning and normalization |
| `backend/app/services/pipeline.py` | Generation, progress, retries, clip assembly |
| `backend/app/services/video_generation` | Provider interface and adapters |
| `frontend/src/main.jsx` | Input form, polling, history, interactive player |
| `backend/tests` | API, storage, plan, and local-video tests |

## API

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Backend health and configured defaults |
| GET | `/api/jobs?limit=30` | Latest jobs; limit is 1–100 |
| POST | `/api/jobs` | Create a job using multipart form data |
| GET | `/api/jobs/{job_id}` | Status, progress, logs, and graph URL |
| POST | `/api/jobs/{job_id}/retry` | Retry failed work using saved assets |
| GET | `/api/jobs/{job_id}/graph` | Completed story graph |
| GET | `/api/jobs/{job_id}/file/{asset_path}` | A file contained within the job directory |
| GET | `/media/{job_id}/clips/{node_id}.mp4` | Playable clip |

Create-job fields: `input_mode` (`text`/`video`), `input_text`, `video`, `genre`, `clip_length_seconds` (`15`/`60`), and optional `video_provider`.

Job IDs are 16 hexadecimal characters. The file route resolves paths and requires containment in the selected job directory.

## Runtime storage

Each job contains input, segment videos, final clips, story scripts, options, status, and graph JSON. These are runtime files and are ignored by Git. Filesystem storage and in-process background tasks are deliberately simple; there is no durable queue or automatic recovery worker.

The media mount serves job assets without authentication. Keep the app on localhost for local use.
