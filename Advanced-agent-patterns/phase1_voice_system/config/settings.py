"""Defines strongly typed application settings sourced from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings loaded from environment variables."""

    openai_api_key: str
    default_llm_model: str = "gpt-4o-mini"
    default_stt_model: str = "whisper-1"
    default_tts_model: str = "tts-1"
    default_tts_voice: str = "alloy"
    voice_sample_rate: int = 16_000
    voice_chunk_size: int = 1_024
    voice_silence_threshold: float = 250.0
    voice_silence_duration_seconds: float = 1.2
    voice_max_record_seconds: float = 20.0
    voice_interrupt_enabled: bool = False
    voice_interrupt_activation_chunks: int = 3
    voice_interrupt_min_chars: int = 12
    voice_interrupt_max_restarts: int = 2
    playback_wait_timeout_seconds: float = 20.0
    preferred_input_device_name: str | None = "Logi USB Headset"
    preferred_output_device_name: str | None = "Logi USB Headset"
    voice_input_device_index: int | None = None
    tts_output_device_index: int | None = None
    voice_channels: int = 1
    voice_dtype: str = "int16"
    tts_sample_rate: int = 24_000
    tts_channels: int = 1
    tts_sample_width_bytes: int = 2
    tts_stream_chunk_size: int = 4_096

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance for the current process."""
    return Settings()
