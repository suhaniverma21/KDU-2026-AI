"""Audio ingestion with silence-aware segmentation and local Whisper transcription."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
import importlib
import logging
from pathlib import Path
import tempfile
from typing import BinaryIO

from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError
from pydub.silence import detect_silence

from config import LOCAL_WHISPER_MODEL
from utils import configure_pydub_audio_binaries, read_file_bytes

LOGGER = logging.getLogger(__name__)

SEGMENT_TARGET_MS = 10 * 60 * 1000
SPLIT_SEARCH_WINDOW_MS = 60 * 1000
MIN_SILENCE_LEN_MS = 700
MIN_TRANSCRIPT_LENGTH = 20

_WHISPER_PIPELINE = None
_WHISPER_LOAD_LOGGED = False


@dataclass
class AudioSegmentMetadata:
    """Metadata for a single transcribed audio segment."""

    segment_index: int
    start_ms: int
    end_ms: int
    duration_ms: int
    transcript_text: str


@dataclass
class AudioIngestionResult:
    """Structured result returned from audio ingestion."""

    transcript_text: str
    segment_metadata: list[AudioSegmentMetadata]
    processing_notes: list[str] = field(default_factory=list)
    error_message: str = ""


def ingest_audio(
    file_obj: BinaryIO | bytes,
    *,
    filename: str,
    model_name: str = LOCAL_WHISPER_MODEL,
) -> AudioIngestionResult:
    """Load, segment, and transcribe audio with a local Whisper pipeline."""
    configure_pydub_audio_binaries()
    audio_bytes = read_file_bytes(file_obj)
    format_hint = Path(filename).suffix.lower().lstrip(".") or None

    try:
        audio = AudioSegment.from_file(BytesIO(audio_bytes), format=format_hint)
    except CouldntDecodeError as exc:
        raise ValueError("File is corrupted or unreadable") from exc
    except Exception as exc:
        raise ValueError("File is corrupted or unreadable") from exc

    processing_notes: list[str] = []
    boundaries = _compute_segment_boundaries(audio)
    segments = _slice_segments(audio, boundaries)

    if len(segments) > 1:
        processing_notes.append(
            f"Audio split into {len(segments)} segments near silence around 10-minute boundaries."
        )
    else:
        processing_notes.append("Audio processed as a single segment.")

    whisper = _get_whisper_pipeline(model_name=model_name, processing_notes=processing_notes)

    segment_metadata: list[AudioSegmentMetadata] = []
    transcript_parts: list[str] = []

    with tempfile.TemporaryDirectory() as temp_dir:
        for index, (start_ms, end_ms, segment_audio) in enumerate(segments):
            temp_path = Path(temp_dir) / f"segment_{index}.wav"
            segment_audio.export(temp_path, format="wav")

            transcript_text = _transcribe_segment(whisper, str(temp_path)).strip()
            segment_metadata.append(
                AudioSegmentMetadata(
                    segment_index=index,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    duration_ms=end_ms - start_ms,
                    transcript_text=transcript_text,
                )
            )
            if transcript_text:
                transcript_parts.append(transcript_text)

    full_transcript = " ".join(part for part in transcript_parts if part).strip()
    if len(full_transcript) < MIN_TRANSCRIPT_LENGTH:
        raise ValueError("No speech was detected in the audio.")

    return AudioIngestionResult(
        transcript_text=full_transcript,
        segment_metadata=segment_metadata,
        processing_notes=processing_notes,
        error_message="",
    )


def _compute_segment_boundaries(audio: AudioSegment) -> list[tuple[int, int]]:
    """Compute start/end boundaries by searching for silence near each target split."""
    duration_ms = len(audio)
    boundaries: list[tuple[int, int]] = []
    start_ms = 0

    while start_ms < duration_ms:
        target_end = start_ms + SEGMENT_TARGET_MS
        if target_end >= duration_ms:
            boundaries.append((start_ms, duration_ms))
            break

        split_ms = _find_nearest_silence(audio, target_end)
        if split_ms <= start_ms:
            split_ms = min(target_end, duration_ms)

        boundaries.append((start_ms, split_ms))
        start_ms = split_ms

    return boundaries


def _find_nearest_silence(audio: AudioSegment, target_ms: int) -> int:
    """Find the silence midpoint nearest the target split position."""
    window_start = max(0, target_ms - SPLIT_SEARCH_WINDOW_MS)
    window_end = min(len(audio), target_ms + SPLIT_SEARCH_WINDOW_MS)
    window_audio = audio[window_start:window_end]

    silence_thresh = window_audio.dBFS - 16 if window_audio.dBFS != float("-inf") else -50
    silence_ranges = detect_silence(
        window_audio,
        min_silence_len=MIN_SILENCE_LEN_MS,
        silence_thresh=silence_thresh,
    )
    if not silence_ranges:
        return target_ms

    midpoint_candidates = [
        window_start + int((silence_start + silence_end) / 2)
        for silence_start, silence_end in silence_ranges
    ]
    return min(midpoint_candidates, key=lambda candidate: abs(candidate - target_ms))


def _slice_segments(audio: AudioSegment, boundaries: list[tuple[int, int]]) -> list[tuple[int, int, AudioSegment]]:
    """Slice an audio object into concrete segment objects."""
    segments: list[tuple[int, int, AudioSegment]] = []
    for start_ms, end_ms in boundaries:
        segment_audio = audio[start_ms:end_ms]
        segments.append((start_ms, end_ms, segment_audio))
    return segments


def _get_whisper_pipeline(*, model_name: str, processing_notes: list[str]):
    """Load or reuse a local Whisper pipeline."""
    global _WHISPER_PIPELINE
    global _WHISPER_LOAD_LOGGED

    if _WHISPER_PIPELINE is not None:
        return _WHISPER_PIPELINE

    if not _WHISPER_LOAD_LOGGED:
        note = (
            "Loading local Whisper model. The first run may download about 140MB, "
            "which can take a moment."
        )
        processing_notes.append(note)
        LOGGER.info(note)
        _WHISPER_LOAD_LOGGED = True

    try:
        transformers_module = importlib.import_module("transformers")
        hf_pipeline = getattr(transformers_module, "pipeline")
    except Exception as exc:
        raise ValueError(
            "Audio transcription dependencies are not fully available. "
            "Install the required Transformers runtime packages and try again."
        ) from exc

    _WHISPER_PIPELINE = hf_pipeline(
        task="automatic-speech-recognition",
        model=model_name,
    )
    return _WHISPER_PIPELINE


def _transcribe_segment(whisper_pipeline, segment_path: str) -> str:
    """Run local Whisper on a single audio segment file."""
    result = whisper_pipeline(segment_path, return_timestamps=True)
    if isinstance(result, dict):
        return str(result.get("text", "")).strip()
    return str(result).strip()
