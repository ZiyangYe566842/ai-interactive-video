from pathlib import Path
import hashlib

from .base import VideoGenerationProvider
from ..video_utils import generate_mock_video
from ...config import Settings
from ...models import SegmentPlan, StoryGraphPlan


class MockVideoProvider(VideoGenerationProvider):
    def __init__(self, settings: Settings):
        self.settings = settings

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
        label = f"{graph.genre or 'story'} · {node_id} segment {segment.index + 1}"
        seed = int.from_bytes(hashlib.sha256(f"{node_id}:{segment.index}:{graph.genre}".encode()).digest()[:4], "big")
        generate_mock_video(output_path, segment.duration, label=label, seed=seed)
        segment.filename = output_path.name
        segment.generated_url = None
        return segment
