# CrewAI Lab

This project currently implements Phase 1, Phase 2, and Phase 3 of the CrewAI lab:

- YAML-configured agents and tasks
- Sequential and hierarchical orchestration
- A flaky custom tool that raises `TimeoutError` about 50% of the time
- Run artifact capture for comparison
- Shared memory with explicit storage and inspection artifacts
- An intentional agent-vs-task contradiction for instruction-priority testing
- A CrewAI Flow with structured state, conditional routing, and loop guardrails

## Quick Start

1. Create a virtual environment.
2. Install dependencies from `pyproject.toml`.
3. Set environment variables:

```env
OPENAI_API_KEY=...
SERPER_API_KEY=...
MODEL_NAME=gpt-4o-mini
MANAGER_MODEL_NAME=gpt-4o-mini
```

## Run

```bash
python -m crewai_lab.main --topic "Impact of small language models in enterprise search" --mode compare
python -m crewai_lab.main --topic "Impact of small language models in enterprise search" --mode compare --memory --day-label day1
python -m crewai_lab.main --topic "Continue the prior analysis on small language models in enterprise search" --mode compare --memory --day-label day2
python -m crewai_lab.flow_app --topic "Impact of small language models in enterprise search" --max-revisions 2
```
