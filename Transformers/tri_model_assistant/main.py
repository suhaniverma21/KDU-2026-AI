from __future__ import annotations

from tri_model_assistant.cli import (
    display_summary,
    pause_for_user,
    print_banner,
    print_header,
    print_system_warning,
    read_multiline_input,
    run_qa_loop,
    select_summary_length,
    validate_source_text,
)
from tri_model_assistant.models import load_models
from tri_model_assistant.summarization import generate_initial_summary, is_short_input, refine_summary
from tri_model_assistant.system import configure_output


def main() -> None:
    configure_output()
    print_banner()
    print_system_warning()

    try:
        source_text = read_multiline_input()
        if not validate_source_text(source_text):
            print("No text was provided. Please run the program again and paste some text.")
            return

        length_choice = select_summary_length()

        print_header("Setup")
        print("The first run may take a while because the models need to download.")
        print("Preparing models and summary pipeline...\n")

        models = load_models()

        print_header("Initial Summarization")
        if is_short_input(source_text):
            print("Input is under 100 words. Skipping Model 1 and sending raw text directly to Model 2.")
            initial_summary = source_text
        else:
            initial_summary = generate_initial_summary(source_text, models.summarizer)

        print_header("Model 1 Output")
        print(initial_summary)
        print()
        pause_for_user()

        print_header("Refining Summary")
        print(f"Target length: {length_choice}")
        print("Generating refined summary...")
        refined_summary = refine_summary(initial_summary, models.refiner, length_choice)

        print_header("Model 2 Output")
        print(refined_summary)
        print()
        pause_for_user()

        display_summary(refined_summary)
        run_qa_loop(refined_summary, models.qa_pipeline, fallback_context=initial_summary)

    except KeyboardInterrupt:
        print("\nInterrupted by user. Goodbye!")
    except EOFError:
        print("\nInput ended unexpectedly. Please run the program again.")
    except RuntimeError as exc:
        print(f"\n{exc}")
    except Exception as exc:
        print("\nThe application ran into an error.")
        print(f"Details: {exc}")
        print("Try reinstalling the requirements or rerun after checking your local model cache.")
