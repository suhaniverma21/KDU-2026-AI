from __future__ import annotations

import torch

from tri_model_assistant.config import EXIT_COMMAND, LENGTH_CONFIGS, NO_ANSWER_MESSAGE
from tri_model_assistant.qa import answer_question, is_qa_input_too_long
from tri_model_assistant.system import get_total_ram_gb


def print_header(title: str) -> None:
    print(f"\n=== {title} ===")


def print_banner() -> None:
    print("=" * 42)
    print("        Tri-Model AI Assistant")
    print("  Powered by HuggingFace + LangChain")
    print("=" * 42)


def print_system_warning() -> None:
    if not torch.cuda.is_available():
        print("Running in CPU mode. Large models may take time to load and answer.")

    total_ram_gb = get_total_ram_gb()
    if total_ram_gb is not None and total_ram_gb < 8:
        print(f"Detected about {total_ram_gb} GB RAM. You may see slowdowns or memory pressure.")


def read_multiline_input() -> str:
    print_header("Input Text")
    print("Paste your text below.")
    print("Finish by pressing Enter on two empty lines.\n")
    print("Warning: This works best with normal everyday text.\n")

    lines: list[str] = []
    blank_line_count = 0

    while True:
        line = input()
        if not line.strip():
            blank_line_count += 1
            if blank_line_count >= 2:
                break
            lines.append("")
            continue

        blank_line_count = 0
        lines.append(line)

    return "\n".join(lines).strip()


def validate_source_text(text: str) -> bool:
    return bool(text.strip())


def select_summary_length() -> str:
    print_header("Summary Length")
    print("Choose one: short / medium / long")

    while True:
        choice = input("> ").strip().lower()
        if choice in LENGTH_CONFIGS:
            return choice
        print("Please type one of: short, medium, or long.")


def display_summary(summary: str) -> None:
    print_header("Your Summary")
    print(summary)
    print()


def pause_for_user(message: str = "Press Enter to continue...") -> None:
    input(message)


def run_qa_loop(context: str, qa_pipeline, fallback_context: str | None = None) -> None:
    normalized_context = context.strip()
    normalized_fallback = fallback_context.strip() if fallback_context else None

    print_header("Q&A Session")
    print(f"Type '{EXIT_COMMAND}' to quit.\n")

    while True:
        question = input("Your question: ").strip()

        if not question:
            print("Please enter a question or type 'exit'.")
            continue

        if question.lower() == EXIT_COMMAND:
            print("\nThanks for using Tri-Model AI Assistant.")
            print("Goodbye!")
            break

        if is_qa_input_too_long(question, normalized_context, qa_pipeline):
            print("Question plus summary is too long for Model 3. Please ask a shorter question.\n")
            continue

        answer = answer_question(question, normalized_context, qa_pipeline)
        if (
            answer == NO_ANSWER_MESSAGE
            and normalized_fallback
            and normalized_fallback != normalized_context
        ):
            fallback_answer = answer_question(question, normalized_fallback, qa_pipeline)
            if fallback_answer != NO_ANSWER_MESSAGE:
                print("Answer recovered from the initial summary.\n")
                answer = fallback_answer

        print(f"Answer: {answer}\n")
