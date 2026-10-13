from pathlib import Path
from typing import Any, Callable

import requests

from .base import VideoGenerationProvider
from ..video_utils import extract_reference_clip
from ...config import Settings
from ...models import SegmentPlan, StoryGraphPlan


class FalSeedanceProvider(VideoGenerationProvider):
    """fal.ai Seedance 2.0 adapter.

    API-specific code is intentionally isolated in this class so that changing
    from Seedance/fal to another provider later only requires replacing this
    adapter and environment variables.
    """

    def __init__(self, settings: Settings, tmp_dir: Path, on_log: Callable[[str], None] | None = None):
        self.settings = settings
        self.tmp_dir = tmp_dir
        self.on_log = on_log or (lambda message: None)

    def prepare_reference(self, source_video: Path | None) -> str | None:
        import fal_client

        if source_video is None:
            return None

        reference_clip = self.tmp_dir / "reference_for_seedance.mp4"
        self.on_log(f"Creating {self.settings.reference_clip_seconds}s source-video reference clip for fal...")
        extract_reference_clip(source_video, reference_clip, self.settings.reference_clip_seconds)
        self.on_log(f"Uploading reference clip to fal: {reference_clip.name} ({reference_clip.stat().st_size / 1024 / 1024:.2f} MB)...")
        url = fal_client.upload_file(str(reference_clip))
        self.on_log(f"fal reference upload finished: {url}")
        return url

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
        import fal_client

        output_path.parent.mkdir(parents=True, exist_ok=True)
        prompt = self._build_prompt(graph=graph, node_id=node_id, segment=segment, use_reference=use_reference)

        try:
            result = self._call_seedance(fal_client, prompt=prompt, reference_url=reference_url, use_reference=use_reference)
        except Exception as exc:
            self.on_log(f"fal Seedance call failed while use_reference={use_reference}: {type(exc).__name__}: {exc}")
            if not use_reference or not self.settings.fallback_to_text_on_reference_error:
                raise
            # Some providers reject certain reference videos, especially videos containing people or private information.
            # Keep the job alive by retrying text-to-video.
            self.on_log("Retrying this segment with text-to-video because reference-to-video failed...")
            fallback_prompt = self._build_prompt(graph=graph, node_id=node_id, segment=segment, use_reference=False)
            result = self._call_seedance(fal_client, prompt=fallback_prompt, reference_url=None, use_reference=False)

        video_url = self._extract_video_url(result)
        self.on_log(f"Downloading generated segment from fal: {video_url}")
        self._download(video_url, output_path)
        self.on_log(f"Saved generated segment: {output_path.name} ({output_path.stat().st_size / 1024 / 1024:.2f} MB)")
        segment.filename = output_path.name
        segment.generated_url = video_url
        return segment

    def _call_seedance(self, fal_client, *, prompt: str, reference_url: str | None, use_reference: bool) -> dict:
        application = self.settings.fal_reference_model_id if (use_reference and reference_url) else self.settings.fal_text_model_id
        arguments: dict[str, Any] = {
            "prompt": prompt,
            "resolution": self.settings.video_resolution,
            "duration": str(self.settings.segment_seconds),
            "aspect_ratio": self.settings.video_aspect_ratio,
            "generate_audio": self.settings.generate_audio,
        }
        if use_reference and reference_url:
            arguments["video_urls"] = [reference_url]

        self.on_log(f"Submitting fal request to {application} (duration={arguments['duration']}s, audio={arguments['generate_audio']})...")

        def on_enqueue(request_id: str) -> None:
            self.on_log(f"fal enqueued request_id={request_id}")

        seen_log_messages: set[str] = set()

        def on_queue_update(update: Any) -> None:
            update_type = type(update).__name__
            position = getattr(update, "position", None)
            if position is not None:
                self.on_log(f"fal status: {update_type}, queue position={position}")
            else:
                self.on_log(f"fal status: {update_type}")

            logs = getattr(update, "logs", None) or []
            for item in logs:
                if isinstance(item, dict):
                    message = item.get("message") or str(item)
                else:
                    message = str(item)
                if message and message not in seen_log_messages:
                    seen_log_messages.add(message)
                    self.on_log(f"fal log: {message}")

        # Important: client_timeout prevents the UI from looking stuck forever.
        # fal docs say subscribe otherwise waits indefinitely if client_timeout is not set.
        result = fal_client.subscribe(
            application,
            arguments=arguments,
            with_logs=True,
            on_enqueue=on_enqueue,
            on_queue_update=on_queue_update,
            start_timeout=self.settings.fal_start_timeout_seconds,
            client_timeout=self.settings.fal_client_timeout_seconds,
        )
        self.on_log(f"fal completed request for {application}")
        return result

    def _build_prompt(self, *, graph: StoryGraphPlan, node_id: str, segment: SegmentPlan, use_reference: bool) -> str:
        reference_line = "Use @Video1 as the source/reference video. " if use_reference else ""
        return (
            f"{reference_line}Genre/tone: {graph.genre or 'interactive video'}.\n"
            f"Preserve this global visual memory: {graph.style_summary}\n"
            f"Preserve this character/object memory: {graph.character_and_object_memory}\n"
            f"Current graph node: {node_id}. Segment: {segment.index + 1}.\n"
            f"Action prompt: {segment.prompt}\n"
            "Make the clip coherent, cinematic, and short. Match the selected genre and story tone. "
            "Include safe synchronized audio when enabled: natural ambience, simple sound effects, and brief original dialogue only if appropriate. "
            "Avoid copyrighted songs, recognizable lyrics, captions, watermarks, UI, or explanatory text overlays."
        )

    @staticmethod
    def _extract_video_url(result: dict) -> str:
        video = result.get("video")
        if isinstance(video, dict) and video.get("url"):
            return video["url"]
        videos = result.get("videos")
        if isinstance(videos, list) and videos and isinstance(videos[0], dict) and videos[0].get("url"):
            return videos[0]["url"]
        raise RuntimeError(f"Cannot find generated video URL in fal response. Response keys: {list(result.keys())}")

    @staticmethod
    def _download(url: str, output_path: Path) -> None:
        with requests.get(url, stream=True, timeout=600) as response:
            response.raise_for_status()
            with output_path.open("wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
