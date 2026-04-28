"""Central configuration constants for the Content Accessibility Suite."""

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
REGISTRY_DIR = DATA_DIR / "registry"
LOGS_DIR = DATA_DIR / "logs"
CHROMA_PATH = BASE_DIR / "chroma_store"
KEYWORD_STORE_DIR = BASE_DIR / "keyword_store"

FILE_SIZE_LIMITS_MB = {
    "pdf": 100,
    "image": 20,
    "audio": 500,
}

AUDIO_DURATION_LIMIT_MINUTES = 120

CHUNK_SIZE_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 50
MAX_CHUNKS_PER_DOCUMENT = 2000
EMBEDDING_BATCH_SIZE = 500

SEARCH_SIMILARITY_THRESHOLD = 0.35
SEARCH_RETRIEVAL_COUNT = 10
SEARCH_RETURN_COUNT = 5
RRF_K = 60

OPENAI_VISION_MODEL = "gpt-4o-mini"
OPENAI_SUMMARIZATION_MODEL = "gpt-4o-mini"
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
LOCAL_WHISPER_MODEL = "openai/whisper-base"

CHROMA_COLLECTION_NAME = "content_accessibility_chunks"

FILESTORE_PATH = REGISTRY_DIR / "files.json"
COST_LOG_PATH = LOGS_DIR / "cost_log.jsonl"
KEYWORD_INDEX_PATH = KEYWORD_STORE_DIR / "index.json"

MODEL_PRICING_USD_PER_1M_TOKENS = {
    "gpt-4o-mini": {
        "input": 0.15,
        "output": 0.60,
    },
    "text-embedding-3-small": {
        "input": 0.02,
        "output": 0.0,
    },
}
