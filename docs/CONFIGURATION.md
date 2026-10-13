# Configuration

Run the backend from `backend/` so `.env` and the default `./data` resolve there. Environment variables override file settings.

## Backend

| Setting | Meaning |
| --- | --- |
| `VIDEO_PROVIDER` | API default when a request omits its provider; defaults to `mock` |
| `GEMINI_API_KEY` / `FAL_KEY` | Private provider credentials |
| `GEMINI_MODEL` | Story-planning model |
| `VEO_LITE_MODEL_ID` / `VEO_FAST_MODEL_ID` / `VEO_STANDARD_MODEL_ID` | Models for the explicit Veo modes |
| `VEO_MODEL_ID` | Legacy field; explicit modes use their corresponding IDs |
| `VEO_DURATION_SECONDS` | Single Veo segment length; default 8 |
| `VEO_RESOLUTION` | Veo output resolution; demo example uses 720p |
| `FAL_TEXT_MODEL_ID` / `FAL_REFERENCE_MODEL_ID` | Configurable fal endpoint IDs |
| `SEGMENT_SECONDS` | fal/mock segment length; mock is capped at 8, fal at 15 |
| `NODE_COUNT` | Story graph size; default 5 |
| `SEGMENTS_PER_NODE` | Base setting, overridden for API jobs using requested duration |
| `DATA_DIR` | Job storage, default `./data` |
| `FRONTEND_ORIGIN` | Allowed frontend origin |
| `VEO_MAX_RETRIES` | Retries for transient provider errors |
| `USE_REFERENCE_FOR_ROOT_FIRST_SEGMENT` | Use an uploaded reference for the first fal root segment |
| `USE_REFERENCE_FOR_ALL_NODE_FIRST_SEGMENTS` | Use a reference at all fal nodes |

The webpage defaults to `mock` independently of the API's environment default. Changing `VIDEO_PROVIDER` does not silently switch the webpage to a paid provider.

Use the provider's supported duration/resolution combinations. The bundled model IDs are starting points from the prototype; this release does not verify current live access. Keep genuine credentials in ignored environment files.

To use 15-second fal segments, set `SEGMENT_SECONDS=15`. Mock mode still caps segments at 8 seconds.

## Frontend

Set `VITE_API_BASE` in a local `frontend/.env` if the backend has a different address. The default is `http://localhost:8000`. The value is included in the frontend bundle; never put provider keys in a `VITE_` variable.

For example, copy `frontend/.env.example` to `frontend/.env` and change the base URL. Restart Vite after changes.

## References and planning

Mock mode never uploads media or calls Gemini. Live Gemini planning can upload an input video to Google's File API. Veo receives text prompts in this implementation, even when the input was a video. The fal path can upload a trimmed reference clip.

Without a Gemini key, fal uses fallback story planning. A failed job can be retried from saved plans and completed segment files; provider timeouts may still consume billable work.

## Troubleshooting

- **FFmpeg missing:** verify `ffmpeg -version` in the same terminal as the backend.
- **Missing key:** configure `backend/.env`, restart, and choose the matching provider.
- **Unavailable model:** update the model/endpoint ID using your provider catalog.
- **UI cannot reach API:** check the backend health URL, `VITE_API_BASE`, and `FRONTEND_ORIGIN`.
- **Interrupted job:** restore the job from history and use Retry after backend restart. This release does not automatically requeue in-flight jobs.

Official references: [Google video API](https://ai.google.dev/gemini-api/docs/video), [fal documentation](https://docs.fal.ai/), [Vite](https://vite.dev/guide/).

## Optional live smoke scripts

From `backend/`, `python scripts/smoke_google_veo.py` or
`python scripts/smoke_fal_seedance.py` submits a real provider request using
your configured key. These scripts can incur charges and are not pytest/CI
tests. They run only when invoked directly.
