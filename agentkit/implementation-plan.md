# Implementation Plan: AgentKit Orchestration, Loop Detection, and Memory Compaction

## Goal
Build a low-cost, production-style multi-agent system using the OpenAI Agents SDK that demonstrates:

- loop detection and circuit breaking
- domain-isolated sub-agents
- structured context passing during handoff
- persistent memory with compaction
- planner-executor orchestration

This plan is organized so each phase is independently testable, while sharing a common runtime and memory layer.

## Recommended Tech Stack

- Language: Python 3.11+
- SDK: OpenAI Agents SDK
- Models:
  - `o3-mini` for reasoning-heavy coordination/planning where explicitly required
  - `gpt-4o-mini` for low-cost execution and general responses
  - fallback provider abstraction for OpenRouter if OpenAI is unavailable
- Storage:
  - SQLite for persistent session state, event logs, case facts, and execution traces
  - JSON files only for local fixtures and sample inputs
- Observability:
  - structured JSON logging
  - per-run trace IDs
  - per-agent step counters

## Proposed Project Structure

```text
agentkit/
  implementation-plan.md
  app/
    main.py
    config.py
    runtime.py
    logging_utils.py
    models/
      schemas.py
      state.py
    tools/
      internal_db.py
      finance_tools.py
      hr_tools.py
      delegation_tools.py
    agents/
      single_agent.py
      coordinator.py
      finance_agent.py
      hr_agent.py
      planner_agent.py
      executor_agent.py
    orchestration/
      circuit_breaker.py
      handoff.py
      planner_executor.py
      retry_policy.py
    memory/
      session_store.py
      compaction.py
      case_facts.py
      flags.py
    fixtures/
      sample_transactions.txt
      sample_employees.json
  tests/
    test_phase1_loop_detection.py
    test_phase2_isolation.py
    test_phase3_context_passing.py
    test_phase4_memory_compaction.py
    test_phase5_planner_executor.py
```

## Shared Architecture

Before phase-by-phase implementation, build the following shared foundations.

### 1. Runtime Layer

- Create a `RuntimeContext` object containing:
  - `session_id`
  - `user_id`
  - `trace_id`
  - `active_agent`
  - `shared_memory_ref`
  - `failure_counters`
  - `flags`
- This becomes the canonical state object passed through orchestration code.

### 2. Tool Interface Standard

Every tool should return a structured envelope:

```json
{
  "ok": true,
  "data": {},
  "error": null,
  "retryable": false,
  "tool_name": "example_tool"
}
```

For failures:

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "HTTP_500",
    "message": "Internal database unavailable"
  },
  "retryable": true,
  "tool_name": "query_internal_database"
}
```

This structure is critical for circuit breaking and handoff reliability.

### 3. Session Persistence

Persist the following tables in SQLite:

- `sessions`
- `agent_runs`
- `tool_calls`
- `handoffs`
- `case_facts`
- `memory_snapshots`
- `flags`

### 4. Observability

Log every important event with:

- timestamp
- session_id
- trace_id
- agent_name
- event_type
- step_index
- payload_summary

Key event types:

- `agent_started`
- `tool_called`
- `tool_failed`
- `loop_detected`
- `circuit_opened`
- `handoff_started`
- `handoff_completed`
- `memory_compacted`
- `missing_required_field`
- `plan_generated`
- `step_executed`

## Phase 1: Loop Detection and Circuit Breaker

### Objective

Demonstrate how a single agent behaves when a retryable tool fails repeatedly, then add safeguards to stop infinite loops.

### Scope

- Single agent using `o3-mini`
- Tool: `query_internal_database`
- Simulated failure: always return 500
- Prompt: `Count the active users`

### Implementation Steps

1. Create `query_internal_database` as a mock tool.
   - Input: SQL-like question or semantic query string
   - Behavior for this phase: always fail with `HTTP_500`
   - Mark as `retryable: true`

2. Create `single_agent.py`.
   - Register only this tool
   - Use a prompt that encourages tool use for data lookup

3. Instrument tool-call counting.
   - Count consecutive failures for the same tool within a run
   - Count total calls and repeated identical requests

4. Implement a loop detector in `orchestration/circuit_breaker.py`.
   - Open circuit after `3` consecutive failures
   - Detect repeated same-tool same-input pattern
   - Write `loop_detected` and `circuit_opened` log events

5. Return a graceful fallback message.
   - Example behavior:
     - stop agent execution
     - return: `I’m unable to access the internal user database right now. Please try again later or contact support.`

### Retry Measurement

To answer “How many retries does the agent attempt before stopping?”:

- first run the phase without circuit breaker instrumentation
- log raw retry attempts
- then enable circuit breaker
- final enforced rule: stop after 3 consecutive failures

Note:
Actual raw retry count may vary depending on SDK/runtime behavior, so measure it empirically in code rather than hardcoding assumptions.

### Circuit Breaker Design

Suggested state:

```python
{
    "tool_name": "query_internal_database",
    "consecutive_failures": 3,
    "circuit_state": "open",
    "last_error_code": "HTTP_500"
}
```

### Acceptance Criteria

- agent attempts tool usage
- repeated failures are detected
- execution stops after 3 consecutive failures
- user receives fallback response
- logs clearly show loop detection and circuit opening

## Phase 2: Coordinator and Agent Isolation

### Objective

Build a multi-agent system with a Coordinator that delegates instead of directly owning business tools.

### Agents

- `Coordinator Agent`
- `Finance Agent`
- `HR Agent`

### Tool Isolation Rules

Coordinator tools:

- `delegate_to_finance`
- `delegate_to_hr`
- optional `respond_to_user`

Finance tools:

- `get_salary(employee_name)`
- `update_banking_details(...)`

HR tools:

- `get_pto_balance(employee_name)`

Do not attach finance or HR tools directly to the Coordinator.

### Implementation Steps

1. Build the Finance and HR agents as isolated specialists.
2. Build delegation wrappers in `tools/delegation_tools.py`.
3. Coordinator receives the user request and decides task decomposition.
4. For cross-domain questions, Coordinator sequences handoffs and combines outputs.

### Example Query

User asks:
`What is John’s salary and how much PTO does he have?`

Expected sequence:

1. Coordinator identifies two domain-specific intents:
   - salary lookup -> Finance
   - PTO lookup -> HR
2. Coordinator invokes Finance handoff with minimal payload.
3. Coordinator stores Finance result.
4. Coordinator invokes HR handoff with minimal payload.
5. Coordinator merges both results into a single user-facing answer.

### Why Isolation Matters

#### Reducing Prompt Bloat

- Coordinator prompt stays small
- tool schema list is shorter
- less irrelevant tool description text gets sent to the model
- lower cost and lower routing confusion

#### Improving Reliability

- fewer tool choices reduces incorrect calls
- domain prompts stay specialized
- easier testing and debugging
- failures are contained to a sub-agent boundary

### Acceptance Criteria

- Coordinator has no direct salary/PTO tools
- Finance and HR only expose domain-relevant tools
- mixed-domain query is answered through delegation
- logs show delegation order and merged result

## Phase 3: Context Passing Between Agents

### Objective

Pass only the relevant context during handoff instead of full conversation history.

### Example Query

`Update my banking details. Routing number is 123456789.`

Coordinator should transfer to Finance Agent.

### Core Problem

Sub-agents should not automatically receive the entire chat transcript. They should receive a structured payload built by orchestration.

### Structured Context Payload

Define a handoff schema in `models/schemas.py`:

```json
{
  "session_id": "sess_123",
  "user_id": "user_456",
  "source_agent": "coordinator",
  "target_agent": "finance",
  "task_type": "update_banking_details",
  "user_intent": "Update banking details",
  "entities": {
    "routing_number": "123456789"
  },
  "required_fields": [
    "routing_number",
    "account_number",
    "account_holder_name"
  ],
  "case_facts_ref": "case_789"
}
```

### Implementation Steps

1. Create a `build_handoff_payload()` helper in `orchestration/handoff.py`.
2. Extract only the current intent and required entities.
3. Strip unrelated messages like greetings, confirmations, and older topics.
4. Pass the payload as structured input to Finance Agent.
5. Finance Agent validates required fields before performing action.

### Ensuring Only Relevant Data is Passed

Use a whitelist approach:

- include:
  - current task
  - extracted entities
  - references to persisted memory
  - required-field checklist
- exclude:
  - full raw transcript
  - prior unrelated requests
  - tool traces from other domains

### Acceptance Criteria

- Coordinator hands off a structured payload
- Finance Agent can act without full chat history
- unrelated conversation is not forwarded
- missing required fields are detectable from payload alone

## Phase 4: Memory Compaction and Case Facts

### Objective

Preserve critical transactional details even when conversation memory is compacted or summarized.

### Problem

A long input document plus trivial follow-up chat can push important details out of active context. Naive summarization may drop:

- order IDs
- account numbers
- amounts
- dates
- routing numbers
- CVV or other required fields

### Strategy

Use dual memory:

1. Conversational summary memory
   - compact natural-language summary for general context
2. Structured case facts memory
   - loss-resistant store for exact facts and required fields

### Case Facts Dictionary

Example structure:

```json
{
  "customer_name": "Jane Doe",
  "transactions": [
    {
      "transaction_id": "TXN-10045",
      "order_id": "ORD-77881",
      "amount": 249.99,
      "currency": "USD",
      "date": "2026-04-30"
    }
  ],
  "banking_details": {
    "routing_number": "123456789",
    "account_number": null,
    "cvv": null
  },
  "required_fields_status": {
    "routing_number": "present",
    "account_number": "missing",
    "cvv": "missing"
  }
}
```

### Extraction Pipeline

Implement in `memory/compaction.py` and `memory/case_facts.py`:

1. ingest large document
2. run structured extraction pass
3. identify:
   - numerical data
   - transaction IDs
   - order IDs
   - amounts
   - dates
   - banking fields
4. write extracted values into `case_facts`
5. generate compact summary separately
6. persist both

### Flagging Mechanism

Implement `memory/flags.py`:

- if required fields for an action are missing:
  - create flag entry
  - mark session state as `requires_user_input`

Example:

```json
{
  "flag_type": "missing_required_field",
  "field": "cvv",
  "status": "open",
  "session_state": "requires_user_input"
}
```

### Why This Prevents Data Loss

- exact values are stored outside the compressed chat summary
- critical facts remain queryable even if chat context shrinks
- downstream agents read stable structured memory instead of relying on raw transcript recall

### Why This Prevents Context Degradation

- noisy follow-up messages do not overwrite important state
- summaries stay short while details live in case facts
- agents retrieve only facts relevant to the current action

### Acceptance Criteria

- long document can be ingested
- transactional facts are extracted into structured storage
- summary compaction does not erase important numeric details
- missing required fields create flags
- session can pause safely for user input

## Phase 5: Hybrid Planner-Executor Workflow

### Objective

Separate reasoning/planning from action execution to improve consistency and control.

### Agents

- `Planner Agent` using `o3-mini`
- `Executor Agent` using `gpt-4o-mini` or `gpt-4o` if explicitly needed

### Workflow

1. Planner receives user objective
2. Planner outputs structured JSON plan
3. Executor reads the plan plus current memory snapshot
4. Executor executes step-by-step
5. Results are written back to shared state after each step

### Planner Output Schema

```json
{
  "goal": "Process a user request safely",
  "steps": [
    {
      "step_id": "step_1",
      "action": "validate_input",
      "agent": "executor",
      "depends_on": [],
      "expected_output": "validated fields"
    },
    {
      "step_id": "step_2",
      "action": "call_finance_tool",
      "agent": "executor",
      "depends_on": ["step_1"],
      "expected_output": "bank update result"
    }
  ],
  "success_criteria": [
    "all required fields present",
    "tool response persisted"
  ]
}
```

### Passing Memory Between Planner and Executor

Do not pass raw transcript. Pass a structured execution bundle:

```json
{
  "plan": { "...": "..." },
  "session_summary": "User wants banking details updated.",
  "case_facts": { "...": "..." },
  "flags": [],
  "completed_steps": [],
  "trace_id": "trace_123"
}
```

### Maintaining Consistency Across Steps

- assign each step a `step_id`
- persist step outputs after execution
- maintain `completed_steps` and `pending_steps`
- re-read canonical session memory before each next action
- do not rely on model memory alone

Suggested executor loop:

1. load current execution state
2. find next unblocked step
3. execute
4. persist result
5. update flags/errors
6. continue or stop

### Biggest Architectural Advantage

Planner-Executor is stronger than raw API chaining because:

- planning becomes explicit and inspectable
- execution becomes deterministic and stateful
- failures can resume from a known step
- reasoning is separated from tool use
- validation, guardrails, and audits are easier to enforce

Raw API chaining is simpler, but it hides intent and makes retries/resume logic much harder.

### Acceptance Criteria

- Planner emits valid structured JSON
- Executor can execute each step from plan state
- memory persists between steps
- interrupted runs can resume from stored step state
- logs show plan generation and step execution lifecycle

## Cross-Phase Build Order

Implement in this order:

1. shared runtime, schemas, logging, SQLite persistence
2. phase 1 single-agent loop detection
3. phase 2 coordinator with isolated finance/hr agents
4. phase 3 structured handoff payloads
5. phase 4 case facts extraction and compaction
6. phase 5 planner-executor workflow
7. end-to-end integration demo tying all phases together

## Testing Plan

### Unit Tests

- circuit opens after 3 failures
- loop detector catches repeated same-tool failures
- Coordinator cannot call finance/hr tools directly
- handoff payload includes only allowed fields
- case facts extractor preserves IDs and amounts
- missing fields create `requires_user_input`
- planner JSON validates against schema
- executor resumes correctly from persisted state

### Integration Tests

- `Count the active users` with failing DB tool
- `What is John’s salary and how much PTO does he have?`
- `Update my banking details. Routing number is 123456789.`
- long transaction document followed by noisy chat
- planner creates steps and executor completes them

### Demo Scenarios

Prepare one script per phase so the behavior is easy to show:

- `python app/main.py --demo phase1`
- `python app/main.py --demo phase2`
- `python app/main.py --demo phase3`
- `python app/main.py --demo phase4`
- `python app/main.py --demo phase5`

## Cost-Control Guidelines

To stay within the lab’s budget expectations:

- default to `gpt-4o-mini` for most execution
- use `o3-mini` only where reasoning quality is specifically required
- keep prompts short and tool schemas minimal
- never resend full long documents after extraction
- persist facts once and reference them later
- cap retries globally and per-tool
- add memoization for deterministic tool lookups in tests/demo flows

## Deliverables Checklist

- multi-agent architecture with Coordinator, Finance, HR, Planner, Executor
- circuit breaker implementation
- loop detection logs
- structured handoff payload mechanism
- persistent memory store
- case facts extraction and compaction logic
- flagging system for missing required fields
- planner-executor workflow with structured JSON plans
- unit and integration tests
- demo entrypoints and sample fixtures

## Suggested Milestones for a 2-Day Epic

### Day 1

- scaffold project structure
- implement runtime, logging, persistence
- complete Phase 1
- complete Phase 2
- start Phase 3

### Day 2

- finish Phase 3
- implement Phase 4 memory compaction and flags
- implement Phase 5 planner-executor workflow
- add tests and demo scripts
- run end-to-end validation

## Final Notes

The most important design principle across all phases is this:

- agents should not rely on raw conversational memory when exactness, safety, or resumability matters

Use explicit state, explicit handoffs, explicit plans, and explicit failure boundaries. That is what turns a toy agent flow into a production-grade orchestration system.
