# Contributing

Use Python 3.12, Node.js 22.12+, and FFmpeg. Install the backend development requirements and frontend locked dependencies.

Run `python -m pytest -q` from the repository root using the backend environment, and `npm --prefix frontend run build`. Paid API generation is a separate manual check, never a CI requirement. Keep provider-specific code in its adapter.

Do not commit credentials, uploads, job outputs, virtual environments, or node_modules. Run `python3 scripts/check_release.py` before pushing.

Describe the concrete problem and resulting behavior in a PR, along with the checks you ran. If a provider's contract changes, document which account/model and SDK you tested.
