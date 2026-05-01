# Implementation Prompt: AgentKit Orchestration, Loop Detection, and Memory Compaction

Build a production-grade multi-agent orchestration system using the OpenAI Agents SDK. The system must demonstrate robust failure handling, agent isolation, structured handoffs, persistent memory, memory compaction, and a planner-executor workflow.

This implementation should prioritize architecture, correctness, observability, and low cost over polished output style.

## Critical Requirements

These are mandatory and should shape every design choice:

### LLM Provider Guidelines

- Use the OpenAI API as the primary provider
- Prefer low-cost models such as `gpt-4o-mini` or GPT-3.5-class models wherever possible
- Use `o3-mini` only where explicitly required for reasoning-heavy tasks
- If OpenAI is unavailable, use OpenRouter as a fallback provider
- Avoid high-cost models unless there is a clear requirement

### Cost and Usage Guidelines

- Focus on architecture and understanding, not output quality
- Always prefer the cheapest viable model during development and demos
- Avoid unnecessary retries, loops, and repeated API calls
- Keep context small and avoid resending large inputs repeatedly
- Persist extracted facts so long documents do not need to be reprocessed
- Use explicit retry caps and circuit breakers
- Keep tool schemas short and agent prompts narrow

## Overall Objective

Implement a system that can:

- prevent infinite execution loops
- handle tool failures gracefully
- isolate tools by agent responsibility
- pass structured context between agents without forwarding full chat history
- compact memory without losing critical transactional facts
- support a hybrid planner-executor workflow with persistent state

## Build Constraints

- Use Python 3.11+
- Use the OpenAI Agents SDK
- Use SQLite for persistent memory and execution state
- Use structured JSON logging
- Keep the implementation modular and testable
- All tool outputs should use a structured success/error envelope
- All important state transitions must be persisted

## Required System Components

Implement the following modules or their equivalents:

- runtime/session state manager
- structured logging and tracing
- tool wrapper layer with standardized result format
- circuit breaker and retry policy
- Coordinator, Finance, HR, Planner, and Executor agents
- structured handoff payload builder
- persistent memory store
- case facts extractor
- memory compaction layer
- missing-field flagging mechanism
- planner-executor state machine
- tests and demo entrypoints

## Standard Tool Result Format

Every tool must return:

```json
{
  "ok": true,
  "data": {},
  "error": null,
  "retryable": false,
  "tool_name": "tool_name"
}
```

On failure:

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

## Phase 1: Loop Detection and Circuit Breaker

### Task

Create a single agent using `o3-mini` with one tool named `query_internal_database`.

### Setup

- The tool must intentionally fail with a 500-style error
- Ask the agent: `Count the active users`
- Observe how many times it retries before stopping under default behavior

### Implement

- a failure counter for repeated tool failures
- loop detection for repeated same-tool same-input execution
- a circuit breaker that opens after 3 consecutive failures
- structured logs for:
  - `tool_called`
  - `tool_failed`
  - `loop_detected`
  - `circuit_opened`

### Required Behavior

- stop execution after 3 consecutive failures
- return a graceful fallback response to the user
- log how many retries occurred before the circuit opened

### Questions This Phase Must Answer

- How many retries did the agent attempt before stopping?
- How was the loop detected?
- How did the circuit breaker prevent repeated calls?

## Phase 2: Coordinator and Agent Isolation

### Task

Build a three-agent system:

- Coordinator Agent
- Finance Agent
- HR Agent

### Isolation Rules

Coordinator must only have delegation tools.

Coordinator must not directly have:

- salary lookup tools
- PTO lookup tools
- banking update tools

Finance Agent owns:

- salary lookup
- banking update tools

HR Agent owns:

- PTO lookup tools

### Required Behavior

For the user request:
`What is John’s salary and how much PTO does he have?`

The system must:

- detect that this spans Finance and HR
- delegate salary retrieval to Finance
- delegate PTO retrieval to HR
- merge both results into one final answer

### Questions This Phase Must Answer

- How does the Coordinator sequence delegation?
- How does it merge sub-agent outputs?
- Why does tool isolation reduce prompt bloat?
- Why does isolation improve reliability?

## Phase 3: Context Passing Between Agents

### Task

Use the Coordinator to process:
`Update my banking details. Routing number is 123456789.`

Transfer the request to the Finance Agent.

### Core Rule

Sub-agents must not inherit the full conversation history automatically.

### Implement

A structured handoff payload containing only relevant information, such as:

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
  ]
}
```

### Required Behavior

- only relevant task data is passed
- unrelated messages are excluded
- Finance Agent uses payload data and required fields to continue the task

### Questions This Phase Must Answer

- How is the context payload constructed?
- How is full chat history avoided?
- How is relevance enforced during handoff?

## Phase 4: Memory Compaction and Case Facts

### Task

Enable persistent session memory and process:

- a long transactional document around 5000 words
- several irrelevant follow-up messages such as `okay` and `cool`

### Problem to Solve

Naive summarization may lose important details such as:

- order IDs
- transaction IDs
- routing numbers
- amounts
- dates
- account fields
- CVV or other required details

### Implement

Two-layer memory:

1. compact conversational summary
2. structured `Case Facts` dictionary

The Case Facts store must extract and preserve:

- numerical data
- transaction IDs
- order IDs
- monetary amounts
- currencies
- dates
- banking fields
- required-field status

### Required Flagging Mechanism

If required fields are missing, for example `CVV`, the system must:

- create a flag record
- mark the session state as `requires_user_input`
- prevent unsafe or incomplete action execution

### Example State

```json
{
  "banking_details": {
    "routing_number": "123456789",
    "account_number": null,
    "cvv": null
  },
  "required_fields_status": {
    "routing_number": "present",
    "account_number": "missing",
    "cvv": "missing"
  },
  "session_state": "requires_user_input"
}
```

### Questions This Phase Must Answer

- How are critical facts extracted before memory compaction?
- How does the Case Facts store prevent data loss?
- How does flagging prevent context degradation and unsafe execution?

## Phase 5: Hybrid Planner-Executor Workflow

### Task

Build a two-agent workflow:

- Planner Agent using `o3-mini`
- Executor Agent using `gpt-4o-mini` by default

Use `gpt-4o` only if there is an explicit need. Default to `gpt-4o-mini` for cost control.

### Workflow Requirements

1. Planner generates structured JSON steps
2. Executor executes the steps
3. State is persisted after each step
4. Execution can resume after interruption

### Planner Output Format

Planner must return a structured JSON plan, for example:

```json
{
  "goal": "Process user request safely",
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
      "action": "perform_finance_update",
      "agent": "executor",
      "depends_on": ["step_1"],
      "expected_output": "update result"
    }
  ],
  "success_criteria": [
    "required fields are present",
    "tool result is persisted"
  ]
}
```

### Executor Input

Executor should receive:

- the plan
- session summary
- relevant case facts
- current flags
- completed step history
- trace ID

Do not pass the full transcript if it is not required.

### Questions This Phase Must Answer

- How is memory passed from Planner to Executor?
- How is step consistency maintained?
- Why is Planner-Executor better than raw API chaining for this system?

## Shared Persistence Requirements

Persist the following:

- sessions
- agent runs
- tool calls
- handoffs
- case facts
- flags
- memory snapshots
- plan state
- step execution results

Use SQLite unless there is a strong reason to replace it.

## Logging Requirements

Log the following event types:

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

Every log entry should include:

- timestamp
- session_id
- trace_id
- agent_name
- step_index if applicable
- event_type
- concise payload summary

## Cost-Safe Implementation Rules

These rules are especially important:

- keep agent prompts narrow and role-specific
- keep tool descriptions short
- do not give every tool to every agent
- do not forward full chat history during handoff
- extract facts once, store them, and reuse them
- cap retries globally and per tool
- short-circuit deterministic failures quickly
- avoid repeated processing of the same 5000-word document
- use small models for tests, demos, and non-critical execution
- treat token usage as a first-class architecture concern

## Testing Requirements

Create tests for:

- Phase 1 retry counting and circuit breaker activation
- Phase 2 tool isolation and delegation order
- Phase 3 structured handoff payload filtering
- Phase 4 fact extraction, compaction safety, and missing-field flags
- Phase 5 planner JSON validation, step execution, and resumability

Also create demo entrypoints or scripts for each phase.

## Expected Deliverables

Produce:

- working multi-agent architecture
- circuit breaker logic
- loop detection instrumentation
- Coordinator, Finance, and HR orchestration
- structured context handoff mechanism
- persistent memory layer
- Case Facts extraction and compaction
- missing-field flagging with `requires_user_input`
- Planner-Executor workflow
- tests
- sample fixtures and runnable demos

## Implementation Priorities

Implement in this order:

1. runtime, schemas, logging, and persistence
2. phase 1 loop detection and circuit breaker
3. phase 2 Coordinator with isolated sub-agents
4. phase 3 structured handoff payloads
5. phase 4 memory compaction and Case Facts
6. phase 5 Planner-Executor flow
7. end-to-end demo and test pass

## Final Instruction

Optimize for robust orchestration, low cost, explicit state, and testability.

Do not build this as a loose chat demo. Build it as a controlled agent system with:

- explicit failure boundaries
- explicit handoffs
- explicit memory
- explicit execution state
- explicit cost controls
