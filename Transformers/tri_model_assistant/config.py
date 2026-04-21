SUMMARIZER_MODEL_NAME = "facebook/bart-large-cnn"
REFINER_MODEL_NAME = "google/flan-t5-base"
QA_MODEL_NAME = "deepset/roberta-base-squad2"

EXIT_COMMAND = "exit"

SHORT_INPUT_WORD_THRESHOLD = 100
MAX_BART_INPUT_TOKENS = 1024
CHUNK_TOKEN_LIMIT = 800
MAX_QA_INPUT_TOKENS = 512

INITIAL_SUMMARY_MIN_LENGTH = 60
INITIAL_SUMMARY_MAX_LENGTH = 180
INTERMEDIATE_SUMMARY_MIN_LENGTH = 40
INTERMEDIATE_SUMMARY_MAX_LENGTH = 120

MIN_QA_CONFIDENCE = 0.1
NO_ANSWER_MESSAGE = "Answer not found in summary"

LENGTH_CONFIGS = {
    "short": {"min_length": 30, "max_length": 60},
    "medium": {"min_length": 60, "max_length": 130},
    "long": {"min_length": 130, "max_length": 250},
}

REFINEMENT_PROMPTS = {
    "short": (
        "Rewrite the summary below into a short summary. "
        "Use only information provided, do not add new facts. "
        "Do not remove important facts, and keep all relevant information.\n\n"
        "Summary:\n{summary}"
    ),
    "medium": (
        "Rewrite the summary below into a medium-length summary. "
        "Use only information provided, do not add new facts. "
        "Do not remove important facts, and keep all relevant information.\n\n"
        "Summary:\n{summary}"
    ),
    "long": (
        "Rewrite the summary below into a long summary. "
        "Use only information provided, do not add new facts. "
        "Do not remove important facts, and keep all relevant information.\n\n"
        "Summary:\n{summary}"
    ),
}
