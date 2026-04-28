"""Shared helper functions for the Content Accessibility Suite."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import shutil
from typing import BinaryIO


_PYDUB_BINARIES_CONFIGURED = False


def compute_md5(data: bytes) -> str:
    """Return the MD5 hash for raw file bytes."""
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def utc_timestamp() -> str:
    """Return an ISO 8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def read_file_bytes(file_obj: BinaryIO | bytes) -> bytes:
    """Return raw bytes from an upload-like object."""
    if isinstance(file_obj, bytes):
        return file_obj

    if hasattr(file_obj, "getvalue"):
        data = file_obj.getvalue()
        return data if isinstance(data, bytes) else bytes(data)

    if hasattr(file_obj, "seek"):
        file_obj.seek(0)
    data = file_obj.read()
    if hasattr(file_obj, "seek"):
        file_obj.seek(0)
    return data if isinstance(data, bytes) else bytes(data)


def extract_chat_response_text(response: object) -> str:
    """Return assistant text from a chat completion response."""
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""

    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", "") if message is not None else ""
    return content or ""


def extract_usage_tokens(response: object) -> tuple[int, int]:
    """Return prompt and completion token counts when available."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0

    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
    return int(prompt_tokens), int(completion_tokens)


def to_plain_english_error(exc: Exception, fallback_message: str) -> str:
    """Return a user-facing error message without leaking stack details."""
    message = str(exc).strip()
    return message if message else fallback_message


def configure_pydub_audio_binaries() -> bool:
    """Configure pydub to use installed FFmpeg binaries when available."""
    global _PYDUB_BINARIES_CONFIGURED

    if _PYDUB_BINARIES_CONFIGURED:
        return True

    ffmpeg_path = _resolve_audio_binary_path("ffmpeg")
    ffprobe_path = _resolve_audio_binary_path("ffprobe")
    if not ffmpeg_path or not ffprobe_path:
        return False

    from pydub import AudioSegment
    from pydub import utils as pydub_utils

    bin_dir = str(Path(ffmpeg_path).parent)
    current_path = os.environ.get("PATH", "")
    path_entries = current_path.split(os.pathsep) if current_path else []
    if bin_dir not in path_entries:
        os.environ["PATH"] = bin_dir + os.pathsep + current_path if current_path else bin_dir

    AudioSegment.converter = ffmpeg_path
    pydub_utils.get_prober_name = lambda: ffprobe_path
    _PYDUB_BINARIES_CONFIGURED = True
    return True


def _resolve_audio_binary_path(binary_name: str) -> str | None:
    """Find an FFmpeg-family binary through env vars, PATH, or common Windows paths."""
    env_var_name = f"{binary_name.upper()}_BINARY"
    env_value = os.environ.get(env_var_name)
    if env_value and Path(env_value).exists():
        return env_value

    which_path = shutil.which(binary_name)
    if which_path:
        return which_path

    candidates = _candidate_audio_binary_paths(binary_name)
    for candidate in candidates:
        try:
            if candidate.exists():
                return str(candidate)
        except OSError:
            continue

    return None


def _candidate_audio_binary_paths(binary_name: str) -> list[Path]:
    """Return likely Windows install paths for FFmpeg binaries."""
    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))

    candidates = [
        program_files / "FFmpeg" / "bin" / f"{binary_name}.exe",
        program_files_x86 / "FFmpeg" / "bin" / f"{binary_name}.exe",
        Path(r"C:\ffmpeg") / "bin" / f"{binary_name}.exe",
        local_app_data / "Microsoft" / "WinGet" / "Links" / f"{binary_name}.exe",
    ]

    winget_packages_dir = local_app_data / "Microsoft" / "WinGet" / "Packages"
    if winget_packages_dir.exists():
        try:
            for match in winget_packages_dir.glob(
                f"Gyan.FFmpeg_*/*/bin/{binary_name}.exe"
            ):
                candidates.append(match)
        except OSError:
            pass

    return candidates
