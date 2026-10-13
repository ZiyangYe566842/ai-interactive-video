#!/usr/bin/env python3
"""Check tracked source for local data and credentials without printing values."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", "generated", "data", "dist", "test-results", "playwright-report"}
PATTERNS = {
    "Google API key": re.compile(r"AIza[A-Za-z0-9_-]{30,}"),
    "OpenAI/Anthropic-style key": re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{30,}"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})"),
    "private key": re.compile("-----BEGIN " + "(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def main():
    probe = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True)
    if probe.returncode == 0 and probe.stdout:
        paths = [ROOT / name.decode() for name in probe.stdout.split(b"\0") if name]
    else:
        paths = [p for p in ROOT.rglob("*") if p.is_file() and not any(part in SKIP for part in p.relative_to(ROOT).parts)]
    errors = []
    for path in paths:
        relative = path.relative_to(ROOT)
        if any(part in SKIP or part == ".DS_Store" or part.startswith("._") or part == "__MACOSX" for part in relative.parts):
            errors.append((relative, "local dependency, cache, or runtime data"))
        if path.name.startswith(".env") and path.name != ".env.example":
            errors.append((relative, "actual environment file"))
        if path.name.endswith(".bak") or ".bak." in path.name:
            errors.append((relative, "configuration backup"))
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pattern in PATTERNS.items():
            if pattern.search(content):
                errors.append((relative, label))
    for path, label in errors:
        print(f"FAIL {path}: {label}", file=sys.stderr)
    if errors:
        return 1
    print(f"Release check passed for {len(paths)} source files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
