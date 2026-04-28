"""PDF ingestion with page-level routing to free extraction or vision fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
import base64
from io import BytesIO
from typing import BinaryIO

from openai import OpenAI
from pdf2image import convert_from_bytes
import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect
from PIL import Image

from config import OPENAI_VISION_MODEL
from storage.cost_log import CostLogger, get_cost_logger
from utils import extract_chat_response_text, extract_usage_tokens, read_file_bytes

MAX_IMAGE_DIMENSION = 2048
NO_TEXT_SENTINEL = "NO_TEXT_FOUND"
MIN_SUMMARIZATION_TEXT_LENGTH = 100


@dataclass
class PdfIngestionResult:
    """Structured result returned from PDF ingestion."""

    transcript_text: str
    failed_pages: list[int]
    is_partial: bool
    partial_notes: list[str]
    should_skip_summary: bool
    pages_processed: int
    vision_pages: list[int] = field(default_factory=list)


def ingest_pdf(
    file_obj: BinaryIO | bytes,
    *,
    file_id: str,
    cost_logger: CostLogger | None = None,
    client: OpenAI | None = None,
    model: str = OPENAI_VISION_MODEL,
) -> PdfIngestionResult:
    """Extract text from a PDF using direct extraction first and vision when needed."""
    pdf_bytes = read_file_bytes(file_obj)
    logger = cost_logger or get_cost_logger()
    openai_client = client or OpenAI()

    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            return _process_pdf(
                pdf_bytes=pdf_bytes,
                pdf=pdf,
                file_id=file_id,
                cost_logger=logger,
                client=openai_client,
                model=model,
            )
    except PDFPasswordIncorrect as exc:
        raise ValueError("Encrypted PDF files are not supported.") from exc
    except Exception as exc:
        raise ValueError("File is corrupted or unreadable") from exc


def _process_pdf(
    *,
    pdf_bytes: bytes,
    pdf: pdfplumber.PDF,
    file_id: str,
    cost_logger: CostLogger,
    client: OpenAI,
    model: str,
) -> PdfIngestionResult:
    """Process each PDF page independently while preserving partial results."""
    page_texts: list[str] = []
    failed_pages: list[int] = []
    vision_pages: list[int] = []

    for page_index, page in enumerate(pdf.pages, start=1):
        try:
            page_text, used_vision = _extract_page_text(
                pdf_bytes=pdf_bytes,
                page=page,
                page_number=page_index,
                file_id=file_id,
                cost_logger=cost_logger,
                client=client,
                model=model,
            )
            if page_text:
                page_texts.append(page_text)
            if used_vision:
                vision_pages.append(page_index)
        except Exception:
            failed_pages.append(page_index)

    transcript_text = "\n\n".join(text for text in page_texts if text.strip()).strip()
    partial_notes = _build_partial_notes(failed_pages)
    if len(transcript_text) < MIN_SUMMARIZATION_TEXT_LENGTH and transcript_text:
        partial_notes.append(
            "Extracted text is under 100 characters. Summarization should be skipped, but search can still run."
        )

    return PdfIngestionResult(
        transcript_text=transcript_text,
        failed_pages=failed_pages,
        is_partial=bool(failed_pages),
        partial_notes=partial_notes,
        should_skip_summary=len(transcript_text) < MIN_SUMMARIZATION_TEXT_LENGTH,
        pages_processed=len(pdf.pages) - len(failed_pages),
        vision_pages=vision_pages,
    )


def _extract_page_text(
    *,
    pdf_bytes: bytes,
    page: pdfplumber.page.Page,
    page_number: int,
    file_id: str,
    cost_logger: CostLogger,
    client: OpenAI,
    model: str,
) -> tuple[str, bool]:
    """Extract a single page using free methods first, then vision when needed."""
    extracted_text = (page.extract_text() or "").strip()
    table_text = _extract_table_text(page).strip()
    has_images = bool(page.images)

    if has_images:
        vision_text = _extract_page_with_vision(
            pdf_bytes=pdf_bytes,
            page_number=page_number,
            file_id=file_id,
            cost_logger=cost_logger,
            client=client,
            model=model,
        )
        return vision_text.strip(), True

    combined_text = "\n\n".join(part for part in [table_text, extracted_text] if part).strip()
    if combined_text:
        return combined_text, False

    vision_text = _extract_page_with_vision(
        pdf_bytes=pdf_bytes,
        page_number=page_number,
        file_id=file_id,
        cost_logger=cost_logger,
        client=client,
        model=model,
    )
    return vision_text.strip(), True


def _extract_table_text(page: pdfplumber.page.Page) -> str:
    """Convert extracted tables into pipe-delimited plain text."""
    extracted_tables = page.extract_tables() or []
    formatted_tables: list[str] = []
    for table in extracted_tables:
        rows: list[str] = []
        for row in table:
            cells = [str(cell).strip() if cell is not None else "" for cell in row]
            if any(cells):
                rows.append(" | ".join(cells))
        if rows:
            formatted_tables.append("\n".join(rows))
    return "\n\n".join(formatted_tables)


def _extract_page_with_vision(
    *,
    pdf_bytes: bytes,
    page_number: int,
    file_id: str,
    cost_logger: CostLogger,
    client: OpenAI,
    model: str,
) -> str:
    """Render a PDF page to PNG and extract visible text through vision."""
    images = convert_from_bytes(
        pdf_bytes,
        first_page=page_number,
        last_page=page_number,
        fmt="png",
        single_file=True,
    )
    if not images:
        return ""

    png_bytes = _prepare_rendered_page(images[0])
    data_url = _to_data_url(png_bytes)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You extract visible text from document images. Return only the text "
                        f"that appears on the page. If there is no readable text, return exactly {NO_TEXT_SENTINEL}."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Extract all visible text from this PDF page. Preserve reading order "
                                f"when possible. If there is no readable text, return exactly {NO_TEXT_SENTINEL}."
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
        cost_logger.log_api_call(
            file_id=file_id,
            operation_type="pdf_page_vision",
            model=model,
            prompt_tokens=0,
            completion_tokens=0,
            success=False,
            error_message=f"Page {page_number}: {exc}",
        )
        raise

    prompt_tokens, completion_tokens = extract_usage_tokens(response)
    cost_logger.log_api_call(
        file_id=file_id,
        operation_type="pdf_page_vision",
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        success=True,
        error_message="",
    )

    extracted_text = extract_chat_response_text(response).strip()
    if extracted_text == NO_TEXT_SENTINEL:
        return ""
    return extracted_text


def _prepare_rendered_page(image: Image.Image) -> bytes:
    """Resize a rendered page if needed and encode it as PNG."""
    working_image = image.copy()
    if working_image.mode not in ("RGB", "RGBA"):
        working_image = working_image.convert("RGB")

    if max(working_image.size) > MAX_IMAGE_DIMENSION:
        working_image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION))

    buffer = BytesIO()
    working_image.save(buffer, format="PNG")
    return buffer.getvalue()


def _build_partial_notes(failed_pages: list[int]) -> list[str]:
    """Return user-facing notes describing skipped pages."""
    if not failed_pages:
        return []
    page_list = ", ".join(str(page) for page in failed_pages)
    return [f"Pages {page_list} could not be extracted."]


def _to_data_url(image_bytes: bytes) -> str:
    """Encode PNG bytes as a data URL for the vision request."""
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"
