# FixIt LLMOps AI Support System

## Project Overview
FixIt is a home services marketplace that handles customer support requests for plumbing, electrical, and cleaning services. This project implements a configuration-driven LLMOps workflow that classifies incoming queries, routes them to the right model tier, loads versioned prompts, tracks AI cost against a monthly budget, and applies deterministic fallback behavior when needed.

The system is modular and testable by design. It now supports real Google AI Studio / Gemini requests through the provider abstraction, while keeping the rest of the architecture provider-agnostic.

## Goals
- Reduce model usage cost by routing simple queries to cheaper tiers
- Keep support quality acceptable through specialized prompts and safe fallbacks
- Externalize behavior through config instead of hardcoding business rules
- Keep the codebase easy to test, debug, and extend

## Architecture Summary
The request flow is orchestrated in [src/main.py](/c:/Users/Dell/Documents/KDU-internship/AI/LLMOps/src/main.py) and is built from small modules with clear responsibilities:

- [src/config_loader.py](/c:/Users/Dell/Documents/KDU-internship/AI/LLMOps/src/config_loader.py): loads and validates YAML config
- [src/classifier.py](/c:/Users/Dell/Documents/KDU-internship/AI/LLMOps/src/classifier.py): deterministic category and complexity classification
- [src/router.py](/c:/Users/Dell/Documents/KDU-internship/AI/LLMOps/src/router.py): model-tier routing based on classification, budget state, and fallback policy
- [src/prompt_manager.py](/c:/Users/Dell/Documents/KDU-internship/AI/LLMOps/src/prompt_manager.py): versioned prompt lookup and prompt fallback
- [src/llm_client.py](/c:/Users/Dell/Documents/KDU-internship/AI/LLMOps/src/llm_client.py): provider-agnostic client with a real Google AI Studio adapter
- [src/cost_tracker.py](/c:/Users/Dell/Documents/KDU-internship/AI/LLMOps/src/cost_tracker.py): request cost estimation and monthly budget tracking
- [src/fallback_handler.py](/c:/Users/Dell/Documents/KDU-internship/AI/LLMOps/src/fallback_handler.py): deterministic fallback policy decisions
- [src/observability.py](/c:/Users/Dell/Documents/KDU-internship/AI/LLMOps/src/observability.py): structured request logging and request tracing

High-level flow:
1. A customer query enters the system.
2. The classifier assigns category and complexity.
3. The cost tracker reports current budget status.
4. The router selects a logical model tier using external config.
5. The prompt manager loads the correct prompt version for the classified category.
6. The LLM client calls the configured Gemini model.
7. Cost is recorded and metadata is returned.
8. If something goes wrong, fallback handling applies a deterministic recovery path.

## Folder Structure
```text
fixit_llmops/
|-- config/
|   |-- classifier.yaml
|   |-- cost_limits.yaml
|   |-- feature_flags.yaml
|   |-- models.yaml
|   |-- prompts.yaml
|   `-- routing.yaml
|-- prompts/
|   |-- booking_v1.txt
|   |-- complaint_v1.txt
|   |-- complaint_v2.txt
|   |-- faq_v1.txt
|   `-- faq_v2.txt
|-- src/
|   |-- classifier.py
|   |-- cli.py
|   |-- config_loader.py
|   |-- cost_tracker.py
|   |-- fallback_handler.py
|   |-- llm_client.py
|   |-- main.py
|   |-- observability.py
|   |-- prompt_manager.py
|   `-- router.py
`-- tests/
    |-- test_classifier.py
    |-- test_config_loader.py
    |-- test_cost_tracker.py
    |-- test_fallback_handler.py
    |-- test_llm_client.py
    |-- test_main.py
    |-- test_observability.py
    |-- test_prompt_manager.py
    `-- test_router.py
```

## Setup Instructions
### Prerequisites
- Python 3.11 or later
- `pytest`
- `PyYAML`

### Install Dependencies
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install pytest pyyaml
```

### Configure Google AI Studio
Set your API key before running the app against real Gemini models:

```powershell
$env:GOOGLE_API_KEY="your-google-ai-studio-api-key"
```

The implementation also accepts `GEMINI_API_KEY`, but `GOOGLE_API_KEY` is the primary documented env var in this repo.

For local runs, the project also auto-loads a repo-root `.env` file if present, so this works too:

```env
GOOGLE_API_KEY=your-google-ai-studio-api-key
```

## Configuration Overview
All major behavior is controlled by files in `config/`.

### `config/models.yaml`
Defines logical model tiers such as `cheap`, `medium`, and `premium`.

Each tier includes:
- provider
- provider model name
- pricing metadata
- timeout values
- whether the tier is enabled

Current Gemini mappings:
- `cheap -> gemini-2.5-flash-lite`
- `medium -> gemini-2.5-flash`
- `premium -> gemini-2.5-flash`

The pricing fields are used for local cost estimation and budget tracking.

### `config/routing.yaml`
Defines routing rules by support category and complexity.

Examples:
- `FAQ + low -> cheap`
- `booking + medium -> medium`
- `complaint + high -> premium`

It also includes:
- low-confidence handling
- unavailable-model fallback
- budget-exceeded fallback
- budget guardrail policies for warning and hard-limit states

### `config/prompts.yaml`
Defines the prompt registry.

Each prompt entry includes:
- `prompt_id`
- `category`
- `current_version`
- `fallback_version`
- intended use
- version-to-file mappings

There is also a `default_prompt` used when the requested prompt cannot be loaded.

### `config/feature_flags.yaml`
Controls optional runtime behavior such as:
- fallback handling
- prompt versioning
- budget guardrails
- request logging

### `config/cost_limits.yaml`
Defines:
- monthly budget
- warning threshold
- hard limit
- target average cost per query

## How the Routing System Works
Routing uses three main inputs:
- classification category
- classification complexity
- current budget status

The router first selects a base model tier from `routing.yaml`. It then adjusts that choice if:
- classification confidence is too low
- premium traffic should be downgraded because the budget is in warning state
- the hard limit has been reached
- the selected model tier is disabled or unavailable

The router returns both the chosen tier and the reason for the decision so routing behavior is traceable during tests and debugging.

## How Prompt Versioning Works
Prompt files live in the `prompts/` directory and are referenced through `config/prompts.yaml`.

The prompt manager supports:
- lookup by category name such as `FAQ` or `booking`
- lookup by `prompt_id` such as `faq`
- using the configured `current_version` through config only
- fallback to a configured version if a requested version is missing
- fallback to the default prompt if a prompt cannot be resolved

This allows prompt content to evolve without changing orchestration logic.

## How Cost Tracking Works
The cost tracker uses pricing metadata from `models.yaml` and budget thresholds from `cost_limits.yaml`.

It provides:
- per-request cost estimation from token counts
- cumulative monthly spend tracking
- budget status reporting as `normal`, `warning`, or `hard_limit`
- monthly summary metadata including remaining budget

Current persistence is in-memory. That is intentional for now and should be replaced later if the system moves to a service or batch-processing environment.

## Logging and Observability
Request observability is handled in [src/observability.py](/c:/Users/Dell/Documents/KDU-internship/AI/LLMOps/src/observability.py).

Each request receives:
- a request ID
- a UTC timestamp
- a structured JSON log entry when logging is enabled

The log entry includes:
- query category
- complexity
- confidence
- selected model tier
- actual model name
- prompt id and version
- latency
- estimated cost
- fallback usage

To reduce unnecessary exposure of customer content, the structured logs do not include the raw query text.

## How to Run Tests
Run the full suite:

```powershell
pytest
```

Run targeted modules:

```powershell
pytest tests/test_llm_client.py
pytest tests/test_main.py
pytest tests/test_router.py
pytest tests/test_cli.py
```

## Interactive CLI
You can manually test the pipeline from the terminal with an interactive CLI.

Start the full pipeline:

```powershell
python -m src.cli
```

Start the routing-only demo mode without live LLM calls:

```powershell
python -m src.cli --no-llm
```

Enable full metadata output for debugging:

```powershell
python -m src.cli --debug
```

### CLI Modes
- Normal mode:
  runs the full pipeline, including live Gemini generation
- `--no-llm` mode:
  skips all live LLM calls, including the secondary classifier, so you can test classification and routing behavior without API spend
- `--debug` mode:
  prints the full metadata structure as pretty JSON after the human-friendly summary

The CLI keeps prompting until you type `exit` or `quit`.

## Example End-to-End Flow
Example query:

```text
My plumber didn't show up and I need a refund.
```

Expected flow:
1. The classifier marks it as `complaint` and `high`.
2. The router chooses the `premium` tier under normal budget conditions.
3. The prompt manager loads the `complaint` prompt, currently `v2`.
4. The LLM client calls the configured Gemini model and captures model metadata and estimated cost.
5. The cost tracker updates monthly spend.
6. The final result includes:
   - customer-facing response text
   - classification metadata
   - routing metadata
   - prompt metadata
   - model metadata
   - cost metadata
   - fallback events if any occurred

## Example Usage
You can call the orchestrator directly from Python:

```python
from src.main import handle_query

result = handle_query("Can I reschedule my cleaning appointment?")
print(result["response_text"])
print(result["metadata"]["route"])
```

## Current Limitations
- The live provider path depends on a configured Google AI Studio API key
- Cost tracking is in-memory only
- The classifier is rules-based and should eventually be supplemented or replaced with stronger evaluation-driven logic
- There is no HTTP API or persistence layer yet

## Suggested Next Steps
- Move monthly cost storage into a persistent backend
- Add an API layer or worker entry point
- Add dashboards or metrics export for operational monitoring
- Add prompt A/B testing and evaluation datasets
