from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

import chromadb
import numpy as np
from openai import OpenAI
from sklearn.feature_extraction.text import TfidfVectorizer

sys.path.append(str(Path(__file__).resolve().parents[1]))

from utils import (
    ATTACK_QUERY,
    CHROMA_DIR,
    build_ground_truth,
    ensure_directories,
    extractive_answer_from_context,
    get_llm_client_config,
    load_json,
)


class TfidfEmbeddingFunction:
    def __init__(self, texts: Sequence[str]):
        self.vectorizer = TfidfVectorizer(stop_words="english")
        self.vectorizer.fit(texts)

    def _transform(self, input: Sequence[str]) -> list[list[float]]:
        matrix = self.vectorizer.transform(input)
        return matrix.toarray().astype(float).tolist()

    def __call__(self, input: Sequence[str]) -> list[list[float]]:
        return self._transform(input)

    def embed_documents(self, input: Sequence[str]) -> list[list[float]]:
        return self._transform(input)

    def embed_query(self, input: Sequence[str]) -> list[list[float]]:
        return self._transform(input)


def load_chunks(chunks_path: str = "outputs/chunks.json") -> dict:
    chunks_path = Path(chunks_path)
    if not chunks_path.exists():
        raise FileNotFoundError("outputs/chunks.json not found. Run src/phase1_ingest.py first.")
    return load_json(chunks_path)


def build_collection(payload: dict):
    chunks = payload["chunks"]
    documents = [chunk["text"] for chunk in chunks]
    embedding_function = TfidfEmbeddingFunction(documents)

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection_name = "phase1_fixed_size"

    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    collection = client.create_collection(
        name=collection_name,
        embedding_function=embedding_function,
        metadata={"baseline": "fixed_size_vector_rag"},
    )
    collection.add(
        ids=[chunk["chunk_id"] for chunk in chunks],
        documents=documents,
        metadatas=[
            {
                "page_number": chunk["page_number"],
                "chunk_index_on_page": chunk["chunk_index_on_page"],
                "start_char": chunk["start_char"],
                "end_char": chunk["end_char"],
                "source_file": chunk["source_file"],
            }
            for chunk in chunks
        ],
    )

    return collection, embedding_function


def retrieve(payload: dict, query: str, top_k: int) -> dict:
    collection, _ = build_collection(payload)
    results = collection.query(query_texts=[query], n_results=top_k)

    retrieved_chunks = []
    ids = results["ids"][0]
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    for rank, (chunk_id, document, metadata, distance) in enumerate(
        zip(ids, documents, metadatas, distances),
        start=1,
    ):
        retrieved_chunks.append(
            {
                "rank": rank,
                "chunk_id": chunk_id,
                "page_number": metadata["page_number"],
                "chunk_index_on_page": metadata["chunk_index_on_page"],
                "distance": float(distance),
                "text": document,
            }
        )

    return {
        "query": query,
        "top_k": top_k,
        "retrieved_chunks": retrieved_chunks,
    }


def generate_answer(query: str, retrieved_chunks: list[dict]) -> tuple[str, str]:
    llm_config = get_llm_client_config()

    if not llm_config:
        return extractive_answer_from_context(retrieved_chunks), "extractive_fallback"

    context = "\n\n".join(
        f"[Rank {chunk['rank']} | Page {chunk['page_number']} | {chunk['chunk_id']}]\n{chunk['text']}"
        for chunk in retrieved_chunks
    )
    client = OpenAI(api_key=llm_config["api_key"], base_url=llm_config["base_url"])
    response = client.chat.completions.create(
        model=llm_config["model"],
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "Answer only from the provided context. "
                    "If the context is insufficient, say so clearly."
                ),
            },
            {
                "role": "user",
                "content": f"Question: {query}\n\nContext:\n{context}",
            },
        ],
    )
    return response.choices[0].message.content.strip(), llm_config["model"]


def evaluate_failure(retrieved_chunks: list[dict], source_file: str) -> dict:
    ground_truth = build_ground_truth(source_file)
    retrieved_pages = [chunk["page_number"] for chunk in retrieved_chunks]
    page_5_missing = ground_truth["phase1_expected_gap_page"] not in retrieved_pages

    return {
        "ground_truth": ground_truth,
        "retrieved_pages": retrieved_pages,
        "missing_expected_page": ground_truth["phase1_expected_gap_page"] if page_5_missing else None,
        "page_5_missing": page_5_missing,
        "notes": [
            "The ultimate parent fact sits on Page 5 and may rank low because it does not strongly overlap with the wording of the question.",
            "Chunks mentioning John Smith and Apex Consulting Ltd are likely to rank higher than chunks about the distant parent company.",
            "Fixed-size chunking preserves local wording but not the ownership chain across pages.",
        ],
    }


def run(query: str, top_k: int, chunks_path: str = "outputs/chunks.json") -> dict:
    ensure_directories()
    payload = load_chunks(chunks_path)
    retrieval = retrieve(payload=payload, query=query, top_k=top_k)
    answer, answer_model = generate_answer(query=query, retrieved_chunks=retrieval["retrieved_chunks"])
    failure_analysis = evaluate_failure(retrieval["retrieved_chunks"], payload["source_file"])

    return {
        "query": query,
        "top_k": top_k,
        "source_file": payload["source_file"],
        "embedding_model": "local_tfidf_baseline",
        "answer_model": answer_model,
        "retrieval": retrieval,
        "answer": answer,
        "failure_analysis": failure_analysis,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 1 baseline RAG pipeline.")
    parser.add_argument("--query", default=ATTACK_QUERY)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--chunks-path", default="outputs/chunks.json")
    args = parser.parse_args()

    result = run(query=args.query, top_k=args.top_k, chunks_path=args.chunks_path)
    Path("outputs/retrieval_results.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    print(f"Saved retrieval results to outputs/retrieval_results.json")
    print(f"Answer model: {result['answer_model']}")
    print(f"Answer: {result['answer']}")
    print("Retrieved pages:", result["failure_analysis"]["retrieved_pages"])


if __name__ == "__main__":
    main()
