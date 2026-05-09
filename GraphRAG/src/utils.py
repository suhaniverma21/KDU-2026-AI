from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import fitz


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
CHROMA_DIR = OUTPUTS_DIR / "chroma_phase1"
DOTENV_PATH = PROJECT_ROOT / ".env"


ATTACK_QUERY = "Who is the ultimate parent company of the organization John Smith works for?"


@dataclass
class ChunkRecord:
    chunk_id: str
    page_number: int
    chunk_index_on_page: int
    start_char: int
    end_char: int
    text: str
    source_file: str

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "page_number": self.page_number,
            "chunk_index_on_page": self.chunk_index_on_page,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "text": self.text,
            "source_file": self.source_file,
        }


def ensure_directories() -> None:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)


def load_project_env() -> None:
    if not DOTENV_PATH.exists():
        return

    for raw_line in DOTENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key or key in os.environ:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        os.environ[key] = value


def load_pdf_pages(pdf_path: Path) -> list[dict]:
    doc = fitz.open(pdf_path)
    pages: list[dict] = []

    try:
        for index in range(doc.page_count):
            text = normalize_whitespace(doc[index].get_text())
            pages.append(
                {
                    "page_number": index + 1,
                    "text": text,
                    "char_count": len(text),
                }
            )
    finally:
        doc.close()

    return pages


def normalize_whitespace(text: str) -> str:
    replacements = {
        "\u2014": "-",
        "\u2013": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u20ac": "EUR ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return re.sub(r"\s+", " ", text).strip()


def chunk_page_text(
    page_text: str,
    page_number: int,
    source_file: str,
    chunk_size: int = 700,
    chunk_overlap: int = 100,
) -> list[ChunkRecord]:
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    chunks: list[ChunkRecord] = []
    start = 0
    chunk_index = 0
    step = chunk_size - chunk_overlap

    while start < len(page_text):
        end = min(len(page_text), start + chunk_size)
        chunk_text = page_text[start:end].strip()

        if chunk_text:
            chunks.append(
                ChunkRecord(
                    chunk_id=f"page-{page_number:02d}-chunk-{chunk_index:02d}",
                    page_number=page_number,
                    chunk_index_on_page=chunk_index,
                    start_char=start,
                    end_char=end,
                    text=chunk_text,
                    source_file=source_file,
                )
            )

        if end >= len(page_text):
            break

        start += step
        chunk_index += 1

    return chunks


def save_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def get_pdf_path(pdf_path_arg: str | None = None) -> Path:
    if pdf_path_arg:
        pdf_path = Path(pdf_path_arg)
        if not pdf_path.is_absolute():
            pdf_path = PROJECT_ROOT / pdf_path
    else:
        candidates = [
            DATA_DIR / "corporate-doc.pdf",
            DATA_DIR / "corporate.pdf",
        ]
        pdf_path = next((candidate for candidate in candidates if candidate.exists()), None)
        if pdf_path is None:
            raise FileNotFoundError(
                f"Expected a PDF at one of: {', '.join(str(candidate) for candidate in candidates)}"
            )

    if not pdf_path.exists():
        raise FileNotFoundError(f"Expected PDF at {pdf_path}")
    return pdf_path


def build_ground_truth(source_file: str | None = None) -> dict:
    truth_by_source = {
        "corporate.pdf": {
            "employee": "John Smith",
            "works_for": "Apex Consulting Ltd",
            "ownership_path": [
                "Apex Consulting Ltd",
                "Meridian Holdings",
                "Orion Group International",
                "Global Nexus Corporation",
            ],
            "ultimate_parent_company": "Global Nexus Corporation",
            "evidence_pages": [2, 3, 5],
            "phase1_expected_gap_page": 5,
        },
        "corporate-doc.pdf": {
            "employee": "John Smith",
            "works_for": "Harlington Advisory Services Ltd",
            "ownership_path": [
                "Harlington Advisory Services Ltd",
                "Castlepoint Nominees Ltd",
                "Vantage Holding Structures PCC Ltd",
                "Meridian Capital Vehicles Ltd",
                "Orion Group Holdings SA",
                "Global Nexus Corporation",
            ],
            "ultimate_parent_company": "Global Nexus Corporation",
            "evidence_pages": [1, 3, 5],
            "phase1_expected_gap_page": 5,
        },
    }

    if source_file and source_file in truth_by_source:
        return truth_by_source[source_file]

    return {
        "employee": "John Smith",
        "works_for": "Unknown",
        "ownership_path": [],
        "ultimate_parent_company": "Unknown",
        "evidence_pages": [],
        "phase1_expected_gap_page": 5,
    }


def extractive_answer_from_context(retrieved_chunks: Iterable[dict]) -> str:
    text = " ".join(chunk["text"] for chunk in retrieved_chunks)
    lowered = text.lower()

    if "global nexus corporation" in lowered:
        return "Global Nexus Corporation is the ultimate parent company."
    if "orion group international" in lowered and "ultimate strategic control" in lowered:
        return (
            "Based on the retrieved chunks, Orion Group International appears to control "
            "the group, but the full ultimate parent is not proven in the retrieved context."
        )
    if "meridian holdings" in lowered:
        return (
            "Based on the retrieved chunks, John Smith works for Apex Consulting Ltd, "
            "which is owned by Meridian Holdings. The retrieved context does not establish "
            "the ultimate parent company."
        )
    return "The retrieved context does not contain enough connected evidence to identify the ultimate parent company."


def get_llm_client_config() -> dict | None:
    load_project_env()

    openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()

    if openrouter_api_key:
        return {
            "provider": "openrouter",
            "api_key": openrouter_api_key,
            "base_url": os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            "model": os.getenv("PHASE1_LLM_MODEL", "meta-llama/llama-3.1-8b-instruct"),
        }

    if openai_api_key:
        return {
            "provider": "openai",
            "api_key": openai_api_key,
            "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            "model": os.getenv("PHASE1_LLM_MODEL", "gpt-4o-mini"),
        }

    return None
