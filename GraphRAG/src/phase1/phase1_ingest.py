from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from utils import ensure_directories, get_pdf_path, load_pdf_pages, save_json, chunk_page_text


def build_chunks(pdf_path: Path, chunk_size: int, chunk_overlap: int) -> dict:
    pages = load_pdf_pages(pdf_path)
    chunks = []

    for page in pages:
        page_chunks = chunk_page_text(
            page_text=page["text"],
            page_number=page["page_number"],
            source_file=pdf_path.name,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        chunks.extend(page_chunks)

    return {
        "source_file": pdf_path.name,
        "chunking_strategy": {
            "type": "fixed_size",
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        },
        "page_count": len(pages),
        "pages": pages,
        "chunk_count": len(chunks),
        "chunks": [chunk.to_dict() for chunk in chunks],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract and chunk the Phase 1 PDF.")
    parser.add_argument("--pdf-path", default=None)
    parser.add_argument("--chunk-size", type=int, default=700)
    parser.add_argument("--chunk-overlap", type=int, default=100)
    args = parser.parse_args()

    ensure_directories()
    pdf_path = get_pdf_path(args.pdf_path)
    payload = build_chunks(
        pdf_path=pdf_path,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )
    save_json(Path("outputs/chunks.json"), payload)

    print(f"Saved {payload['chunk_count']} chunks from {payload['page_count']} pages to outputs/chunks.json")


if __name__ == "__main__":
    main()
