# Implementation Plan

## Objective

Build the Content Accessibility Suite as a modular Streamlit application that:

- ingests PDFs, images, and audio
- extracts accessible text
- normalizes and chunks content
- creates embeddings and hybrid search
- generates cached summaries, key points, and tags
- tracks processing state and API cost

This plan is designed to be implementable in a short project window while preserving clean architecture and low-cost behavior.

## Delivery Strategy

Build the application in small vertical slices so the system becomes usable early:

1. Project scaffold and configuration
2. File registry, status tracking, and cost logging
3. Chroma startup and embedding path
4. PDF, image, and audio ingestion modules
5. Shared text quality gate and chunker
6. Search pipeline
7. Summarization pipeline
8. Streamlit UI integration
9. Error handling, caching, and verification

## Implementation Principles

- Prefer deterministic logic before LLM calls
- Fail fast on invalid files
- Cache aggressively after expensive work
- Keep search and summarization independent
- Preserve partial value whenever full success is impossible
- Use configuration constants instead of hardcoded thresholds

## Proposed Repository Layout

```text
accessibility_suite/
├── app.py
├── config.py
├── utils.py
├── ingest/
│   ├── __init__.py
│   ├── validator.py
│   ├── pdf.py
│   ├── image.py
│   └── audio.py
├── pipeline/
│   ├── __init__.py
│   ├── quality_gate.py
│   ├── chunker.py
│   ├── embedder.py
│   ├── summarizer.py
│   └── search.py
├── storage/
│   ├── __init__.py
│   ├── vectorstore.py
│   ├── filestore.py
│   └── cost_log.py
├── data/
│   ├── uploads/
│   ├── registry/
│   └── logs/
├── chroma_store/
├── requirements.txt
├── .env.example
└── .gitignore
```

## Phase 1: Project Scaffold

### Goals

- create the package layout
- define configuration constants
- add dependencies
- initialize environment loading

### Tasks

- Create directories for `ingest`, `pipeline`, `storage`, `data`, and `chroma_store`
- Add `requirements.txt`
- Add `.env.example` with `OPENAI_API_KEY`
- Create `config.py` for:
  - file size limits
  - audio duration limit
  - chunk size and overlap
  - maximum chunks
  - embedding batch size
  - search threshold
  - RRF and retrieval parameters
  - model names
  - Chroma collection name and path
- Create a small `utils.py` for shared helpers such as hashing, MIME helpers, and timestamp formatting

### Output

A runnable project skeleton with shared configuration and dependencies defined.

## Phase 2: File Registry and Status Tracking

### Goals

- support deduplication
- persist file-level metadata
- track processing status
- store cached outputs

### Tasks

- Implement `storage/filestore.py`
- Define a file record schema with:
  - `file_id`
  - `md5`
  - `original_name`
  - `source_type`
  - `mime_type`
  - `status`
  - `transcript`
  - `summary`
  - `key_points`
  - `tags`
  - `partial_notes`
  - `error_message`
  - `created_at`
  - `updated_at`
- Use a simple JSON-backed registry or SQLite-backed local store
- Add helpers to:
  - create file records
  - update status
  - look up by MD5
  - save transcripts and summaries
  - mark summary pending
  - record partial extraction notes

### Output

A local persistent metadata layer that enables deduplication and status-driven UI behavior.

## Phase 3: Cost Logging

### Goals

- track API usage and cost for each operation
- expose data for UI reporting

### Tasks

- Implement `storage/cost_log.py`
- Support logging for:
  - timestamp
  - file ID
  - operation type
  - model
  - prompt tokens
  - completion tokens
  - cost in USD
  - success boolean
  - error message
- Add cost computation helpers for:
  - `gpt-4o-mini`
  - `text-embedding-3-small`
- Support:
  - session total
  - per-file totals
  - totals grouped by operation type

### Output

A reusable logging module that records and aggregates cost metrics for the UI.

## Phase 4: Validation and Deduplication

### Goals

- reject bad uploads early
- avoid reprocessing duplicates

### Tasks

- Implement `ingest/validator.py`
- Validate:
  - non-empty upload
  - file size
  - extension and MIME consistency
  - readable/openable file
  - audio duration under limit
- Compute MD5 from uploaded bytes
- If the MD5 exists, return the cached result immediately
- Return a normalized validation result object with:
  - `is_valid`
  - `source_type`
  - `md5`
  - `mime_type`
  - `cached_record`
  - `error_message`

### Output

A single validation entry point used before any ingestion begins.

## Phase 5: Ingestion Modules

## PDF Ingestion

### Tasks

- Implement `ingest/pdf.py`
- Open PDFs with `pdfplumber`
- For each page:
  - extract text
  - extract tables and convert rows to pipe-delimited text
  - inspect page images
  - route image-heavy or blank pages to vision fallback
- Use `pdf2image` for rendering pages when vision is needed
- Capture per-page failures without stopping the whole document
- Return:
  - transcript text
  - failed pages list
  - partial status flag
  - extraction notes

### Acceptance Criteria

- Encrypted PDFs fail cleanly
- Blank scanned pages use vision fallback
- Fully image-based PDFs are processed entirely through per-page vision fallback
- Mixed PDFs preserve extracted text and partial failure reporting

## Image Ingestion

### Tasks

- Implement `ingest/image.py`
- Open images with Pillow
- Resize if the longest dimension exceeds 2048px
- Convert to PNG before sending to vision
- Parse the vision result into transcript text
- If no text is found, store an empty transcript and skip later chunk/embedding work

### Acceptance Criteria

- Large images are resized before API usage
- Non-text images do not trigger unnecessary downstream steps

## Audio Ingestion

### Tasks

- Implement `ingest/audio.py`
- Load audio with `pydub`
- Detect silence near each 10-minute boundary
- Split audio at the closest silence point
- Transcribe each segment with a local HuggingFace Whisper pipeline
- Concatenate segment transcripts
- Reject silent audio when the final transcript is too short
- Log the first model download event clearly

### Acceptance Criteria

- Long audio is segmented safely
- Corrupted audio fails early
- Silent audio returns a plain-English error

## Phase 6: Text Quality Gate and Chunking

### Goals

- normalize text
- decide whether summarization should run
- create search-ready chunks

### Tasks

- Implement `pipeline/quality_gate.py`
- Normalize encoding to UTF-8-safe text
- Collapse excessive whitespace
- Decide:
  - summary should be skipped for under-150-character text
  - very short transcript still proceeds to chunking where applicable
- Implement `pipeline/chunker.py`
- Use `RecursiveCharacterTextSplitter`
- Use `tiktoken` for token-aware chunk size calculation
- Add dynamic chunk resizing when chunk count would exceed 2000
- Attach metadata to every chunk:
  - `file_id`
  - `chunk_index`
  - `source_type`
  - `page_number` where available

### Output

A normalized transcript and a chunk list ready for embeddings and search.

## Phase 7: Embeddings and Vector Store

### Goals

- embed chunks efficiently
- persist vectors with correct similarity configuration

### Tasks

- Implement `storage/vectorstore.py`
- Initialize Chroma in persistent mode
- Explicitly create the collection with cosine distance
- Add startup health check and chunk count logging
- Implement insert and query methods
- Implement `pipeline/embedder.py`
- Batch chunk embedding requests in groups of 500
- Log cost and failures
- Save chunk text plus metadata into Chroma

### Acceptance Criteria

- Application fails early if Chroma cannot be opened
- Embedding failures are surfaced and not ignored
- Stored metadata supports clear search result display

## Phase 8: Hybrid Search

### Goals

- support low-cost and high-recall document search
- keep behavior deterministic and explainable

### Tasks

- Implement `pipeline/search.py`
- Reject queries under 3 characters
- Reject searches when the store has no content
- Accept optional metadata filters before retrieval:
  - `file_id`
  - `source_type`
- Embed the query with `text-embedding-3-small`
- Run semantic retrieval in Chroma for top 10 matches
- Build local BM25 retrieval over stored chunks using `rank_bm25`
- Apply the same metadata filter subset to BM25 before scoring
- Merge semantic and BM25 results using Reciprocal Rank Fusion
- Filter merged results by configurable threshold
- Return the top 5 formatted results with metadata
- Provide `"No relevant content found"` when neither retrieval path returns useful results

### Output

A reusable hybrid search layer callable from the UI without depending on summarization.

## Phase 9: Summarization Pipeline

### Goals

- summarize full documents without truncation
- preserve usability if summarization fails

### Tasks

- Implement `pipeline/summarizer.py`
- Skip summarization for text under 150 characters
- Run map phase:
  - one prompt per chunk
  - 2-3 sentence summary per chunk
- Combine map outputs
- If combined content exceeds the reduce budget:
  - batch into groups of 20
  - generate intermediate summaries
  - run final reduce
- Parse labeled sections:
  - `SUMMARY`
  - `KEY POINTS`
  - `TAGS`
- If parsing fails, store the raw response as fallback
- If the API call fails, mark summary as pending and keep the document searchable

### Acceptance Criteria

- Long documents summarize without silent truncation
- Search remains available during summary failure
- Summary refresh can be added later without redesign

## Phase 10: Streamlit UI

### Goals

- provide an end-to-end user flow
- make status and errors visible
- expose cost and search features

### Tasks

- Implement `app.py`
- Add upload support for PDF, image, and audio
- Show validation errors immediately
- Show processing status transitions:
  - `PENDING`
  - `PROCESSING`
  - `READY`
  - `PARTIAL`
  - `FAILED`
- Display:
  - transcript
  - summary
  - key points
  - tags
  - partial notes
  - search UI
  - cost dashboard
- Allow cached duplicates to return instantly
- Keep the interface simple and operationally clear

### Recommended UI Sections

- Upload panel
- Current file status card
- Transcript viewer
- Summary and tags panel
- Semantic search panel
- Cost tracking panel
- Processing logs or status notes panel

## Phase 11: Error Handling and Status Rules

### Goals

- keep failures understandable
- preserve partial value

### Rules

- Nothing extracted: mark `FAILED`
- Some pages failed but useful text exists: mark `PARTIAL`
- Search available but summary missing: allow `READY` or `PARTIAL` with summary pending metadata
- User-facing messages should be plain English
- Detailed stack traces stay in logs only

## Phase 12: Testing and Verification

### Minimum Test Matrix

- valid text PDF
- scanned PDF requiring vision fallback
- fully image-based PDF
- encrypted PDF
- image with text
- image with no text
- short audio with speech
- silent audio
- audio over 120 minutes
- duplicate upload
- corrupted upload
- long transcript forcing multi-stage reduce
- search query under 3 characters
- empty store search
- search with `file_id` filter
- search with `source_type` filter
- query where only BM25 returns useful matches
- query where only semantic retrieval returns useful matches

### What to Verify

- deduplication prevents duplicate processing
- chunk metadata is stored correctly
- cosine similarity is configured correctly in Chroma
- summarization failure does not break search
- metadata filters are applied before retrieval
- RRF merges semantic and BM25 results deterministically
- costs are logged per operation
- partial extraction notes are shown to the user

## Build Order Recommendation

1. Scaffold project and config.
2. Build file registry and cost logging.
3. Build validator and deduplication.
4. Build quality gate and chunker.
5. Build vector store and embedder.
6. Build hybrid search.
7. Build image ingestion because it is the simplest vision path.
8. Build PDF ingestion next because it reuses vision logic.
9. Build audio ingestion after that because it adds local model complexity.
10. Build summarizer once ingestion plus search are stable.
11. Build Streamlit UI last around proven backend modules.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Vision costs rise on large scanned PDFs | Use strict per-page routing and image resizing |
| Whisper first-run download appears frozen | Log model download explicitly |
| Chroma defaults to wrong distance metric | Set cosine at collection creation and verify at startup |
| Very large documents produce too many chunks | Dynamically raise chunk size to stay under cap |
| Semantic-only search misses exact terms | Add BM25 and merge with RRF |
| Filters produce inconsistent search results | Apply filters before both Chroma and BM25 retrieval |
| Summary parser breaks on format drift | Fall back to storing raw response |
| Partial extraction confuses users | Show exact skipped pages and mark status as `PARTIAL` |

## Definition of Done

The project is complete when:

- uploads for PDF, image, and audio work end to end
- duplicate uploads return cached results
- valid files produce transcript output
- searchable files are embedded into Chroma
- hybrid search returns merged and filtered results with metadata
- long documents can be summarized through map-reduce
- cost logging is visible in the UI
- failures are surfaced clearly without crashing the app

## Step-by-Step Build Prompts

These prompts are intended for use with an AI coding assistant to build the application incrementally.

### Prompt 1: Scaffold the Project

```text
Create the initial project scaffold for a Python Streamlit app called "Content Accessibility Suite" with this structure:

- app.py
- config.py
- utils.py
- ingest/{__init__.py, validator.py, pdf.py, image.py, audio.py}
- pipeline/{__init__.py, quality_gate.py, chunker.py, embedder.py, summarizer.py, search.py}
- storage/{__init__.py, vectorstore.py, filestore.py, cost_log.py}
- data/uploads
- data/registry
- data/logs
- chroma_store
- requirements.txt
- .env.example
- .gitignore

Use Python modules and placeholders with docstrings. In config.py define constants for:
- file size limits
- audio duration limit
- chunk size and overlap
- maximum chunks
- embedding batch size
- similarity threshold
- model names
- chroma path and collection name

Populate requirements.txt with openai, transformers, torch, pydub, pdfplumber, pdf2image, Pillow, chromadb, langchain-text-splitters, tiktoken, streamlit, and python-dotenv.
```

### Prompt 2: Build the File Registry and Cost Logger

```text
Implement storage/filestore.py and storage/cost_log.py for the Content Accessibility Suite.

Requirements for filestore.py:
- persist file metadata locally
- support lookup by md5 hash
- support create/update/get operations
- track file statuses: PENDING, PROCESSING, READY, PARTIAL, FAILED
- store transcript, summary, key_points, tags, partial_notes, and error_message
- keep created_at and updated_at timestamps

Requirements for cost_log.py:
- log every API call with timestamp, file_id, operation_type, model, prompt_tokens, completion_tokens, total_cost_usd, success, and error_message
- compute costs for gpt-4o-mini and text-embedding-3-small using config constants
- support aggregate helpers for session total, per-file totals, and per-operation totals

Use a simple local persistence approach suitable for a small project, and keep the API clean for later use by app.py and pipeline modules.
```

### Prompt 3: Build Upload Validation and Deduplication

```text
Implement ingest/validator.py.

Requirements:
- validate uploaded file is not empty
- enforce size limits: PDF <= 100MB, Image <= 20MB, Audio <= 500MB
- verify extension and MIME type are compatible
- verify the file can be opened
- for audio, verify duration is under 120 minutes
- compute MD5 hash from file bytes
- if md5 already exists in filestore, return cached record immediately

Return a normalized validation result object or dataclass containing:
- is_valid
- source_type
- mime_type
- md5
- error_message
- cached_record

Keep user-facing error messages plain English and do not perform any expensive processing here.
```

### Prompt 4: Build the Quality Gate and Chunker

```text
Implement pipeline/quality_gate.py and pipeline/chunker.py.

For quality_gate.py:
- normalize text to safe UTF-8-compatible output
- replace unreadable characters
- collapse excessive whitespace and blank lines
- trim leading and trailing whitespace
- determine whether summarization should be skipped for text under 150 characters

For chunker.py:
- use RecursiveCharacterTextSplitter
- target 500 token chunks with 50 token overlap
- use tiktoken for token estimation
- if chunk count would exceed 2000, dynamically increase chunk size to stay under the cap
- return chunk objects that include text plus metadata such as file_id, chunk_index, source_type, and page_number when available

Make the code reusable for PDF, image, and audio transcripts.
```

### Prompt 5: Build Chroma Storage and Embeddings

```text
Implement storage/vectorstore.py and pipeline/embedder.py.

Requirements for vectorstore.py:
- initialize a persistent Chroma collection
- explicitly configure cosine distance at collection creation
- verify the store is readable on startup
- log total chunk count
- support insert and query methods

Requirements for embedder.py:
- use OpenAI text-embedding-3-small
- embed chunks in batches of 500
- store chunk text and metadata in Chroma
- log token usage and cost through cost_log.py
- surface API failures instead of swallowing them

Design the interfaces so semantic search can call them later without coupling to summarization.
```

### Prompt 6: Build Hybrid Search

```text
Implement pipeline/search.py.

Requirements:
- reject queries shorter than 3 characters without making an API call
- reject search if the vector store is empty and return a user-friendly message
- support optional metadata filters for file_id and source_type, applied before retrieval
- embed the query with text-embedding-3-small
- query Chroma for top 10 semantic matches
- implement BM25 keyword search locally using rank_bm25 over stored chunk text
- ensure BM25 and Chroma operate on the same filtered subset when filters are provided
- merge semantic and BM25 results with Reciprocal Rank Fusion
- filter merged results using a configurable threshold of 0.35 from config
- return the top 5 passing results with chunk text and metadata
- if no results pass the threshold, return "No relevant content found"

Keep the module independent from summarization and usable directly from the Streamlit UI.
```

### Prompt 7: Build Image Ingestion

```text
Implement ingest/image.py.

Requirements:
- open images with Pillow
- if the longest dimension is greater than 2048px, resize while preserving aspect ratio
- normalize all images to PNG before sending to the model
- call OpenAI gpt-4o-mini vision to extract visible text
- if no text is found, return an empty transcript and mark chunking/embedding as skippable
- log model usage and cost

Return a structured result object that includes transcript text, whether text was found, and any processing notes.
```

### Prompt 8: Build PDF Ingestion with Page-Level Routing

```text
Implement ingest/pdf.py.

Requirements:
- open PDFs with pdfplumber
- reject encrypted PDFs with a clear user-facing error
- process pages one by one
- for each page:
  - use extract_text when available
  - use extract_tables and convert rows to pipe-delimited text
  - inspect page images
  - if the page has embedded images or returns blank text, render the page with pdf2image and send it to gpt-4o-mini vision
- if a page fails, skip it, record its page number, and continue
- if the PDF is fully image-based and every page is blank through pdfplumber, let every page flow through vision fallback automatically
- if total extracted text is under 100 characters, skip summarization later but still allow chunking and embedding
- return transcript text, failed page numbers, partial status, and user-facing partial notes

Keep API calls minimal by only invoking vision when necessary.
```

### Prompt 9: Build Audio Ingestion with Local Whisper

```text
Implement ingest/audio.py.

Requirements:
- load audio with pydub
- identify split points near each 10-minute mark using nearby silence
- split audio at the nearest silence so segments keep sentence boundaries as much as possible
- transcribe segments with a local HuggingFace Whisper pipeline
- concatenate segment transcripts into a full transcript
- if the final transcript is under 20 characters, return a clear no-speech-detected error
- reject corrupted files cleanly
- log when the Whisper model is downloading for the first time so the app does not appear hung

Return a structured result object with transcript text, segment metadata, and any notes or errors.
```

### Prompt 10: Build the Summarization Pipeline

```text
Implement pipeline/summarizer.py.

Requirements:
- skip summarization entirely for transcripts under 150 characters and use the raw text as the summary
- implement map-reduce summarization with OpenAI gpt-4o-mini
- map step: summarize each chunk in 2-3 sentences
- reduce step: combine chunk summaries into:
  - a 150-word summary
  - 5-7 key points
  - 3-5 tags
- require the model to respond with labeled sections: SUMMARY, KEY POINTS, TAGS
- if combined map outputs are too long, batch them into groups of 20, summarize each group, then run a final reduce
- if parsing fails, store the raw response as the summary fallback
- if the API fails, mark the summary as pending but do not break search
- log usage and cost for every call
```

### Prompt 11: Build the Streamlit UI

```text
Implement app.py as the Streamlit entry point for the Content Accessibility Suite.

Requirements:
- support PDF, image, and audio uploads
- run validation and deduplication before processing
- display file status transitions: PENDING, PROCESSING, READY, PARTIAL, FAILED
- orchestrate ingestion, quality gate, chunking, embeddings, optional summarization, and search
- display transcript, summary, key points, tags, partial notes, and user-friendly errors
- provide a semantic search input and show top results with metadata
- provide a cost dashboard showing session total, total cost, and per-file breakdown
- return cached results immediately for duplicate files

Keep the UI simple, clear, and operational rather than decorative.
```

### Prompt 12: Add Final Verification and Hardening

```text
Review the full Content Accessibility Suite implementation and harden it.

Tasks:
- check imports, module boundaries, and circular dependency risks
- add defensive error handling around OpenAI, Chroma, pdfplumber, pydub, and Whisper interactions
- ensure all user-facing errors are plain English
- verify cosine distance is explicitly set in Chroma
- verify deduplication prevents duplicate indexing
- verify summarization failure does not block search
- verify partial PDF failures are surfaced with exact page numbers
- add lightweight tests or validation helpers for the main happy paths and edge cases
- clean up any repeated logic into utility helpers

Do not redesign the architecture. Keep the existing structure and improve reliability.
```

### Prompt 13: Refactor Search into Hybrid Retrieval

```text
Refactor the existing search implementation from semantic-only retrieval into hybrid retrieval while preserving the current module boundaries.

Requirements:
- keep pipeline/search.py as the main public entry point
- add BM25 keyword retrieval using rank_bm25
- preserve the existing Chroma semantic retrieval path
- apply optional metadata filters before both semantic and BM25 retrieval
- merge both ranked lists with Reciprocal Rank Fusion
- keep the existing user-facing response structure as stable as possible
- keep query validation, cost logging, and plain-English error behavior
- avoid redesigning unrelated ingestion or summarization modules

Update config.py and requirements.txt if needed, and make the Streamlit UI use the refactored hybrid search without changing the overall user flow.
```

### Prompt 14: Refactor Shared Helpers and Error Handling

```text
Refactor the existing codebase to reduce duplication and improve reliability without changing the external architecture.

Focus areas:
- centralize repeated helpers for reading upload bytes, extracting chat response text, extracting token usage, and formatting user-facing errors
- keep these helpers in utils.py or another small shared utility module
- update ingest/image.py, ingest/pdf.py, ingest/audio.py, ingest/validator.py, pipeline/summarizer.py, and app.py to use the shared helpers
- ensure user-facing errors remain plain English
- avoid changing the high-level flow or module ownership

Also review imports and module boundaries to avoid circular dependency risks.
```

### Prompt 15: Refactor Vector Store Verification and Search Filters

```text
Refactor the vector and search layers for stronger correctness guarantees.

Requirements:
- verify at startup that the Chroma collection is actually configured with cosine distance
- fail early with a clear error if an existing collection is using a non-cosine metric
- ensure search filters are applied before retrieval, not after
- preserve the current persistent Chroma setup
- keep the public interfaces of storage/vectorstore.py and pipeline/search.py as stable as possible

Add lightweight tests or validation helpers for:
- cosine metric verification
- metadata filter behavior
- empty-store search handling
```

### Prompt 16: Refactor the Streamlit App Around the Final Design

```text
Refactor app.py to align with the final design decisions while keeping the UI simple and operational.

Requirements:
- preserve upload, deduplication, status tracking, transcript display, summary display, search, and cost dashboard
- ensure duplicate uploads return cached results immediately
- ensure status transitions only reflect real processing state, not informational notes
- make hybrid search available with optional file_id and source_type filtering
- surface partial PDF failures exactly as user-facing notes
- keep summarization failure from blocking search
- keep user-facing errors plain English

Do not redesign the app visually. Focus on orchestration, reliability, and clear state handling.
```