import json
import math
import os
import traceback
from pathlib import Path

from ..config import Settings
from ..models import JobRequestOptions, StoryGraphPlan
from ..storage import JobStore
from .llm_client import GeminiStoryPlanner
from .video_generation.base import VideoGenerationProvider
from .video_generation.fal_seedance import FalSeedanceProvider
from .video_generation.google_veo import GoogleVeoProvider
from .video_generation.mock import MockVideoProvider
from .video_utils import concat_videos


class GenerationPipeline:
    def __init__(self, settings: Settings, store: JobStore):
        self.settings = settings
        self.store = store

    def run(self, job_id: str, input_video: Path | None, options: JobRequestOptions) -> None:
        self._run_with_error_handling(job_id, input_video, options, resume_existing_plan=False)

    def resume(self, job_id: str) -> None:
        """Resume a failed job, reusing the saved story plan and any finished segment files."""
        options = self.store.read_options(job_id)
        input_video = self.store.find_input_video(job_id) if options.input_mode == "video" else None
        self._run_with_error_handling(job_id, input_video, options, resume_existing_plan=True)

    def _run_with_error_handling(
        self,
        job_id: str,
        input_video: Path | None,
        options: JobRequestOptions,
        *,
        resume_existing_plan: bool,
    ) -> None:
        try:
            self._run(job_id, input_video, options, resume_existing_plan=resume_existing_plan)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            tb = traceback.format_exc()
            (self.store.job_dir(job_id) / "error_traceback.txt").write_text(tb, encoding="utf-8")
            self.store.update_status(job_id, status="failed", progress=1.0, message=error, error=error)

    def _run(
        self,
        job_id: str,
        input_video: Path | None,
        options: JobRequestOptions,
        *,
        resume_existing_plan: bool = False,
    ) -> None:
        job_settings = self._settings_for_job(options)
        job_dir = self.store.job_dir(job_id)
        segments_dir = job_dir / "segments"
        clips_dir = job_dir / "clips"
        scripts_dir = job_dir / "scripts"
        tmp_dir = job_dir / "tmp"

        self.store.write_json(job_id, "scripts/runtime_settings.json", {
            "video_provider": job_settings.video_provider,
            "segment_seconds": job_settings.segment_seconds,
            "segments_per_node": job_settings.segments_per_node,
            "clip_length_seconds_requested": options.clip_length_seconds,
            "clip_length_seconds_actual": job_settings.segment_seconds * job_settings.segments_per_node,
            "video_aspect_ratio": job_settings.video_aspect_ratio,
            "veo_model_id": job_settings.veo_model_id,
            "veo_resolution": job_settings.veo_resolution,
        })

        script_plan_path = job_dir / "scripts" / "script_plan.json"
        if resume_existing_plan and script_plan_path.exists():
            self.store.update_status(
                job_id,
                status="generating",
                progress=0.08,
                message="Resuming failed job from saved story plan...",
                error=None,
            )
            graph = StoryGraphPlan.model_validate_json(script_plan_path.read_text(encoding="utf-8"))
            self.store.append_log(
                job_id,
                f"Resuming from saved story graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges. "
                "Existing non-empty segment files will be reused.",
            )
        else:
            self.store.update_status(
                job_id,
                status="analyzing",
                progress=0.05,
                message="Analyzing input and writing story graph...",
                error=None,
            )
            planner = GeminiStoryPlanner(job_settings, on_log=lambda message: self.store.append_log(job_id, message))
            graph = planner.plan_story_graph(input_video, options)
            self.store.write_json(job_id, "scripts/script_plan.json", graph.model_dump(mode="json"))
            self.store.append_log(job_id, f"Story graph created: {len(graph.nodes)} nodes, {len(graph.edges)} edges.")
        self.store.append_log(
            job_id,
            f"Provider={job_settings.video_provider}; requested clip length={options.clip_length_seconds}s; "
            f"actual clip length≈{job_settings.segment_seconds * job_settings.segments_per_node}s "
            f"({job_settings.segments_per_node} × {job_settings.segment_seconds}s).",
        )

        provider = self._make_video_provider(job_settings, tmp_dir, job_id)
        reference_url = None
        if input_video is not None and self._needs_reference(job_settings, graph):
            self.store.append_log(job_id, "Preparing short source-video reference for video generation...")
            reference_url = provider.prepare_reference(input_video)
            if reference_url:
                self.store.write_json(job_id, "scripts/reference.json", {"reference_url": reference_url})

        total_segments = sum(len(node.segments) for node in graph.nodes)
        done_segments = 0
        self.store.update_status(job_id, status="generating", progress=0.10, message="Generating AI video segments...")

        for node in graph.nodes:
            segment_paths: list[Path] = []
            for segment in node.segments:
                use_reference = input_video is not None and self._should_use_reference(job_settings, graph.root_id, node.id, segment.index)
                segment_filename = f"{node.id}_seg{segment.index + 1:02d}.mp4"
                segment_output = segments_dir / segment_filename
                self.store.append_log(job_id, f"Generating {node.id} segment {segment.index + 1}/{len(node.segments)}...")

                # Reuse an existing non-empty segment when a failed job is manually rerun later.
                if segment_output.exists() and segment_output.stat().st_size > 1024:
                    self.store.append_log(job_id, f"Reusing existing segment file: {segment_output.name}")
                    segment.filename = segment_output.name
                    updated_segment = segment
                else:
                    updated_segment = provider.generate_segment(
                        job_id=job_id,
                        graph=graph,
                        node_id=node.id,
                        segment=segment,
                        output_path=segment_output,
                        reference_url=reference_url,
                        use_reference=use_reference,
                    )

                segment_paths.append(segment_output)
                node.segments[segment.index] = updated_segment
                done_segments += 1
                progress = 0.10 + 0.75 * (done_segments / max(total_segments, 1))
                self.store.update_status(job_id, status="generating", progress=progress, message=f"Generated {done_segments}/{total_segments} video segments.")

            self.store.update_status(job_id, status="concatenating", progress=0.88, message=f"Concatenating final clip for {node.id}...")
            final_clip = clips_dir / f"{node.id}.mp4"
            concat_videos(segment_paths, final_clip)
            node.filename = f"clips/{final_clip.name}"
            self.store.write_json(job_id, f"scripts/{node.id}.script.json", node.model_dump(mode="json"))
            self.store.append_log(job_id, f"Final clip completed for {node.id}.")

        graph_payload = graph.model_dump(mode="json")
        self.store.write_json(job_id, "graph.json", graph_payload)
        self.store.update_status(
            job_id,
            status="completed",
            progress=1.0,
            message="All clips generated. Interactive graph is ready.",
            graph_url=f"/api/jobs/{job_id}/graph",
        )

    def _settings_for_job(self, options: JobRequestOptions) -> Settings:
        provider = options.video_provider or self.settings.video_provider
        clip_len = int(options.clip_length_seconds)

        update = {"video_provider": provider}

        if provider.startswith("veo"):
            segment_seconds = self.settings.veo_duration_seconds
            if provider == "veo_lite":
                update["veo_model_id"] = self.settings.veo_lite_model_id
            elif provider == "veo_fast":
                update["veo_model_id"] = self.settings.veo_fast_model_id
            elif provider in {"veo_standard", "veo"}:
                update["veo_model_id"] = self.settings.veo_standard_model_id
            else:
                update["veo_model_id"] = self.settings.veo_model_id
            update["generate_audio"] = True  # Veo 3.1 outputs native audio.
        elif provider == "fal":
            segment_seconds = min(15, max(4, self.settings.segment_seconds if self.settings.segment_seconds else 15))
            update["generate_audio"] = self.settings.generate_audio
        else:
            segment_seconds = min(8, max(4, self.settings.segment_seconds if self.settings.segment_seconds else 8))
            update["generate_audio"] = self.settings.generate_audio

        segments_per_node = max(1, math.ceil(clip_len / segment_seconds))
        update["segment_seconds"] = segment_seconds
        update["segments_per_node"] = segments_per_node
        return self.settings.model_copy(update=update)

    def _make_video_provider(self, settings: Settings, tmp_dir: Path, job_id: str) -> VideoGenerationProvider:
        if settings.video_provider.startswith("veo"):
            return GoogleVeoProvider(settings, on_log=lambda message: self.store.append_log(job_id, message))
        if settings.video_provider == "fal":
            if settings.fal_key:
                os.environ["FAL_KEY"] = settings.fal_key
            return FalSeedanceProvider(settings, tmp_dir, on_log=lambda message: self.store.append_log(job_id, message))
        return MockVideoProvider(settings)

    def _needs_reference(self, settings: Settings, graph: StoryGraphPlan) -> bool:
        return settings.video_provider == "fal" and any(
            self._should_use_reference(settings, graph.root_id, node.id, segment.index)
            for node in graph.nodes
            for segment in node.segments
        )

    def _should_use_reference(self, settings: Settings, root_id: str, node_id: str, segment_index: int) -> bool:
        if settings.video_provider != "fal":
            return False
        if segment_index != 0:
            return False
        if settings.use_reference_for_all_node_first_segments:
            return True
        return settings.use_reference_for_root_first_segment and node_id == root_id
