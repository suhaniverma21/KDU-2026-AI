from __future__ import annotations

from typing import Iterable

import torch
from langchain_community.llms import HuggingFacePipeline
from transformers import AutoTokenizer

from tri_model_assistant.config import (
    CHUNK_TOKEN_LIMIT,
    INITIAL_SUMMARY_MAX_LENGTH,
    INITIAL_SUMMARY_MIN_LENGTH,
    INTERMEDIATE_SUMMARY_MAX_LENGTH,
    INTERMEDIATE_SUMMARY_MIN_LENGTH,
    LENGTH_CONFIGS,
    MAX_BART_INPUT_TOKENS,
    REFINEMENT_PROMPTS,
    SHORT_INPUT_WORD_THRESHOLD,
)
from tri_model_assistant.schemas import SummarizerResources


def count_words(text: str) -> int:
    return len(text.split())


def is_short_input(text: str, min_words: int = SHORT_INPUT_WORD_THRESHOLD) -> bool:
    return count_words(text) < min_words


def count_input_tokens(text: str, tokenizer: AutoTokenizer) -> int:
    return len(tokenizer.encode(text, add_special_tokens=False))


def chunk_text(
    text: str,
    tokenizer: AutoTokenizer,
    max_input_tokens: int = CHUNK_TOKEN_LIMIT,
) -> list[str]:
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    if len(token_ids) <= MAX_BART_INPUT_TOKENS:
        return [text]

    chunks: list[str] = []
    for start in range(0, len(token_ids), max_input_tokens):
        chunk_ids = token_ids[start : start + max_input_tokens]
        chunk_text_value = tokenizer.decode(chunk_ids, skip_special_tokens=True)
        if chunk_text_value.strip():
            chunks.append(chunk_text_value.strip())

    return chunks


def summarize_text(
    text: str,
    summarizer: HuggingFacePipeline,
    min_length: int,
    max_length: int,
) -> str:
    with torch.inference_mode():
        result = summarizer.invoke(
            (
                "Summarize the following text. "
                "Do not remove important facts, and keep all relevant information.\n\n"
                f"Text:\n{text}"
            ),
            pipeline_kwargs={
                "min_length": min_length,
                "max_length": max_length,
                "do_sample": False,
            },
        )
    return result.strip()


def refine_text(
    prompt: str,
    refiner: HuggingFacePipeline,
    min_length: int,
    max_length: int,
) -> str:
    with torch.inference_mode():
        result = refiner.invoke(
            prompt,
            pipeline_kwargs={
                "min_length": min_length,
                "max_length": max_length,
                "do_sample": True,
                "temperature": 0.3,
            },
        )
    return result.strip()


def summarize_chunks(
    chunks: Iterable[str],
    summarizer: HuggingFacePipeline,
    min_length: int,
    max_length: int,
) -> str:
    summaries: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        print(f"Summarizing chunk {index}...")
        summaries.append(
            summarize_text(
                text=chunk,
                summarizer=summarizer,
                min_length=min_length,
                max_length=max_length,
            )
        )
    return " ".join(summaries).strip()


def generate_initial_summary(text: str, resources: SummarizerResources) -> str:
    token_count = count_input_tokens(text, resources.tokenizer)
    print(f"Model 1 input token count: {token_count}")

    chunks = chunk_text(text, resources.tokenizer)

    if len(chunks) == 1:
        print("Generating initial summary...")
        return summarize_text(
            text=chunks[0],
            summarizer=resources.llm,
            min_length=INITIAL_SUMMARY_MIN_LENGTH,
            max_length=INITIAL_SUMMARY_MAX_LENGTH,
        )

    print(f"Input is long, so it will be summarized in {len(chunks)} chunks first.")
    intermediate_summary = summarize_chunks(
        chunks=chunks,
        summarizer=resources.llm,
        min_length=INTERMEDIATE_SUMMARY_MIN_LENGTH,
        max_length=INTERMEDIATE_SUMMARY_MAX_LENGTH,
    )

    return summarize_text(
        text=intermediate_summary,
        summarizer=resources.llm,
        min_length=INITIAL_SUMMARY_MIN_LENGTH,
        max_length=INITIAL_SUMMARY_MAX_LENGTH,
    )


def get_length_config(length_choice: str) -> dict[str, int]:
    return LENGTH_CONFIGS[length_choice]


def refine_summary(summary: str, resources: SummarizerResources, length_choice: str) -> str:
    config = get_length_config(length_choice)
    prompt = REFINEMENT_PROMPTS[length_choice].format(summary=summary)
    return refine_text(
        prompt=prompt,
        refiner=resources.llm,
        min_length=config["min_length"],
        max_length=config["max_length"],
    )
