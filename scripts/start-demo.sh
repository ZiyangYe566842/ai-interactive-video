#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
task_python="$task_root/backend/.venv/bin/python"
if [[ ! -x "$task_python" || ! -d "$task_root/frontend/node_modules" ]]; then
  echo "Install dependencies using README.md first." >&2
  exit 1
fi
command -v ffmpeg >/dev/null 2>&1 || { echo "FFmpeg is required." >&2; exit 1; }
task_backend_pid=""
task_frontend_pid=""
task_cleanup() {
  [[ -z "$task_backend_pid" ]] || kill "$task_backend_pid" 2>/dev/null || true
  [[ -z "$task_frontend_pid" ]] || kill "$task_frontend_pid" 2>/dev/null || true
}
trap task_cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
(cd "$task_root/backend" && VIDEO_PROVIDER=mock exec "$task_python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000) &
task_backend_pid=$!
(cd "$task_root/frontend" && exec node node_modules/vite/bin/vite.js) &
task_frontend_pid=$!
echo "Local demo: http://localhost:5173 — choose Local demo and enter a concept."
echo "Press Ctrl+C to stop both servers."
wait "$task_backend_pid" "$task_frontend_pid"
