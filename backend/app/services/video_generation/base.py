from abc import ABC, abstractmethod
from pathlib import Path

from ...models import SegmentPlan, StoryGraphPlan


class VideoGenerationProvider(ABC):
    @abstractmethod
    def prepare_reference(self, source_video: Path | None) -> str | None:
        """Return a public URL for a source/reference video, or None.

        Google Veo path intentionally returns None because this app uses Veo as text-to-video only.
        """

    @abstractmethod
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
        """Generate one video segment and save it to output_path."""
