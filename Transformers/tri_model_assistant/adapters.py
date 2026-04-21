from __future__ import annotations

from typing import Any

import torch


class LocalSeq2SeqPipeline:
    """Small adapter so LangChain can wrap a local seq2seq model reliably."""

    task = "text2text-generation"

    def __init__(self, model, tokenizer, device: str) -> None:
        self.model = model
        self.tokenizer = tokenizer
        self.device = device

    def __call__(self, inputs, **kwargs):
        if isinstance(inputs, str):
            prompts = [inputs]
        else:
            prompts = list(inputs)

        encoded = self.tokenizer(
            prompts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=1024,
        )
        encoded = {key: value.to(self.device) for key, value in encoded.items()}

        outputs = self.model.generate(
            **encoded,
            min_length=kwargs.get("min_length", 60),
            max_length=kwargs.get("max_length", 180),
            do_sample=kwargs.get("do_sample", False),
            temperature=kwargs.get("temperature", 1.0),
        )

        decoded = self.tokenizer.batch_decode(outputs, skip_special_tokens=True)
        return [{"generated_text": text.strip()} for text in decoded]


class LocalQuestionAnsweringPipeline:
    """Simple extractive QA adapter that avoids task-registry differences."""

    def __init__(self, model, tokenizer, device: str) -> None:
        self.model = model
        self.tokenizer = tokenizer
        self.device = device

    def __call__(self, question: str, context: str) -> dict[str, Any]:
        encoded = self.tokenizer(
            question,
            context,
            return_tensors="pt",
            truncation="only_second",
            max_length=512,
        )
        encoded = {key: value.to(self.device) for key, value in encoded.items()}

        with torch.inference_mode():
            outputs = self.model(**encoded)

        input_ids = encoded["input_ids"][0]
        start_logits = outputs.start_logits[0]
        end_logits = outputs.end_logits[0]

        start_index = int(torch.argmax(start_logits).item())
        end_index = int(torch.argmax(end_logits).item())

        if end_index < start_index:
            end_index = start_index

        answer_ids = input_ids[start_index : end_index + 1]
        answer = self.tokenizer.decode(answer_ids, skip_special_tokens=True).strip()

        no_answer_score = float((start_logits[0] + end_logits[0]).item())
        best_span_score = float((start_logits[start_index] + end_logits[end_index]).item())

        return {
            "answer": answer,
            "score": best_span_score - no_answer_score,
        }
