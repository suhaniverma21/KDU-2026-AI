"""Manages input and output audio buffers without persisting raw audio to disk."""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass, field


@dataclass(slots=True)
class InMemoryAudioBuffer:
    """Stores raw PCM chunks in memory and exposes WAV conversion helpers."""

    sample_rate: int
    channels: int
    sample_width_bytes: int = 2
    _chunks: list[bytes] = field(default_factory=list)

    def append(self, chunk: bytes) -> None:
        """Append a raw PCM chunk to the in-memory buffer."""
        self._chunks.append(chunk)

    def clear(self) -> None:
        """Reset the in-memory buffer after a completed utterance."""
        self._chunks.clear()

    def is_empty(self) -> bool:
        """Return whether the buffer currently has any audio data."""
        return not self._chunks

    def to_pcm_bytes(self) -> bytes:
        """Concatenate all buffered chunks into a single PCM byte string."""
        return b"".join(self._chunks)

    def to_wav_bytesio(self, filename: str = "utterance.wav") -> io.BytesIO:
        """Wrap buffered PCM bytes in an in-memory WAV file for upload."""
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(self.sample_width_bytes)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(self.to_pcm_bytes())

        wav_buffer.seek(0)
        wav_buffer.name = filename
        return wav_buffer
