# Content Accessibility Suite — Design Document

**Project:** Multi-Modal Content Accessibility Platform
**Stack:** OpenAI API · HuggingFace Transformers · Chroma · Streamlit
**Scope:** 2-day cohort project, production-grade design
**Priority:** Low cost · Minimal API calls · Clear architecture

---

## 1. Problem Summary

Build a system that accepts PDFs, images, and audio files and makes their content accessible through a clean text transcript, an AI-generated summary, key points, topic tags, and semantic search.

All three file types converge on the same processing pipeline after ingestion. The system must handle real-world edge cases — scanned documents, long files, corrupted uploads, duplicates — without crashing or silently producing bad output.

---

## 2. System Overview

```
  [User uploads file]
          |
          v
  [Validate + Deduplicate] --duplicate?--> return cached result
          |
          |
    .-----+-----.
    |     |     |
   PDF  Image Audio
    |     |     |
    '-----+-----'
          |
          v
   [Raw Text String]
          |
          v
  [Text Quality Check]
          |
          v
      [Chunking]
      500 tok, 50 tok overlap
          |
     .----+----.
     |         |
     v         v
  SEARCH    SUMMARY
  PIPELINE  PIPELINE
     |         |
  Embed     Map: one LLM
  chunks    call per chunk
     |         |
  Store in  Reduce: combine
  Chroma    into summary
     |       + bullets + tags
  Query        |
  on demand  Cache result
```

The two pipelines after chunking are fully independent. A failure in one does not affect the other.

---

## 3. File Validation

Every upload passes through this gate before any processing. Fail fast here to avoid wasting API calls on bad input.

| Check | Failure Action |
|---|---|
| File is not empty | "No file received" |
| File size within limit (PDF ≤ 100MB, Image ≤ 20MB, Audio ≤ 500MB) | Error with size limit |
| File extension matches MIME type | "File type mismatch" |
| File opens without exception | "File is corrupted or unreadable" |
| Audio duration under 120 minutes | "Audio file exceeds 120 minute limit" |
| MD5 hash not seen before | Return cached result if duplicate |

If the MD5 hash already exists in the file registry, the existing transcript, summary, and search index are returned immediately. The pipeline does not run again.

---

## 4. PDF Ingestion

### 4.1 Page-level routing

```
For each page:
        │
        ├─ page.images found?
        │       YES → render page as image → GPT-4o-mini vision call
        │
        ├─ page.extract_tables() found?
        │       YES → convert rows to pipe-delimited plain text (free)
        │
        ├─ page.extract_text() returns content?
        │       YES → use pdfplumber text directly (free)
        │
        └─ page returns nothing (scanned)?
                YES → GPT-4o-mini vision call
```

Vision is called only when a page has an embedded image or is fully blank. Text-only and table-only pages are free.

### 4.2 Edge cases

**Fully image-based PDF (scanned document):** pdfplumber returns empty text on every page. Every page hits the vision fallback automatically — no special handling needed. The system processes it correctly, it just makes one vision call per page. This is the most expensive document type the system will encounter.

**Encrypted PDF:** Cannot be opened. Return a user-facing error and do not proceed.

**Per-page extraction failure:** Skip the failed page, continue with the rest of the document, and record the page number. On completion, tell the user exactly which pages failed — e.g. *"Pages 4, 7, 12 could not be extracted."* Mark the file as PARTIAL.

**Very short total extracted text:** If total extracted text across all pages is under 100 characters, skip summarization and store the raw text as-is. The text is still chunked and embedded for search.

### 4.3 Known limitations

- Vector graphics and charts drawn with PDF drawing commands are not detected by pdfplumber and will not be extracted.
- Complex tables with merged cells may lose structure when converted to plain text rows.
- In production, replace pdfplumber with AWS Textract or Azure Document Intelligence.

---

## 5. Image Ingestion

```
Open with Pillow
       │
       ├─ longest dimension > 2048px?
       │       YES → resize down, preserve aspect ratio
       │
       ├─ Convert to PNG (normalises all formats)
       │
       └─ Send to GPT-4o-mini vision
               │
               ├─ Text found? → store transcript, proceed to chunking
               └─ No text?   → store empty transcript, skip chunking + embedding
```

### Edge cases

**Oversized image:** Resized to max 2048px on the longest dimension before sending. Controls vision tiling cost.

**No text in image:** Detected from the vision response. Transcript stored as empty. Chunking and embedding are skipped.

**Unsupported format:** All images normalized to PNG via Pillow. Handles BMP, TIFF, WebP, and others.

---

## 6. Audio Ingestion

```
Load with pydub
       │
       └─ Find silence near every 10-minute mark → split there
               │
               └─ Transcribe each segment with local Whisper (HuggingFace)
                       │
                       └─ Concatenate all segments → full transcript
```

Splitting at silence near the 10-minute mark rather than exactly at 10 minutes ensures Whisper always receives complete sentences at segment boundaries. Cutting mid-sentence would cause Whisper to produce broken transcriptions at the start and end of each segment.

### Edge cases

**Corrupted file:** Return a clear error immediately. Do not proceed.

**Silent audio:** If the full concatenated transcript is under 20 characters, return an error indicating no speech was detected. Do not proceed to chunking.

**First run model download:** Whisper downloads approximately 140MB on first run. Log this explicitly so it does not appear as a hang.

---

## 7. Text Quality Check

Runs after every ingestion path before chunking.

| Check | Action |
|---|---|
| Total length under 150 characters | Skip summarization. Store text as-is. Still chunk and embed. 150 characters is approximately 2-3 short sentences — below this the LLM call adds no value over just showing the raw text directly. |
| Encoding issues | Normalize to UTF-8, replacing unreadable characters. |
| Excessive whitespace | Collapse multiple blank lines, strip leading and trailing whitespace. |

---

## 8. Chunking

**Parameters:** 500 token chunk size · 50 token overlap · RecursiveCharacterTextSplitter

```
Raw text
   │
   └─ Split on paragraphs → sentences → words (in order)
           │
           ├─ chunk_0  [metadata: file_id, chunk_index, source_type, page_number]
           ├─ chunk_1
           ├─ chunk_2  ← 50-token overlap with chunk_1 and chunk_3
           └─ ...
```

**Edge case — document shorter than one chunk:** Produces a single chunk. No special handling needed.

**Edge case — very large document:** If total chunks would exceed 2000, chunk size is increased dynamically to stay within the cap.

**Production upgrade path (not implemented — cost constraints):**
- Parent-child chunking: small chunks for precise retrieval, larger parent chunks returned as results
- HyDE: embed a hypothetical answer to the query instead of the raw query string

---

## 9. Embedding

**Model:** text-embedding-3-small · 1536 dimensions · $0.02 per million tokens

Chunks are sent to the embeddings API in batches of 500.

**Edge case — API failure:** Surface the error to the user. Do not proceed.

---

## 10. Vector Store

**Choice:** Chroma · persistent mode · cosine distance explicitly set

Cosine distance must be set explicitly at collection creation — Chroma defaults to L2 which is wrong for text embeddings.

On application start, verify the store is readable and log the total chunk count. Raise an error immediately if unreadable.

---

## 11. Hybrid Search

Hybrid search combines two retrieval methods and merges their results. Semantic search alone misses exact keyword matches — for example searching "GPT-4o-mini" would not reliably find that exact string through embeddings alone. Keyword search alone misses conceptually related content. Combining both gives better results than either individually.

```
User query + optional metadata filter
     │
     ├─ Under 3 characters? → reject, no API call
     │
     ├─ Store empty? → tell user to upload a file first, no API call
     │
     ├─ Apply metadata filter (optional, free)
     │       filter by file_id  → search only within one document
     │       filter by source_type → search only pdfs / images / audio
     │       no filter → search across everything
     │
     ├──────────────────────────────────────┐
     │                                      │
     v                                      v
SEMANTIC SEARCH                      KEYWORD SEARCH
Embed query                          BM25 over all
(text-embedding-3-small)             stored chunks
     │                                      │
Cosine similarity                    Exact + fuzzy
search in Chroma                     term matching
(top 10)                             (top 10)
     │                                      │
     └──────────────┬───────────────────────┘
                    │
             [RRF Merge]
        Reciprocal Rank Fusion
        combines both result lists
                    │
             Filter: score ≥ 0.35
                    │
             Return top 5 results
             with chunk text + metadata
```

**Reciprocal Rank Fusion (RRF):** Each result is scored based on its rank position in both lists. A result appearing in the top 3 of both semantic and keyword search scores higher than one appearing in only one list. No additional API call needed — purely a mathematical merge of two ranked lists.

**BM25 for keyword search:** BM25 is a standard keyword ranking algorithm. It runs entirely locally with no API cost. Library: `rank_bm25`.

**Metadata filters:** Filters are applied before search runs, not after. Chroma accepts a `where` clause that narrows the chunk pool before similarity search. BM25 applies the same filter to its index. Both methods search the same filtered subset so RRF results are consistent. `page_number` and `chunk_index` are not exposed as filters — they exist for display and attribution in results only.

**Edge cases**

**No results from either method:** Tell the user no relevant content was found.

**Results from only one method:** Return those results as-is. RRF handles the case where one list is empty gracefully.

The similarity threshold of 0.35 applies to the merged results. It is a config value, not hardcoded, as different document types have different score distributions.

---

## 12. Summarization

```
All chunks from document
        │
        └─ MAP: one LLM call per chunk
                │   "Summarize in 2-3 sentences"
                ├─ chunk_0 → mini_summary_0
                ├─ chunk_1 → mini_summary_1
                └─ ...
                        │
                        └─ [if combined summaries > 4000 tokens]
                                → batch into groups of 20
                                → intermediate reduce per group
                                → final reduce across groups
                        │
                        └─ REDUCE: one final LLM call
                                │   "Combine into 150-word summary
                                │    + 5-7 key points + 3-5 tags"
                                └─ Cache result
```

### Edge cases

**Summarization API failure:** Mark the summary as pending. The file remains fully searchable.

**Document under 150 characters:** Skip map-reduce entirely. Store the raw text as the summary.

**Caching:** Summary is stored after first generation and never re-run unless the user explicitly requests a refresh.

### Response parsing

The LLM is prompted to respond with labelled sections: SUMMARY, KEY POINTS, TAGS. The parser splits on these labels. If parsing fails for any reason, the raw response is stored as the summary so the user always gets something useful.

---

## 13. Cost Tracking

Every API call is logged with: timestamp, file ID, operation type, model, prompt tokens, completion tokens, computed cost in USD, and success status. Failures are logged with the error message.

**Cost rates:**

| Model | Input | Output |
|---|---|---|
| gpt-4o-mini | $0.15 / 1M tokens | $0.60 / 1M tokens |
| text-embedding-3-small | $0.02 / 1M tokens | — |

**UI surfaces:** total cost across all files · per-file cost by operation type · running session total.

---

## 15. File Status

```
PENDING → PROCESSING → READY
                     → PARTIAL  (some content skipped, search still works)
                     → FAILED   (nothing extracted, search unavailable)
```

| Status | Meaning |
|---|---|
| PENDING | Uploaded, not yet processed |
| PROCESSING | Pipeline currently running |
| READY | Fully processed, search and summary available |
| PARTIAL | Processed with some pages or content skipped. User told exactly what was skipped. |
| FAILED | Nothing was extracted. Search unavailable. |

User-facing errors are always plain English. Internal exceptions stay in logs only.

---

## 16. Project File Structure

```
accessibility_suite/
├── app.py                      # Streamlit entry point
│
├── ingest/
│   ├── validator.py            # File validation + deduplication
│   ├── pdf.py                  # pdfplumber + per-page vision routing
│   ├── image.py                # Pillow resize + GPT-4o-mini vision
│   └── audio.py                # pydub segmentation + local Whisper
│
├── pipeline/
│   ├── quality_gate.py         # Post-ingestion text normalization
│   ├── chunker.py              # RecursiveCharacterTextSplitter
│   ├── embedder.py             # Batched text-embedding-3-small
│   ├── summarizer.py           # Map-reduce summarization
│   └── search.py               # Query embed + Chroma similarity search
│
├── storage/
│   ├── vectorstore.py          # Chroma init, insert, query, startup check
│   ├── filestore.py            # File records, status tracking, summary cache
│   └── cost_log.py             # API call logging + cost computation
│
├── chroma_store/               # Chroma persistent storage (gitignored)
├── requirements.txt
├── .env                        # OPENAI_API_KEY (gitignored)
└── .gitignore
```

---

## 17. Dependencies

| Package | Purpose |
|---|---|
| rank_bm25 | BM25 keyword search for hybrid retrieval |
| openai | GPT-4o-mini vision, summarization, embeddings |
| transformers | Local Whisper model via HuggingFace |
| torch | Required by transformers |
| pydub | Audio segmentation into 10-minute chunks |
| pdfplumber | PDF text and table extraction |
| pdf2image | Render PDF pages to images for vision fallback |
| Pillow | Image open, resize, format normalization |
| chromadb | Local persistent vector store |
| langchain-text-splitters | RecursiveCharacterTextSplitter |
| tiktoken | Token counting for chunk size calculation |
| streamlit | UI |
| python-dotenv | Environment variable management |

---

## 18. Known Limitations

- Vector graphics and charts drawn with PDF drawing commands are not detected and will not be extracted.
- Complex tables with merged cells lose formatting when converted to plain text rows. Data is preserved, structure is not.
- Audio files over 120 minutes are rejected.
- Parent-child chunking and HyDE are excluded due to cost constraints. These are the first additions for a production upgrade.
- In production, replace pdfplumber with AWS Textract or Azure Document Intelligence for full document fidelity.

---

## 19. Major Design Decisions

**Use local Whisper instead of OpenAI Whisper API**
The local HuggingFace model produces identical output to the API because it uses the same model weights. The API costs $0.006/minute — the local model is free. At development scale with many test runs, this is the only sensible choice.

**Per-page vision routing for PDFs**
Vision is only called when pdfplumber detects an embedded image on a page or the page returns blank text. Text-only and table-only pages never trigger a vision call. Cost is proportional to actual need, not document length.

**MD5 deduplication as the only deduplication layer**
Hashing file bytes at upload time catches all duplicates before processing begins. This guarantee means the vector store never needs a delete-before-insert step — a file that reaches the store is always new.

**Map-reduce for summarization instead of truncation**
Truncation silently drops content. Map-reduce covers the full document regardless of length by summarizing each chunk individually then combining the results. If the combined chunk summaries themselves are too large for the reduce call, they are batched into intermediate groups before the final reduce.

**Chroma with cosine distance instead of the default L2**
L2 distance is sensitive to vector magnitude. Cosine similarity measures the angle between vectors and is the correct metric for semantic text similarity. Chroma defaults to L2 so cosine must be set explicitly at collection creation.

**Two independent pipelines after chunking**
Search and summarization are decoupled after chunking. A summarization failure does not make the file unsearchable and vice versa. A partial failure always leaves the user with something useful.

**Fixed-size chunking over parent-child or semantic chunking**
Parent-child chunking and HyDE would improve retrieval quality but add LLM calls per search query. Given the constraint of minimal API calls, fixed-size chunking with overlap is the correct tradeoff for this scope.

**Metadata filters applied before search, not after**
Filtering after search would mean running similarity across the entire chunk store and then discarding irrelevant results — wasteful. Applying the filter as a Chroma `where` clause before search narrows the chunk pool first so both semantic and BM25 search run on a smaller, relevant subset. Free, no API call, and more efficient.

**Hybrid search over semantic-only search**
Semantic search alone misses exact keyword matches — searching for a specific model name, version number, or proper noun may not surface the right chunks purely through vector similarity. BM25 keyword search catches these exact matches. Combining both via RRF produces better results than either individually. BM25 runs entirely locally with no API cost so it adds retrieval quality at zero extra expense.

**PARTIAL status distinct from FAILED**
A file where only some pages failed extraction is still largely useful. PARTIAL communicates that the file is searchable but incomplete. The UI tells the user exactly which pages were skipped and why.

**Similarity threshold as a config value**
The 0.35 cosine similarity threshold is defined in config.py, not hardcoded. Different document types have different similarity distributions and the threshold needs to be tunable without a code change.