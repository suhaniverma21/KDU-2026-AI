from __future__ import annotations

from typing import Any

from langchain_community.llms import HuggingFacePipeline
from transformers import AutoModelForQuestionAnswering, AutoModelForSeq2SeqLM, AutoTokenizer

from tri_model_assistant.adapters import LocalQuestionAnsweringPipeline, LocalSeq2SeqPipeline
from tri_model_assistant.config import QA_MODEL_NAME, REFINER_MODEL_NAME, SUMMARIZER_MODEL_NAME
from tri_model_assistant.schemas import AppModels, SummarizerResources
from tri_model_assistant.system import format_model_error, get_model_load_kwargs, get_torch_device


def load_models() -> AppModels:
    return AppModels(
        summarizer=load_summarizer(),
        refiner=load_refiner(),
        qa_pipeline=load_qa_model(),
    )


def load_summarizer() -> SummarizerResources:
    print("\nLoading summarization model...")
    return _load_seq2seq_llm(SUMMARIZER_MODEL_NAME)


def load_refiner() -> SummarizerResources:
    print("Loading refinement model...")
    return _load_seq2seq_llm(REFINER_MODEL_NAME)


def load_qa_model() -> Any:
    print("Loading question answering model...")
    try:
        tokenizer = AutoTokenizer.from_pretrained(QA_MODEL_NAME)
        model = AutoModelForQuestionAnswering.from_pretrained(
            QA_MODEL_NAME,
            **get_model_load_kwargs(),
        )
        model = model.to(get_torch_device())
        model.eval()

        return LocalQuestionAnsweringPipeline(
            model=model,
            tokenizer=tokenizer,
            device=get_torch_device(),
        )
    except Exception as exc:
        raise RuntimeError(format_model_error(exc)) from exc


def _load_seq2seq_llm(model_name: str) -> SummarizerResources:
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSeq2SeqLM.from_pretrained(
            model_name,
            **get_model_load_kwargs(),
        )
        model = model.to(get_torch_device())
        model.eval()

        local_pipeline = LocalSeq2SeqPipeline(
            model=model,
            tokenizer=tokenizer,
            device=get_torch_device(),
        )

        llm = HuggingFacePipeline(pipeline=local_pipeline)
        return SummarizerResources(tokenizer=tokenizer, llm=llm)
    except Exception as exc:
        raise RuntimeError(format_model_error(exc)) from exc
