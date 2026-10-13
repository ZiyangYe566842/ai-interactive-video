import time
from pathlib import Path
from typing import Any, Callable

from .base import VideoGenerationProvider
from ...config import Settings
from ...models import SegmentPlan, StoryGraphPlan


class VeoTransientError(RuntimeError):
    """A retryable Google Veo operation failure."""

    def __init__(self, message: str, *, code: int | None = None, operation_name: str | None = None):
        super().__init__(message)
        self.code = code
        self.operation_name = operation_name


class GoogleVeoProvider(VideoGenerationProvider):
    """Google Veo 3.1 text-to-video adapter.

    Important design decision for this MVP:
    - Uploaded user videos are used only by Gemini for understanding/story planning.
    - The user's uploaded video is NOT sent as a video input to Veo.
    - Veo receives text prompts only, because this workflow treats Veo 3.1 as text-to-video.
    """

    def __init__(self, settings: Settings, on_log: Callable[[str], None] | None = None):
        self.settings = settings
        self.on_log = on_log or (lambda message: None)
        if not self.settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required when VIDEO_PROVIDER uses Google Veo.")
        from google import genai

        self.client = genai.Client(api_key=self.settings.gemini_api_key)

    def prepare_reference(self, source_video: Path | None) -> str | None:
        return None

    def generate_segment(
        self,
        *,
        job_id: str,
        graph: StoryGraphPlan,
        node_id: str,
        segment: SegmentPlan,
        output_path: Path,
        reference_url: str | None,
        use_reference: bool,
    ) -> SegmentPlan:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        prompt = self._build_prompt(graph=graph, node_id=node_id, segment=segment)

        max_retries = self.settings.veo_max_retries
        delay = self.settings.veo_retry_initial_delay_seconds
        last_exc: Exception | None = None

        for attempt in range(1, max_retries + 2):
            try:
                operation_name = self._generate_once(prompt=prompt, segment=segment, output_path=output_path, attempt=attempt)
                segment.filename = output_path.name
                segment.generated_url = operation_name
                return segment
            except VeoTransientError as exc:
                last_exc = exc
                if attempt > max_retries:
                    raise
                self.on_log(
                    f"Veo transient failure on attempt {attempt}/{max_retries + 1}: {exc}. "
                    f"Waiting {delay}s, then regenerating this segment..."
                )
                time.sleep(delay)
                delay = int(delay * self.settings.veo_retry_backoff_multiplier)

        # Should be unreachable, but keeps static analyzers happy.
        raise RuntimeError(f"Veo generation failed after retries: {last_exc}")

    def _generate_once(self, *, prompt: str, segment: SegmentPlan, output_path: Path, attempt: int) -> str | None:
        self.on_log(
            f"Submitting Google Veo request to {self.settings.veo_model_id} "
            f"(attempt={attempt}, duration={segment.duration}s, resolution={self.settings.veo_resolution}, audio=always on)..."
        )

        from google.genai import types

        config = types.GenerateVideosConfig(
            aspect_ratio=self.settings.video_aspect_ratio,
            duration_seconds=str(segment.duration),
            resolution=self.settings.veo_resolution,
            number_of_videos=1,
        )

        operation = self.client.models.generate_videos(
            model=self.settings.veo_model_id,
            prompt=prompt,
            config=config,
        )
        operation_name = getattr(operation, "name", None)
        if operation_name:
            self.on_log(f"Veo operation started: {operation_name}")

        deadline = time.monotonic() + self.settings.veo_timeout_seconds
        poll = self.settings.veo_poll_interval_seconds
        while not getattr(operation, "done", False):
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Timed out waiting for Veo operation after {self.settings.veo_timeout_seconds}s. "
                    "Increase VEO_TIMEOUT_SECONDS or try again later."
                )
            self.on_log("Veo generation still running...")
            time.sleep(poll)
            operation = self.client.operations.get(operation)

        self._raise_if_operation_error(operation, operation_name)
        self._save_operation_video(operation, output_path)
        self.on_log(f"Saved Veo segment: {output_path.name} ({output_path.stat().st_size / 1024 / 1024:.2f} MB)")
        return operation_name

    def _build_prompt(self, *, graph: StoryGraphPlan, node_id: str, segment: SegmentPlan) -> str:
        return (
            f"Genre/tone: {graph.genre or 'cinematic interactive story'}.\n"
            f"Global visual/story memory: {graph.style_summary}\n"
            f"Character/object/setting memory: {graph.character_and_object_memory}\n"
            f"Current graph node: {node_id}. Segment: {segment.index + 1}.\n"
            f"Action prompt: {segment.prompt}\n"
            "Create a coherent cinematic video segment with native synchronized audio. "
            "Use natural ambience, safe sound effects, and brief original dialogue only if appropriate. "
            "Do not use copyrighted songs, recognizable lyrics, subtitles, captions, watermarks, UI, or explanatory text overlays."
        )

    def _raise_if_operation_error(self, operation: Any, operation_name: str | None) -> None:
        error = getattr(operation, "error", None)
        if not error:
            return

        code = None
        message = str(error)
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message") or message
        else:
            code = getattr(error, "code", None)
            message = getattr(error, "message", None) or message

        if self._is_transient_veo_error(code, message):
            raise VeoTransientError(
                f"operation={operation_name or '<unknown>'}, code={code}, message={message}",
                code=code,
                operation_name=operation_name,
            )
        raise RuntimeError(f"Veo operation failed: operation={operation_name or '<unknown>'}, code={code}, message={message}")

    def _is_transient_veo_error(self, code: int | None, message: str) -> bool:
        msg = (message or "").lower()
        return (
            code in {13, 14, 500, 502, 503, 504}
            or "internal server" in msg
            or "try again" in msg
            or "temporarily unavailable" in msg
            or "unavailable" in msg
            or "timeout" in msg
        )

    def _save_operation_video(self, operation: Any, output_path: Path) -> None:
        try:
            generated_video = operation.response.generated_videos[0]
        except Exception as exc:
            raise RuntimeError(f"Veo operation finished but no generated video was found: {operation}") from exc

        video_obj = generated_video.video
        try:
            self.client.files.download(file=video_obj)
            video_obj.save(str(output_path))
            return
        except Exception as primary_exc:
            # SDK versions differ slightly. Fall back to video_bytes when present.
            data = getattr(video_obj, "video_bytes", None) or getattr(video_obj, "data", None)
            if data:
                output_path.write_bytes(data)
                return
            raise RuntimeError(f"Failed to download/save Veo video: {primary_exc}") from primary_exc
