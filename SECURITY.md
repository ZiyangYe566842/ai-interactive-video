# Security

Keep provider keys in local environment variables or ignored `.env` files.
Never include keys, user media, or private logs in issues or pull requests.
Run `python3 scripts/check_release.py` before publishing source changes.
This focused check is not a comprehensive secret detector.

These tools are intended for local, trusted use. The video API has no login or
job ownership checks; the game generator executes generated code on your
machine. For untrusted inputs or public hosting, add authentication, request
limits, worker isolation, and deployment-specific controls.

If a key has been exposed, revoke it at its provider. When reporting a
security issue, describe the reproduction without including live credentials
or private files. Use GitHub private vulnerability reporting if the repository
owner has enabled it.
