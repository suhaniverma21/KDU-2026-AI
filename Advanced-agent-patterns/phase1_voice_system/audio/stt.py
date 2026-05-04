"""Wraps Whisper transcription calls for buffered speech-to-text conversion."""

from audio.buffer import InMemoryAudioBuffer
from config.settings import Settings
from services.openai_client import get_openai_client


class WhisperTranscriber:
    """Transcribe buffered in-memory audio using the OpenAI Whisper API."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def transcribe(self, audio_buffer: InMemoryAudioBuffer) -> str:
        """Upload an in-memory WAV buffer to Whisper and return transcript text."""
        client = get_openai_client()
        wav_buffer = audio_buffer.to_wav_bytesio()
        transcript = client.audio.transcriptions.create(
            model=self.settings.default_stt_model,
            file=wav_buffer,
        )
        return transcript.text.strip()
