import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types


def main() -> None:
    load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("Set GEMINI_API_KEY in backend/.env first.")

    model = os.getenv("VEO_MODEL_ID", "veo-3.1-generate-preview")
    duration = os.getenv("VEO_DURATION_SECONDS", "8")
    resolution = os.getenv("VEO_RESOLUTION", "1080p")

    client = genai.Client(api_key=api_key)
    prompt = (
        "A short cinematic science-fiction shot of a tiny friendly robot walking across a desk, "
        "natural room ambience, gentle mechanical sound effects, no text overlays, no copyrighted music."
    )

    operation = client.models.generate_videos(
        model=model,
        prompt=prompt,
        config=types.GenerateVideosConfig(
            aspect_ratio="16:9",
            duration_seconds=str(duration),
            resolution=resolution,
            number_of_videos=1,
        ),
    )
    print("Started operation:", getattr(operation, "name", None))

    while not operation.done:
        print("Waiting for Veo generation...")
        time.sleep(10)
        operation = client.operations.get(operation)

    out = Path("veo_test.mp4")
    generated_video = operation.response.generated_videos[0]
    client.files.download(file=generated_video.video)
    generated_video.video.save(str(out))
    print("Saved", out.resolve())


if __name__ == "__main__":
    main()
