from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI Interactive Video"
    data_dir: Path = Path("./data")
    frontend_origin: str = "http://localhost:5173"

    # A fresh checkout must run without provider credentials or paid API calls.
    video_provider: Literal["mock", "fal", "veo", "veo_lite", "veo_fast", "veo_standard"] = "mock"

    # Google Gemini API: used for video understanding / text planning and for Veo generation.
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash"
    gemini_file_poll_interval_seconds: int = Field(default=5, ge=1, le=60)
    gemini_file_processing_timeout_seconds: int = Field(default=600, ge=30, le=3600)

    # Google Veo 3.1 generation settings.
    # veo_model_id is kept for backward compatibility; explicit Lite/Fast/Standard IDs are preferred.
    veo_model_id: str = "veo-3.1-lite-generate-preview"
    veo_lite_model_id: str = "veo-3.1-lite-generate-preview"
    veo_fast_model_id: str = "veo-3.1-fast-generate-preview"
    veo_standard_model_id: str = "veo-3.1-generate-preview"
    veo_duration_seconds: int = Field(default=8, ge=4, le=8)  # longest supported single generation for Veo 3.1
    veo_resolution: str = "1080p"
    veo_poll_interval_seconds: int = Field(default=10, ge=2, le=60)
    veo_timeout_seconds: int = Field(default=900, ge=60, le=7200)
    # Retries for transient Veo operation failures such as Google internal server errors.
    # Total attempts = 1 + veo_max_retries.
    veo_max_retries: int = Field(default=2, ge=0, le=10)
    veo_retry_initial_delay_seconds: int = Field(default=60, ge=5, le=1800)
    veo_retry_backoff_multiplier: float = Field(default=2.0, ge=1.0, le=10.0)

    # fal.ai / Seedance settings kept as an alternate provider.
    fal_key: str | None = None
    fal_text_model_id: str = "bytedance/seedance-2.0/text-to-video"
    fal_reference_model_id: str = "bytedance/seedance-2.0/reference-to-video"
    fal_start_timeout_seconds: int = Field(default=300, ge=30, le=3600)
    fal_client_timeout_seconds: int = Field(default=1800, ge=60, le=7200)

    # Default graph shape. clip_length_seconds from the UI controls segments_per_node dynamically.
    node_count: int = Field(default=5, ge=2, le=12)
    segments_per_node: int = Field(default=2, ge=1, le=16)
    segment_seconds: int = Field(default=8, ge=4, le=15)
    video_resolution: str = "720p"
    video_aspect_ratio: str = "16:9"
    generate_audio: bool = True

    # Reference input settings for Seedance only. Veo path never sends the user's uploaded video to Veo.
    reference_clip_seconds: int = Field(default=10, ge=2, le=15)
    use_reference_for_root_first_segment: bool = True
    use_reference_for_all_node_first_segments: bool = False
    fallback_to_text_on_reference_error: bool = True

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "jobs").mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
