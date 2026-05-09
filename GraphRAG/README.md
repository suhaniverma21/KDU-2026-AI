# GraphRAG for Multi-Hop Reasoning

This project implements a three-phase GraphRAG workflow for answering multi-hop corporate ownership questions from a document.

Target question:

`Who is the ultimate parent company of the organization John Smith works for?`

## Phases

### Phase 1

Build a basic vector RAG baseline with:

- fixed-size chunking
- ChromaDB
- semantic retrieval

Goal:

- show why vector-only RAG fails on multi-hop relationship questions

### Phase 2

Extract structured triples from the document and build a knowledge graph in Neo4j.

Goal:

- preserve ownership and executive relationships explicitly

### Phase 3

Generate Cypher from a user question, query Neo4j, retrieve the graph path, and use that path to produce a grounded final answer.

Goal:

- answer the multi-hop question using graph traversal plus lightweight LLM reasoning

## Project Structure

```text
GraphRAG/
  data/
  outputs/
  src/
    phase1/
    phase2/
    phase3/
    utils.py
  context.md
  design-doc.md
  implementation-plan.md
  phase2-implementation-plan.md
  phase3-implementation-plan.md
```

## Key Files

### Source

- [src/phase1](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/src/phase1)
- [src/phase2](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/src/phase2)
- [src/phase3](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/src/phase3)
- [src/utils.py](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/src/utils.py)

### Docs

- [context.md](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/context.md)
- [design-doc.md](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/design-doc.md)
- [implementation-plan.md](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/implementation-plan.md)
- [phase2-implementation-plan.md](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/phase2-implementation-plan.md)
- [phase3-implementation-plan.md](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/phase3-implementation-plan.md)

### Main Outputs

- [outputs/phase1_report.md](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/outputs/phase1_report.md)
- [outputs/phase2_report.md](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/outputs/phase2_report.md)
- [outputs/phase2_graph.png](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/outputs/phase2_graph.png)
- [outputs/phase3_report.md](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/outputs/phase3_report.md)
- [outputs/phase3_answer.md](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/outputs/phase3_answer.md)

## Requirements

Python 3.11+

Install Neo4j driver if needed:

```powershell
pip install neo4j
```

## Environment Variables

This project reads configuration from `.env` at runtime.

Example variables are listed in:

- [.env.example](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/.env.example)

Main variables:

- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL`
- `PHASE2_LLM_MODEL`
- `PHASE3_LLM_MODEL`
- `NEO4J_URI`
- `NEO4J_USERNAME`
- `NEO4J_PASSWORD`

Recommended lightweight model:

- `meta-llama/llama-3.1-8b-instruct`

## Running the Project

### Phase 1

```powershell
python src/phase1/phase1_ingest.py --pdf-path data/corporate-doc.pdf
python src/phase1/phase1_eval.py --top-k 3
```

### Phase 2

```powershell
python src/phase2/phase2_extract.py --pdf-path data/corporate-doc.pdf --allow-repair
python src/phase2/phase2_graph.py
python src/phase2/phase2_neo4j.py
python src/phase2/phase2_visualize.py
python src/phase2/phase2_report.py
```

### Phase 3

```powershell
python src/phase3/phase3_eval.py
```

## Generated Evidence

### Phase 1 Evidence

- chunked retrieval baseline
- retrieval logs
- failure analysis report

Files:

- [outputs/chunks.json](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/outputs/chunks.json)
- [outputs/retrieval_results.json](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/outputs/retrieval_results.json)
- [outputs/phase1_report.md](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/outputs/phase1_report.md)

### Phase 2 Evidence

- extracted triples
- normalized graph payload
- Neo4j-backed graph screenshot
- entity-resolution report

Files:

- [outputs/triples.json](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/outputs/triples.json)
- [outputs/graph_nodes_edges.json](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/outputs/graph_nodes_edges.json)
- [outputs/entity_aliases.json](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/outputs/entity_aliases.json)
- [outputs/phase2_graph.png](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/outputs/phase2_graph.png)
- [outputs/phase2_report.md](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/outputs/phase2_report.md)

### Phase 3 Evidence

- generated Cypher
- corrected Cypher after retry
- graph path
- final grounded answer

Files:

- [outputs/phase3_query_result.json](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/outputs/phase3_query_result.json)
- [outputs/phase3_answer.md](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/outputs/phase3_answer.md)
- [outputs/phase3_report.md](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/outputs/phase3_report.md)

## Design Notes

- Phase 1 intentionally uses a simple baseline so the multi-hop blindspot is visible.
- Phase 2 uses page-level extraction instead of fixed chunks to preserve relationship context.
- Phase 3 uses Neo4j as the source of truth and allows one retry for Cypher correction.
- The final answer is grounded in the returned graph path rather than raw full-document context.

## Submission-Oriented Files

If you need the most important files for submission, start with:

- [outputs/phase1_report.md](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/outputs/phase1_report.md)
- [outputs/phase2_report.md](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/outputs/phase2_report.md)
- [outputs/phase2_graph.png](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/outputs/phase2_graph.png)
- [outputs/phase3_report.md](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/outputs/phase3_report.md)
- [outputs/phase3_answer.md](C:/Users/Dell/Documents/KDU-internship/AI/GraphRAG/outputs/phase3_answer.md)
