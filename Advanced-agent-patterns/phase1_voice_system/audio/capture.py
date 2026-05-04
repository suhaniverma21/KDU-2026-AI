"""Captures microphone audio into in-memory buffers using raw PCM chunks."""

from __future__ import annotations

import queue
import sys
import threading
from collections import deque

import numpy as np
import sounddevice as sd

from audio.buffer import InMemoryAudioBuffer
from audio.vad import calculate_rms, required_silent_chunks
from config.settings import Settings


class MicrophoneRecorder:
    """Capture microphone input to an in-memory buffer until silence is detected."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue()

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        """Receive raw audio blocks from sounddevice and queue them safely."""
        del frames, time_info
        if status:
            print(f"Audio callback status: {status}", file=sys.stderr)
        self._audio_queue.put(indata.copy())

    def record_until_silence(self) -> InMemoryAudioBuffer:
        """Record one utterance into memory using RMS-based silence detection."""
        self._clear_audio_queue()
        buffer = InMemoryAudioBuffer(
            sample_rate=self.settings.voice_sample_rate,
            channels=self.settings.voice_channels,
        )
        heard_speech = False
        silent_chunks = 0
        max_chunks = int(
            (self.settings.voice_max_record_seconds * self.settings.voice_sample_rate)
            / self.settings.voice_chunk_size
        )
        silence_limit = required_silent_chunks(
            sample_rate=self.settings.voice_sample_rate,
            chunk_size=self.settings.voice_chunk_size,
            silence_duration_seconds=self.settings.voice_silence_duration_seconds,
        )

        with sd.InputStream(
            samplerate=self.settings.voice_sample_rate,
            channels=self.settings.voice_channels,
            dtype=self.settings.voice_dtype,
            blocksize=self.settings.voice_chunk_size,
            device=self._resolve_input_device(),
            callback=self._audio_callback,
        ):
            for _ in range(max_chunks):
                chunk = self._audio_queue.get()
                rms = calculate_rms(chunk)
                buffer.append(chunk.tobytes())

                if rms >= self.settings.voice_silence_threshold:
                    heard_speech = True
                    silent_chunks = 0
                elif heard_speech:
                    silent_chunks += 1

                if heard_speech and silent_chunks >= silence_limit:
                    break

        if buffer.is_empty():
            raise RuntimeError("No audio was captured from the microphone.")

        return buffer

    def record_interrupting_utterance(
        self,
        interrupt_event: threading.Event,
        playback_stop_callback,
        stop_listening_event: threading.Event,
    ) -> InMemoryAudioBuffer:
        """Capture stable interrupting speech, then interrupt TTS and record to silence."""
        self._clear_audio_queue()
        buffer = InMemoryAudioBuffer(
            sample_rate=self.settings.voice_sample_rate,
            channels=self.settings.voice_channels,
        )
        heard_speech = False
        silent_chunks = 0
        consecutive_speech_chunks = 0
        pending_chunks: deque[np.ndarray] = deque()
        max_chunks = int(
            (self.settings.voice_max_record_seconds * self.settings.voice_sample_rate)
            / self.settings.voice_chunk_size
        )
        silence_limit = required_silent_chunks(
            sample_rate=self.settings.voice_sample_rate,
            chunk_size=self.settings.voice_chunk_size,
            silence_duration_seconds=self.settings.voice_silence_duration_seconds,
        )

        with sd.InputStream(
            samplerate=self.settings.voice_sample_rate,
            channels=self.settings.voice_channels,
            dtype=self.settings.voice_dtype,
            blocksize=self.settings.voice_chunk_size,
            device=self._resolve_input_device(),
            callback=self._audio_callback,
        ):
            for _ in range(max_chunks):
                if stop_listening_event.is_set() and not heard_speech:
                    raise RuntimeError("Playback ended before any interrupting speech was captured.")

                try:
                    chunk = self._audio_queue.get(timeout=0.1)
                except queue.Empty:
                    if stop_listening_event.is_set() and not heard_speech:
                        raise RuntimeError(
                            "Playback ended before any interrupting speech was captured."
                        )
                    continue
                rms = calculate_rms(chunk)

                if not heard_speech:
                    if rms < self.settings.voice_silence_threshold:
                        consecutive_speech_chunks = 0
                        pending_chunks.clear()
                        continue

                    consecutive_speech_chunks += 1
                    pending_chunks.append(chunk.copy())
                    if (
                        consecutive_speech_chunks
                        < self.settings.voice_interrupt_activation_chunks
                    ):
                        continue

                    heard_speech = True
                    interrupt_event.set()
                    playback_stop_callback()
                    while pending_chunks:
                        buffer.append(pending_chunks.popleft().tobytes())
                    silent_chunks = 0
                    continue

                buffer.append(chunk.tobytes())

                if rms >= self.settings.voice_silence_threshold:
                    silent_chunks = 0
                else:
                    silent_chunks += 1

                if heard_speech and silent_chunks >= silence_limit:
                    break

        if buffer.is_empty():
            raise RuntimeError("No interrupting audio was captured from the microphone.")

        return buffer

    def _clear_audio_queue(self) -> None:
        """Discard stale microphone frames before starting a new capture window."""
        while True:
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                return

    def _resolve_input_device(self) -> int | None:
        """Prefer the configured headset name, then explicit index, then default input."""
        preferred_name = self.settings.preferred_input_device_name
        if preferred_name:
            preferred_name_lower = preferred_name.lower()
            for index, device in enumerate(sd.query_devices()):
                if int(device["max_input_channels"]) <= 0:
                    continue
                device_name = str(device["name"])
                if preferred_name_lower in device_name.lower():
                    return index
        return self.settings.voice_input_device_index

    @staticmethod
    def list_input_devices() -> list[dict[str, object]]:
        """Return available input devices so users can select the correct microphone."""
        devices: list[dict[str, object]] = []
        for index, device in enumerate(sd.query_devices()):
            if int(device["max_input_channels"]) > 0:
                devices.append(
                    {
                        "index": index,
                        "name": str(device["name"]),
                        "max_input_channels": int(device["max_input_channels"]),
                        "default_samplerate": float(device["default_samplerate"]),
                    }
                )
        return devices
