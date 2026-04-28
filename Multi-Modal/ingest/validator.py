"""Validation and deduplication helpers for uploaded files."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import mimetypes
from pathlib import Path
from typing import BinaryIO

from PIL import Image
import pdfplumber
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

from config import AUDIO_DURATION_LIMIT_MINUTES, FILE_SIZE_LIMITS_MB
from storage.filestore import FileRecord, FileStore, get_file_store
from utils import compute_md5, configure_pydub_audio_binaries, read_file_bytes

PDF_MIME_TYPES = {"application/pdf"}
IMAGE_MIME_TYPES = {
    "image/bmp",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
}
AUDIO_MIME_TYPES = {
    "audio/aac",
    "audio/flac",
    "audio/m4a",
    "audio/mp3",
    "audio/mp4",
    "audio/mpeg",
    "audio/ogg",
    "audio/wav",
    "audio/webm",
    "audio/x-m4a",
    "audio/x-wav",
}

SOURCE_TYPE_MIME_MAP = {
    "pdf": PDF_MIME_TYPES,
    "image": IMAGE_MIME_TYPES,
    "audio": AUDIO_MIME_TYPES,
}

EXTENSION_SOURCE_MAP = {
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".bmp": "image",
    ".tif": "image",
    ".tiff": "image",
    ".webp": "image",
    ".gif": "image",
    ".mp3": "audio",
    ".wav": "audio",
    ".m4a": "audio",
    ".ogg": "audio",
    ".flac": "audio",
    ".aac": "audio",
    ".mp4": "audio",
    ".webm": "audio",
}


@dataclass
class ValidationResult:
    """Normalized validation result returned before ingestion begins."""

    is_valid: bool
    source_type: str | None
    mime_type: str | None
    md5: str | None
    error_message: str
    cached_record: FileRecord | None


def validate_upload(
    file_obj: BinaryIO | bytes,
    *,
    filename: str,
    mime_type: str | None = None,
    file_store: FileStore | None = None,
) -> ValidationResult:
    """Validate an uploaded file and return any cached result when duplicated."""
    file_bytes = read_file_bytes(file_obj)
    if not file_bytes:
        return ValidationResult(
            is_valid=False,
            source_type=None,
            mime_type=None,
            md5=None,
            error_message="No file received",
            cached_record=None,
        )

    extension = Path(filename).suffix.lower()
    source_type = EXTENSION_SOURCE_MAP.get(extension)
    if source_type is None:
        return ValidationResult(
            is_valid=False,
            source_type=None,
            mime_type=None,
            md5=None,
            error_message="Unsupported file type",
            cached_record=None,
        )

    resolved_mime_type = _resolve_mime_type(filename, mime_type)
    if not _is_extension_mime_compatible(source_type, resolved_mime_type):
        return ValidationResult(
            is_valid=False,
            source_type=source_type,
            mime_type=resolved_mime_type,
            md5=None,
            error_message="File type mismatch",
            cached_record=None,
        )

    size_limit_mb = FILE_SIZE_LIMITS_MB[source_type]
    file_size_mb = len(file_bytes) / (1024 * 1024)
    if file_size_mb > size_limit_mb:
        return ValidationResult(
            is_valid=False,
            source_type=source_type,
            mime_type=resolved_mime_type,
            md5=None,
            error_message=f"File exceeds size limit of {size_limit_mb}MB",
            cached_record=None,
        )

    try:
        _verify_file_can_open(
            file_bytes=file_bytes,
            filename=filename,
            source_type=source_type,
        )
    except ValueError as exc:
        return ValidationResult(
            is_valid=False,
            source_type=source_type,
            mime_type=resolved_mime_type,
            md5=None,
            error_message=str(exc),
            cached_record=None,
        )

    md5 = compute_md5(file_bytes)
    store = file_store or get_file_store()
    cached_record = store.get_by_md5(md5)
    if cached_record is not None:
        return ValidationResult(
            is_valid=True,
            source_type=source_type,
            mime_type=resolved_mime_type,
            md5=md5,
            error_message="",
            cached_record=cached_record,
        )

    return ValidationResult(
        is_valid=True,
        source_type=source_type,
        mime_type=resolved_mime_type,
        md5=md5,
        error_message="",
        cached_record=None,
    )


def _resolve_mime_type(filename: str, mime_type: str | None) -> str:
    """Return the best available MIME type for validation."""
    if mime_type:
        return mime_type.lower()
    guessed_mime, _ = mimetypes.guess_type(filename)
    return (guessed_mime or "").lower()


def _is_extension_mime_compatible(source_type: str, mime_type: str) -> bool:
    """Check whether the resolved MIME type matches the file category."""
    if not mime_type:
        return False
    return mime_type in SOURCE_TYPE_MIME_MAP[source_type]


def _verify_file_can_open(*, file_bytes: bytes, filename: str, source_type: str) -> None:
    """Verify that the file opens successfully and meets type-specific rules."""
    try:
        if source_type == "pdf":
            _verify_pdf(file_bytes)
        elif source_type == "image":
            _verify_image(file_bytes)
        elif source_type == "audio":
            _verify_audio(file_bytes, filename)
        else:
            raise ValueError("Unsupported file type")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("File is corrupted or unreadable") from exc


def _verify_pdf(file_bytes: bytes) -> None:
    """Verify that a PDF can be opened and parsed."""
    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        _ = len(pdf.pages)


def _verify_image(file_bytes: bytes) -> None:
    """Verify that an image can be opened safely."""
    with Image.open(BytesIO(file_bytes)) as image:
        image.verify()


def _verify_audio(file_bytes: bytes, filename: str) -> None:
    """Verify that an audio file opens and stays within the duration cap."""
    configure_pydub_audio_binaries()
    extension = Path(filename).suffix.lower().lstrip(".")
    format_hint = extension or None
    try:
        audio = AudioSegment.from_file(BytesIO(file_bytes), format=format_hint)
    except CouldntDecodeError as exc:
        raise ValueError("File is corrupted or unreadable") from exc

    duration_minutes = len(audio) / 1000 / 60
    if duration_minutes > AUDIO_DURATION_LIMIT_MINUTES:
        raise ValueError(
            f"Audio file exceeds {AUDIO_DURATION_LIMIT_MINUTES} minute limit"
        )
