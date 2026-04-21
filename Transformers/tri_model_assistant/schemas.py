from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_community.llms import HuggingFacePipeline
from transformers import AutoTokenizer


@dataclass
class SummarizerResources:
    tokenizer: AutoTokenizer
    llm: HuggingFacePipeline


@dataclass
class AppModels:
    summarizer: SummarizerResources
    refiner: SummarizerResources
    qa_pipeline: Any
