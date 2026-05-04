"""Coordinates interruption events between active playback and fresh user speech."""

import threading

from audio.capture import MicrophoneRecorder
from audio.playback import PlaybackController


def handle_interruption(playback: PlaybackController) -> None:
    """Stop TTS immediately, flush pending audio, and return control to recording."""
    playback.stop_playback()


def listen_for_interruption(
    recorder: MicrophoneRecorder,
    playback: PlaybackController,
    interrupt_event: threading.Event,
    stop_listening_event: threading.Event,
    result_holder: dict,
) -> None:
    """Monitor microphone input during playback and capture the interrupting utterance."""
    try:
        result_holder["audio_buffer"] = recorder.record_interrupting_utterance(
            interrupt_event=interrupt_event,
            playback_stop_callback=playback.stop_playback,
            stop_listening_event=stop_listening_event,
        )
    except RuntimeError:
        result_holder["audio_buffer"] = None
