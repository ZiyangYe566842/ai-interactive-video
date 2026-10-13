import json
import math
import re
import time
from pathlib import Path
from typing import Any, Callable

from ..config import Settings
from ..models import EdgePlan, JobRequestOptions, NodePlan, SegmentPlan, StoryGraphPlan


GENRE_LABELS = {
    "absurd_comedy": "absurd comedy / viral physical gag",
    "light_comedy": "light family-friendly comedy",
    "cinematic_drama": "cinematic drama",
    "sci_fi": "science fiction",
    "fantasy": "fantasy adventure",
    "action": "action adventure",
    "mystery": "mystery / suspense",
    "romance": "romantic short story",
    "documentary": "mini documentary / educational",
    "advertisement": "commercial advertisement / product showcase",
}


class GeminiStoryPlanner:
    def __init__(self, settings: Settings, on_log: Callable[[str], None] | None = None):
        self.settings = settings
        self.on_log = on_log

    def plan_story_graph(self, input_video: Path | None, options: JobRequestOptions) -> StoryGraphPlan:
        if self.settings.video_provider == "mock" or not self.settings.gemini_api_key:
            return self._mock_plan(options)

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.settings.gemini_api_key)
        prompt = self._build_prompt(input_video=input_video, options=options)

        if input_video is not None:
            uploaded = client.files.upload(file=str(input_video))
            uploaded = self._wait_for_file_active(client, uploaded)
            contents = [uploaded, prompt]
        else:
            contents = [prompt]

        response = client.models.generate_content(
            model=self.settings.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.90,
            ),
        )
        raw = response.text or ""
        payload = self._parse_json(raw)
        return self._normalize_plan(payload, options)

    def _wait_for_file_active(self, client: Any, uploaded_file: Any) -> Any:
        """Wait until a Gemini File API upload is usable for video understanding."""
        file_name = getattr(uploaded_file, "name", None)
        if not file_name:
            return uploaded_file

        deadline = time.monotonic() + self.settings.gemini_file_processing_timeout_seconds
        poll_interval = self.settings.gemini_file_poll_interval_seconds
        current = uploaded_file

        while True:
            state = self._file_state_name(current)
            self._log(f"Gemini uploaded file {file_name} state: {state or 'UNKNOWN'}")

            if state == "ACTIVE":
                return current

            if state in {"FAILED", "ERROR"}:
                raise RuntimeError(f"Gemini File API processing failed for {file_name}; state={state}")

            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Timed out waiting for Gemini File API file {file_name} to become ACTIVE. "
                    f"Last state={state or 'UNKNOWN'}. Increase GEMINI_FILE_PROCESSING_TIMEOUT_SECONDS "
                    "or try a shorter/smaller input video."
                )

            time.sleep(poll_interval)
            current = client.files.get(name=file_name)

    @staticmethod
    def _file_state_name(file_obj: Any) -> str | None:
        state = getattr(file_obj, "state", None)
        if state is None:
            return None
        name = getattr(state, "name", None)
        if name:
            return str(name).upper()
        value = getattr(state, "value", None)
        if value:
            return str(value).upper()
        return str(state).split(".")[-1].upper()

    def _log(self, message: str) -> None:
        if self.on_log:
            self.on_log(message)

    def _build_prompt(self, *, input_video: Path | None, options: JobRequestOptions) -> str:
        node_count = self.settings.node_count
        segments_per_node = self.settings.segments_per_node
        segment_seconds = self.settings.segment_seconds
        total_seconds = segments_per_node * segment_seconds
        genre_label = GENRE_LABELS.get(options.genre, options.genre.replace("_", " "))
        input_description = (
            "The user uploaded a source video. Analyze it carefully: visual style, camera style, location, lighting, "
            "main people/characters if any, animals, objects, props, mood, and sound environment. Use the uploaded video "
            "only to create a text-based story plan and text prompts."
            if input_video is not None
            else f"The user provided this text concept instead of a video: {options.input_text!r}. Build the whole story from this concept."
        )
        provider_note = (
            "The video generator is Google Veo 3.1. It will receive TEXT ONLY. Do not write @Video1 and do not assume video input to Veo."
            if options.video_provider.startswith("veo")
            else (
                "The video generator is fal.ai Seedance. If a source video exists, clip1 segment 0 may use @Video1 as a reference video."
                if options.video_provider == "fal"
                else "The video generator is local mock mode for testing."
            )
        )

        root_reference_instruction = (
            "- For clip1 segment 0, explicitly reference the original uploaded video as @Video1 and ask to continue/transform it while preserving style, characters, objects, lighting, and camera."
            if options.video_provider == "fal" and input_video is not None
            else "- For clip1 segment 0, describe the opening scene fully in text. Do not refer to @Video1 or any video input."
        )

        return f"""
You are designing an AI interactive video app.
{input_description}

Selected genre/tone: {genre_label}.
{provider_note}

Create a directed graph story plan. The user will choose options after each generated clip.

Hard constraints:
- Return ONLY valid JSON. No markdown.
- root_id must be "clip1".
- Create exactly {node_count} nodes.
- Each node is a final playable clip of roughly {total_seconds} seconds.
- Each node must contain exactly {segments_per_node} segment prompts.
- Each segment prompt is for one {segment_seconds}-second video generation call.
- Segment prompts must be in English, detailed, cinematic, and safe.
- Prompts should include native audio cues because the default video should have sound: natural ambience, safe sound effects, and brief original dialogue when appropriate.
- Avoid copyrighted songs, recognizable lyrics, brand names unless the user explicitly gave them, subtitles, captions, watermarks, UI, and explanatory text overlays.
{root_reference_instruction}
- For all later segments, include enough visual memory in the prompt to keep style/characters/objects consistent without video input.
- Edges must form a directed graph with at least one branching choice and at least one shared target node if possible. Cycles are allowed, but do not make an infinite-only graph.
- Every node id must be clip1, clip2, clip3, ...
- node.option is the text shown as a choice button.
- edge.label is the choice text from source to target.

JSON schema:
{{
  "root_id": "clip1",
  "genre": "{genre_label}",
  "style_summary": "short visual style memory",
  "character_and_object_memory": "short reusable memory of characters and important objects",
  "nodes": [
    {{
      "id": "clip1",
      "option": "Introduction Scene",
      "title": "short title",
      "description": "one sentence summary",
      "segments": [
        {{"index": 0, "duration": {segment_seconds}, "prompt": "..."}}
      ]
    }}
  ],
  "edges": [
    {{"source": "clip1", "target": "clip2", "label": "..."}}
  ]
}}
""".strip()

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
            if not match:
                raise
            return json.loads(match.group(0))

    def _normalize_plan(self, payload: dict[str, Any], options: JobRequestOptions) -> StoryGraphPlan:
        root_id = payload.get("root_id") or "clip1"
        raw_nodes = payload.get("nodes") or []
        raw_edges = payload.get("edges") or []

        nodes: list[NodePlan] = []
        used_ids: set[str] = set()
        for i, raw_node in enumerate(raw_nodes[: self.settings.node_count], start=1):
            node_id = str(raw_node.get("id") or f"clip{i}")
            if not re.fullmatch(r"clip\d+", node_id) or node_id in used_ids:
                node_id = f"clip{i}"
                while node_id in used_ids:
                    node_id = f"clip{int(node_id[4:]) + 1}"
            used_ids.add(node_id)
            segments: list[SegmentPlan] = []
            raw_segments = raw_node.get("segments") or []
            for j in range(self.settings.segments_per_node):
                raw_segment = raw_segments[j] if j < len(raw_segments) else {}
                prompt = str(raw_segment.get("prompt") or self._fallback_prompt(node_id, j, options))
                segments.append(
                    SegmentPlan(
                        index=j,
                        prompt=prompt,
                        duration=self.settings.segment_seconds,
                    )
                )
            nodes.append(
                NodePlan(
                    id=node_id,
                    option=str(raw_node.get("option") or raw_node.get("title") or f"Scene {i}"),
                    title=str(raw_node.get("title") or raw_node.get("option") or f"Scene {i}"),
                    description=str(raw_node.get("description") or ""),
                    segments=segments,
                )
            )

        while len(nodes) < self.settings.node_count:
            i = len(nodes) + 1
            while f"clip{i}" in used_ids:
                i += 1
            used_ids.add(f"clip{i}")
            nodes.append(
                NodePlan(
                    id=f"clip{i}",
                    option=f"Scene {i}",
                    title=f"Scene {i}",
                    description=f"A generated fallback {GENRE_LABELS.get(options.genre, options.genre)} scene.",
                    segments=[
                        SegmentPlan(index=j, duration=self.settings.segment_seconds, prompt=self._fallback_prompt(f"clip{i}", j, options))
                        for j in range(self.settings.segments_per_node)
                    ],
                )
            )

        valid_ids = {node.id for node in nodes}
        edges: list[EdgePlan] = []
        for raw_edge in raw_edges:
            source = str(raw_edge.get("source") or "")
            target = str(raw_edge.get("target") or "")
            if source in valid_ids and target in valid_ids and source != target:
                edges.append(EdgePlan(source=source, target=target, label=str(raw_edge.get("label") or "Choose this path")))

        if not edges:
            for i in range(len(nodes) - 1):
                edges.append(EdgePlan(source=nodes[i].id, target=nodes[i + 1].id, label=nodes[i + 1].option))
            if len(nodes) >= 4:
                edges.append(EdgePlan(source=nodes[0].id, target=nodes[2].id, label=nodes[2].option))
                edges.append(EdgePlan(source=nodes[2].id, target=nodes[1].id, label="Loop back with a twist"))

        return StoryGraphPlan(
            root_id=root_id if root_id in valid_ids else nodes[0].id,
            genre=str(payload.get("genre") or GENRE_LABELS.get(options.genre, options.genre)),
            style_summary=str(payload.get("style_summary") or self._default_style(options)),
            character_and_object_memory=str(payload.get("character_and_object_memory") or self._default_memory(options)),
            nodes=nodes,
            edges=edges,
        )

    def _fallback_prompt(self, node_id: str, index: int, options: JobRequestOptions) -> str:
        genre_label = GENRE_LABELS.get(options.genre, options.genre.replace("_", " "))
        concept = options.input_text or "the uploaded video's setting and subjects"
        return (
            f"{genre_label} continuation for {node_id}, segment {index + 1}. Base concept: {concept}. "
            "Preserve a consistent visual style, characters, objects, lighting, and camera movement. "
            "Include native synchronized audio with natural ambience, safe sound effects, and brief original dialogue only if appropriate."
        )

    def _default_style(self, options: JobRequestOptions) -> str:
        if options.input_text:
            return f"Cinematic style based on the user's concept: {options.input_text[:240]}"
        return "Preserve the uploaded video's visual style, camera, lighting, and mood."

    def _default_memory(self, options: JobRequestOptions) -> str:
        if options.input_text:
            return "Keep the same main subjects, setting, and recurring objects introduced in the text concept."
        return "Keep the same main characters, animals, props, and setting inferred from the uploaded video."

    def _mock_plan(self, options: JobRequestOptions) -> StoryGraphPlan:
        duration = self.settings.segment_seconds
        genre_label = GENRE_LABELS.get(options.genre, options.genre.replace("_", " "))
        concept = options.input_text or "the uploaded source video"
        style = f"Cinematic {genre_label} style based on {concept}."
        memory = "Recurring characters, props, and location remain visually consistent across clips."

        def segs(node_id: str, action: str) -> list[SegmentPlan]:
            return [
                SegmentPlan(
                    index=i,
                    duration=duration,
                    prompt=(
                        f"{genre_label} scene for {node_id}, segment {i + 1}. {action} "
                        "Use native synchronized audio with safe ambience and simple sound effects."
                    ),
                )
                for i in range(self.settings.segments_per_node)
            ]

        if options.genre == "documentary":
            actions = [
                "Open with a clear visual hook and a narrator-style setup.",
                "Reveal the first surprising detail with close-up cinematic shots.",
                "Compare two possible explanations using visual examples.",
                "Escalate to the key insight with dramatic but accurate visuals.",
                "End with a memorable takeaway and a loop back to the opening question.",
            ]
        elif options.genre == "advertisement":
            actions = [
                "Show the problem in a visually engaging way.",
                "Introduce the product or idea as the elegant solution.",
                "Demonstrate the benefit through a surprising transformation.",
                "Show social proof or a bold visual payoff.",
                "End with a memorable brand-style closing beat without text overlays.",
            ]
        else:
            actions = [
                "Open with the main subject noticing that the world has become strangely cinematic.",
                "A small object or background detail unexpectedly takes control of the scene.",
                "The characters choose between two escalating paths.",
                "Two paths converge into one bigger reveal.",
                "The story loops back, but one important detail has changed.",
            ]

        nodes = [
            NodePlan(id=f"clip{i+1}", option=f"{genre_label.title()} Scene {i+1}", title=f"Scene {i+1}", description=actions[i], segments=segs(f"clip{i+1}", actions[i]))
            for i in range(min(self.settings.node_count, len(actions)))
        ]
        while len(nodes) < self.settings.node_count:
            i = len(nodes)
            action = f"Continue the {genre_label} story with a coherent new beat."
            nodes.append(NodePlan(id=f"clip{i+1}", option=f"Scene {i+1}", title=f"Scene {i+1}", description=action, segments=segs(f"clip{i+1}", action)))

        valid = {n.id for n in nodes}
        edges = [
            EdgePlan(source="clip1", target="clip2", label="Take the first path"),
            EdgePlan(source="clip1", target="clip3", label="Take the stranger path"),
            EdgePlan(source="clip2", target="clip4", label="Move toward the reveal"),
            EdgePlan(source="clip3", target="clip4", label="Converge on the reveal"),
            EdgePlan(source="clip4", target="clip5", label="Finish the arc"),
            EdgePlan(source="clip5", target="clip1", label="Loop back to the beginning"),
        ]
        edges = [e for e in edges if e.source in valid and e.target in valid]
        if not edges:
            edges = [EdgePlan(source=nodes[i].id, target=nodes[i + 1].id, label=nodes[i + 1].option) for i in range(len(nodes) - 1)]
        return StoryGraphPlan(root_id="clip1", genre=genre_label, style_summary=style, character_and_object_memory=memory, nodes=nodes, edges=edges)
