"""Quick standalone fal.ai Seedance smoke test.

Run from backend/:
    python scripts/smoke_fal_seedance.py

It submits one tiny 4-second text-to-video request. If this does not show a
request_id and queue status, the problem is your FAL_KEY / account / network,
not the app pipeline.
"""

import os
from pathlib import Path

from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    fal_key = os.getenv("FAL_KEY")
    if not fal_key:
        raise SystemExit("FAL_KEY is missing. Put FAL_KEY=... in backend/.env or export it in this terminal.")

    import fal_client

    application = os.getenv("FAL_TEXT_MODEL_ID", "bytedance/seedance-2.0/text-to-video")
    print(f"Submitting smoke test to {application}...")

    def on_enqueue(request_id: str) -> None:
        print(f"ENQUEUED request_id={request_id}")

    def on_queue_update(update) -> None:
        print(f"STATUS {type(update).__name__}", end="")
        position = getattr(update, "position", None)
        if position is not None:
            print(f" position={position}", end="")
        print()
        for log in getattr(update, "logs", None) or []:
            if isinstance(log, dict):
                print("LOG", log.get("message") or log)
            else:
                print("LOG", log)

    result = fal_client.subscribe(
        application,
        arguments={
            "prompt": "A short funny cinematic clip: a tiny rubber duck wearing sunglasses slides across a desk, honks once, and a dramatic movie trailer sound plays.",
            "resolution": "480p",
            "duration": "4",
            "aspect_ratio": "16:9",
            "generate_audio": True,
        },
        with_logs=True,
        on_enqueue=on_enqueue,
        on_queue_update=on_queue_update,
        start_timeout=int(os.getenv("FAL_START_TIMEOUT_SECONDS", "300")),
        client_timeout=int(os.getenv("FAL_CLIENT_TIMEOUT_SECONDS", "900")),
    )
    print("RESULT KEYS:", list(result.keys()))
    print("VIDEO URL:", (result.get("video") or {}).get("url"))


if __name__ == "__main__":
    main()
