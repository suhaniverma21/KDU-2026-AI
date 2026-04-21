from __future__ import annotations

from typing import Any

from tri_model_assistant.config import MAX_QA_INPUT_TOKENS, MIN_QA_CONFIDENCE, NO_ANSWER_MESSAGE


def is_qa_input_too_long(question: str, context: str, qa_pipeline: Any) -> bool:
    token_count = len(
        qa_pipeline.tokenizer.encode(
            question,
            context,
            add_special_tokens=True,
            truncation=False,
        )
    )
    return token_count > MAX_QA_INPUT_TOKENS


def answer_question(question: str, context: str, qa_pipeline: Any) -> str:
    try:
        result = qa_pipeline(question=question, context=context)
        answer = result.get("answer", "").strip()
        score = float(result.get("score", 0.0))
    except Exception:
        return "Question answering failed for this prompt. Please try a simpler question."

    if not answer or score < MIN_QA_CONFIDENCE:
        return NO_ANSWER_MESSAGE

    return answer
