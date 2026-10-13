# Validation

Validated on 2026-10-12 (America/New_York).

Environment: Python 3.12, Node.js 24.19.0, npm 11.9.0, FFmpeg, local Chromium 133.0.6943.0.

| Check | Result |
| --- | --- |
| Backend tests | 7 passed |
| Frontend production build | Passed |
| Actual local FFmpeg job | Passed; generated playable MP4 files and persisted graph/status |
| Mock mode with a configured Gemini key | Does not call Gemini |
| Credential/input validation | Missing live keys, empty text, invalid durations, and invalid limits rejected |
| Path containment | Traversal into sibling/private job paths rejected |
| Graph normalization | Unique node IDs and valid root |
| Browser input/default provider | Text input and local mock provider confirmed |
| Browser video playback | A generated local clip loaded; duration 16.04 seconds |
| Branch choice | Moved from clip1 to clip2 through an on-screen choice |
| Reload recovery | Restored clip2 and its saved path |
| Browser runtime / external requests | No page errors; no external requests |
| Release source check | Passed before packaging |

The README screenshots come from the actual running app with local placeholder videos. Live Google/fal services were not called; their credentials, quotas, endpoint availability, output continuity, and charges were not verified.

The frontend uses pinned React 19.1.1, Vite 7.3.7, and React plugin 5.1.4. Original floating/future package selections were replaced with versions that installed and built successfully here.

Backend tests produced one Starlette deprecation warning about its httpx test transport; the tests passed. The GitHub CI workflow is provided but has not yet run on GitHub.
