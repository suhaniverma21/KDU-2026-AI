"""Controls speaker playback, cancellation, and overlap prevention."""

from __future__ import annotations

import io
import queue
import threading
import wave
from typing import Optional

import pyaudio

from audio.tts import OpenAITTSClient
from config.settings import Settings


class PlaybackController:
    """Streams TTS audio to the speaker with interruption-safe non-blocking playback."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.is_interrupted = threading.Event()
        self.is_playing = threading.Event()
        self._playback_lock = threading.Lock()
        self._audio_queue: queue.Queue[bytes] = queue.Queue()
        self._playback_thread: Optional[threading.Thread] = None
        self._generation = 0
        self._tts_client = OpenAITTSClient(settings)
        self._last_error: Exception | None = None

    def play_text(self, text: str) -> None:
        """Start speaking text on a background thread after safely stopping prior playback."""
        with self._playback_lock:
            self.stop_playback()
            self.is_interrupted.clear()
            self._last_error = None
            self._generation += 1
            generation = self._generation
            self._playback_thread = threading.Thread(
                target=self._playback_worker,
                args=(text, generation),
                name=f"tts-playback-{generation}",
                daemon=True,
            )
            self._playback_thread.start()

    def stop_playback(self) -> None:
        """Immediately interrupt playback, flush queued audio, and stop the speaker stream."""
        self.is_interrupted.set()
        self._generation += 1
        self._flush_audio_queue()

        thread = self._playback_thread
        if thread and thread.is_alive():
            thread.join(timeout=1.0)
        self._playback_thread = None

    def _playback_worker(self, text: str, generation: int) -> None:
        """Fetch PCM bytes from TTS and write them to the speaker unless interrupted."""
        pa = pyaudio.PyAudio()
        stream = None
        self.is_playing.set()
        try:
            wav_bytes = self._tts_client.synthesize_wav_bytes(text)
            with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
                stream = pa.open(
                    format=pa.get_format_from_width(wav_file.getsampwidth()),
                    channels=wav_file.getnchannels(),
                    rate=wav_file.getframerate(),
                    output=True,
                    output_device_index=self._resolve_output_device_index(pa),
                    frames_per_buffer=self.settings.tts_stream_chunk_size,
                )

                while True:
                    if self._should_abort(generation):
                        break
                    chunk = wav_file.readframes(self.settings.tts_stream_chunk_size)
                    if not chunk:
                        break
                    self._audio_queue.put(chunk)
                    self._drain_audio_queue(stream, generation)
        except Exception as exc:
            self._last_error = exc
        finally:
            self._flush_audio_queue()
            self.is_playing.clear()
            if stream is not None:
                try:
                    stream.stop_stream()
                finally:
                    stream.close()
            pa.terminate()

    def wait_until_idle(self, timeout: float | None = None) -> bool:
        """Block until playback finishes or interruption fully stops the playback thread."""
        thread = self._playback_thread
        if not thread:
            return True
        thread.join(timeout=timeout)
        return not thread.is_alive()

    def raise_if_failed(self) -> None:
        """Raise any playback-thread error so the caller can surface it cleanly."""
        if self._last_error is not None:
            raise RuntimeError(f"TTS playback failed: {self._last_error}") from self._last_error

    def _drain_audio_queue(self, stream: pyaudio.Stream, generation: int) -> None:
        """Write queued PCM chunks to the speaker until queue is empty or interrupted."""
        while not self._audio_queue.empty():
            if self._should_abort(generation):
                return
            chunk = self._audio_queue.get_nowait()
            stream.write(chunk)

    def _flush_audio_queue(self) -> None:
        """Discard all queued audio so interrupted speech cannot continue playing."""
        while True:
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                return

    def _should_abort(self, generation: int) -> bool:
        """Detect whether current playback has been interrupted or superseded."""
        return self.is_interrupted.is_set() or generation != self._generation

    def _resolve_output_device_index(self, pa: pyaudio.PyAudio) -> int | None:
        """Prefer the configured headset name, then explicit index, then default output."""
        preferred_name = self.settings.preferred_output_device_name
        if preferred_name:
            preferred_name_lower = preferred_name.lower()
            for index in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(index)
                if int(info.get("maxOutputChannels", 0)) <= 0:
                    continue
                device_name = str(info.get("name", ""))
                if preferred_name_lower in device_name.lower():
                    return index
        return self.settings.tts_output_device_index

    @staticmethod
    def list_output_devices() -> list[dict[str, object]]:
        """Return available output devices so users can select the correct speaker."""
        pa = pyaudio.PyAudio()
        devices: list[dict[str, object]] = []
        try:
            for index in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(index)
                if int(info.get("maxOutputChannels", 0)) > 0:
                    devices.append(
                        {
                            "index": index,
                            "name": str(info.get("name", "")),
                            "max_output_channels": int(info.get("maxOutputChannels", 0)),
                            "default_sample_rate": float(info.get("defaultSampleRate", 0)),
                        }
                    )
        finally:
            pa.terminate()
        return devices
