"""Wraps text-to-speech generation and audio output formatting."""

from io import BytesIO

from config.settings import Settings
from services.openai_client import get_openai_client


class OpenAITTSClient:
    """Fetches audio from OpenAI's TTS API for speaker playback."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def synthesize_wav_bytes(self, text: str) -> bytes:
        """Return WAV audio bytes for the given text using the configured TTS model and voice."""
        client = get_openai_client()
        with client.audio.speech.with_streaming_response.create(
            model=self.settings.default_tts_model,
            voice=self.settings.default_tts_voice,
            input=text,
            response_format="wav",
        ) as response:
            wav_buffer = BytesIO()
            for chunk in response.iter_bytes(chunk_size=self.settings.tts_stream_chunk_size):
                wav_buffer.write(chunk)
            return wav_buffer.getvalue()
