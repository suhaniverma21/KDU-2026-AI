# Hybrid-Search RAG Chatbot

Local Python project scaffold for a single-document hybrid-search RAG teaching assistant.

## Current Status

The repository structure is set up and the app is runnable. Core ingestion, retrieval, reranking, and generation logic are still placeholders.

## Project Structure

```text
app.py
pipeline/
evaluation/
storage/
utils/
requirements.txt
.env.example
README.md
implementation-plan.md
```

## Setup

```bash
pip install -r requirements.txt
```

Optional:

```bash
copy .env.example .env
```

## Run

```bash
streamlit run app.py
```

## Next Build Steps

1. Implement document ingestion for PDF and URL sources.
2. Add recursive chunking.
3. Add contextual enrichment.
4. Add semantic and BM25 indexing.
5. Add hybrid retrieval, reranking, and grounded generation.
6. Add evaluation scripts.
