"""Runs the Phase 1 microphone-to-agent-to-speaker conversation loop."""

from __future__ import annotations

import re
import threading

from agents.billing_agent import BillingAgent
from agents.triage_agent import TriageAgent
from audio.capture import MicrophoneRecorder
from audio.interruption import handle_interruption, listen_for_interruption
from audio.playback import PlaybackController
from audio.stt import WhisperTranscriber
from config.settings import Settings, get_settings


def transcribe_single_utterance(settings: Settings | None = None) -> str:
    """Capture one utterance from the microphone and return transcribed text."""
    resolved_settings = settings or get_settings()
    recorder = MicrophoneRecorder(resolved_settings)
    transcriber = WhisperTranscriber(resolved_settings)
    audio_buffer = recorder.record_until_silence()
    return transcriber.transcribe(audio_buffer)


def speak_text_non_blocking(
    text: str,
    settings: Settings | None = None,
) -> PlaybackController:
    """Start non-blocking TTS playback and return the active controller."""
    resolved_settings = settings or get_settings()
    playback = PlaybackController(resolved_settings)
    playback.play_text(text)
    return playback


def interrupt_and_return_to_recording(playback: PlaybackController) -> None:
    """Preempt active playback so the caller can resume microphone capture."""
    handle_interruption(playback)


class Phase1VoicePipeline:
    """Coordinates STT, triage, billing, TTS, and live interruption recovery."""

    _INTERRUPTION_ALLOWED_KEYWORDS = {
        "account",
        "actually",
        "amount",
        "april",
        "balance",
        "bill",
        "billing",
        "cancel",
        "charge",
        "charged",
        "correction",
        "date",
        "double",
        "duplicate",
        "incorrect",
        "invoice",
        "march",
        "payment",
        "refund",
        "subscription",
        "twice",
        "wrong",
    }
    _INTERRUPTION_REJECT_PHRASES = {
        "thank you",
        "thank you for watching",
        "thanks for watching",
        "you are welcome",
        "you're welcome",
    }

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.recorder = MicrophoneRecorder(self.settings)
        self.transcriber = WhisperTranscriber(self.settings)
        self.triage_agent = TriageAgent(self.settings)
        self.billing_agent = BillingAgent(self.settings)
        self.playback = PlaybackController(self.settings)
        self.interrupt_event = threading.Event()
        self.conversation_summary: str | None = None
        self.conversation_history: list[dict[str, str]] = []

    def run(self) -> dict:
        """Run the full Phase 1 pipeline, restarting from triage when interrupted."""
        audio_buffer = self.recorder.record_until_silence()
        transcript = self.transcriber.transcribe(audio_buffer)
        return self._process_transcript(transcript)

    def _process_transcript(self, transcript: str) -> dict:
        """Send transcripts through triage and billing until playback completes cleanly."""
        current_transcript = transcript
        restart_count = 0

        while True:
            triage_handoff = self.triage_agent.run(
                transcribed_text=current_transcript,
                conversation_history=self.conversation_history,
                conversation_summary=self.conversation_summary,
            )
            billing_result = self.billing_agent.run(
                handoff_payload=triage_handoff,
                playback=self.playback,
            )
            self.conversation_summary = billing_result.get("conversation_summary")
            self.conversation_history = billing_result["conversation_history"]

            interrupted_audio = self._monitor_for_interruption()
            if interrupted_audio is None:
                return billing_result

            interrupting_text = self.transcriber.transcribe(interrupted_audio).strip()
            if not self._is_valid_interruption(interrupting_text):
                print(
                    "[Phase1] Ignoring interruption transcript that does not look like"
                    f" a billing follow-up: {interrupting_text!r}"
                )
                return billing_result

            restart_count += 1
            if restart_count > self.settings.voice_interrupt_max_restarts:
                return billing_result

            current_transcript = interrupting_text

    def _monitor_for_interruption(self):
        """Listen in the background while TTS is active and capture interruption speech."""
        # Interruption listening is optional because open-speaker playback can leak back
        # into the microphone and create false "user" interruptions. We keep it off by
        # default so normal end-to-end voice playback is reliable without headphones.
        if not self.settings.voice_interrupt_enabled:
            self.playback.wait_until_idle(
                timeout=self.settings.playback_wait_timeout_seconds
            )
            self.playback.raise_if_failed()
            return None

        self.interrupt_event.clear()
        stop_listening_event = threading.Event()
        interruption_result: dict = {"audio_buffer": None}
        listener_thread = threading.Thread(
            target=listen_for_interruption,
            args=(
                self.recorder,
                self.playback,
                self.interrupt_event,
                stop_listening_event,
                interruption_result,
            ),
            name="phase1-interrupt-listener",
            daemon=True,
        )
        listener_thread.start()

        self.playback.wait_until_idle(timeout=self.settings.playback_wait_timeout_seconds)
        self.playback.raise_if_failed()
        stop_listening_event.set()
        listener_thread.join(timeout=1.0)

        if self.interrupt_event.is_set():
            return interruption_result.get("audio_buffer")

        return None

    def _is_valid_interruption(self, transcript: str) -> bool:
        """Ignore empty, tiny, or irrelevant transcripts so noise does not restart the loop."""
        normalized = transcript.strip()
        if not normalized:
            return False
        if len(normalized) < self.settings.voice_interrupt_min_chars:
            return False
        lowered = normalized.lower()
        if lowered in self._INTERRUPTION_REJECT_PHRASES:
            return False

        words = {
            token
            for token in re.findall(r"[a-zA-Z]+", lowered)
            if len(token) >= 3
        }
        if not words.intersection(self._INTERRUPTION_ALLOWED_KEYWORDS):
            return False
        return True


def run_phase1_pipeline(settings: Settings | None = None) -> dict:
    """Run mic -> Whisper -> Triage -> Billing -> TTS with interruption support."""
    pipeline = Phase1VoicePipeline(settings)
    return pipeline.run()


# Handoff state passed between agents:
# - `intent` from the Triage Agent so Billing receives the resolved route.
# - `entities` such as `account_id` and `issue` extracted during triage.
# - `original_message` so Billing can see the exact latest user request.
# - `conversation_summary` so older turns are preserved without replaying them all.
# - the last 6 turns of `conversation_history` so Billing keeps recent continuity.
#
# Audio buffer flushing:
# - `PlaybackController.stop_playback()` sets the interruption flag immediately.
# - It flushes all queued PCM frames through `_flush_audio_queue()`.
# - The playback thread checks the flag/generation and exits before writing more audio.
#
# Preventing overlapping recording and playback:
# - TTS output always runs on a single `PlaybackController` thread.
# - During TTS, only one background interruption listener owns the microphone stream.
# - When speech crosses the threshold, the listener sets `interrupt_event` and calls
#   `stop_playback()` before finishing the new utterance capture.
# - The main pipeline does not start a second recording pass until that listener returns.
