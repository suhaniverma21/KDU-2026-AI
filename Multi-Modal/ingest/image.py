"""Image ingestion for OCR-style text extraction through vision."""

from __future__ import annotations

from dataclasses import dataclass, field
import base64
from io import BytesIO
from typing import BinaryIO

from openai import OpenAI
from PIL import Image

from config import OPENAI_VISION_MODEL
from storage.cost_log import CostLogger, get_cost_logger
from utils import extract_chat_response_text, extract_usage_tokens, read_file_bytes

MAX_IMAGE_DIMENSION = 2048
NO_TEXT_SENTINEL = "NO_TEXT_FOUND"


@dataclass
class ImageIngestionResult:
    """Structured result returned from image text extraction."""

    transcript_text: str
    text_found: bool
    should_skip_chunking: bool
    normalized_format: str
    width: int
    height: int
    processing_notes: list[str] = field(default_factory=list)


def ingest_image(
    file_obj: BinaryIO | bytes,
    *,
    file_id: str,
    cost_logger: CostLogger | None = None,
    client: OpenAI | None = None,
    model: str = OPENAI_VISION_MODEL,
) -> ImageIngestionResult:
    """Open, normalize, and extract visible text from an image using vision."""
    image_bytes = read_file_bytes(file_obj)
    openai_client = client or OpenAI()
    logger = cost_logger or get_cost_logger()

    png_bytes, width, height, notes = _prepare_image(image_bytes)
    data_url = _to_data_url(png_bytes)

    try:
        response = openai_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You extract visible text from images. Return only the text that "
                        f"appears in the image. If there is no readable text, return exactly {NO_TEXT_SENTINEL}."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Extract all visible text from this image. Preserve line breaks "
                                f"when useful. If there is no readable text, return exactly {NO_TEXT_SENTINEL}."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                },
            ],
        )
    except Exception as exc:
        logger.log_api_call(
            file_id=file_id,
            operation_type="image_ocr",
            model=model,
            prompt_tokens=0,
            completion_tokens=0,
            success=False,
            error_message=str(exc),
        )
        raise

    prompt_tokens, completion_tokens = extract_usage_tokens(response)
    logger.log_api_call(
        file_id=file_id,
        operation_type="image_ocr",
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        success=True,
        error_message="",
    )

    transcript_text = extract_chat_response_text(response).strip()
    if transcript_text == NO_TEXT_SENTINEL:
        notes.append("No readable text detected in image.")
        return ImageIngestionResult(
            transcript_text="",
            text_found=False,
            should_skip_chunking=True,
            normalized_format="PNG",
            width=width,
            height=height,
            processing_notes=notes,
        )

    return ImageIngestionResult(
        transcript_text=transcript_text,
        text_found=bool(transcript_text),
        should_skip_chunking=not bool(transcript_text),
        normalized_format="PNG",
        width=width,
        height=height,
        processing_notes=notes,
    )


def _prepare_image(image_bytes: bytes) -> tuple[bytes, int, int, list[str]]:
    """Resize and convert an image to PNG bytes for vision input."""
    notes: list[str] = []
    with Image.open(BytesIO(image_bytes)) as image:
        working_image = image.copy()

    if working_image.mode not in ("RGB", "RGBA"):
        working_image = working_image.convert("RGB")
        notes.append("Converted image color mode for PNG normalization.")

    original_width, original_height = working_image.size
    longest_dimension = max(original_width, original_height)
    if longest_dimension > MAX_IMAGE_DIMENSION:
        working_image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION))
        notes.append(
            f"Resized image from {original_width}x{original_height} to "
            f"{working_image.width}x{working_image.height}."
        )

    png_buffer = BytesIO()
    working_image.save(png_buffer, format="PNG")
    notes.append("Normalized image to PNG before vision extraction.")
    return png_buffer.getvalue(), working_image.width, working_image.height, notes


def _to_data_url(image_bytes: bytes) -> str:
    """Encode image bytes as a PNG data URL for the vision request."""
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"
