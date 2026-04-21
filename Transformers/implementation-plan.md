# Implementation Plan — Tri-Model AI Assistant

## 1. Goal

Build a fully local, offline-capable AI assistant in Python using HuggingFace Transformers and LangChain that:

- accepts long-form user text input
- generates an initial summary
- refines the summary to a user-selected length
- enters an interactive question-answering loop using the refined summary as context

The system should run on a local machine after the first model download and should not require external APIs.

## 2. Final Deliverable

A working command-line application that provides:

- local model loading
- summarization with `facebook/bart-large-cnn`
- summary refinement with adjustable length
- extractive QA with `deepset/roberta-base-squad2`
- an interactive terminal-based user flow
- clean modular code with separate loading and orchestration responsibilities

## 3. Core Requirements

### Functional Requirements

- load the summarization model from HuggingFace
- load the QA model from HuggingFace
- allow the user to paste multiline text
- create an initial compressed summary
- allow the user to choose `short`, `medium`, or `long`
- regenerate or refine the summary using the selected length configuration
- display the refined summary
- allow repeated user questions against the refined summary
- stop the QA loop when the user types `exit`

### Non-Functional Requirements

- run fully locally after first model download
- support CPU execution
- keep code modular and readable
- handle invalid input gracefully
- make terminal prompts clear for non-technical users

## 4. Implementation Strategy

The implementation will follow a layered structure:

1. model loading layer
2. LangChain wrapper layer
3. summarization and refinement logic
4. QA context handling
5. CLI interaction layer

This keeps the code easy to test and easy to explain.

## 5. Proposed File Structure

```text
Tri-Model-AI-Assistant/
├── app.py
├── requirements.txt
├── README.md
├── implementation-plan.md
├── implementation-prompt.md
└── utils/
    └── prompts.py
```

If we want a simpler submission, we can also collapse everything into:

- `app.py`
- `requirements.txt`
- `README.md`

## 6. Dependency Plan

Create a `requirements.txt` with:

```txt
transformers
torch
langchain
langchain-community
sentencepiece
```

Optional additions if needed during implementation:

- `accelerate`
- `scipy`

These should only be added if the selected Transformers pipeline requires them on the local machine.

## 7. Model Loading Plan

### Summarization Model

Model:

- `facebook/bart-large-cnn`

Libraries:

- `transformers.AutoTokenizer`
- `transformers.AutoModelForSeq2SeqLM`
- `transformers.pipeline`

LangChain wrapper:

- `langchain_community.llms.HuggingFacePipeline`

Purpose:

- initial summarization
- refinement summarization with different generation parameters

### Question Answering Model

Model:

- `deepset/roberta-base-squad2`

Libraries:

- `transformers.AutoTokenizer`
- `transformers.AutoModelForQuestionAnswering`
- `transformers.pipeline`

LangChain usage:

- use LangChain to structure the QA stage
- since extractive QA is not a text-generation LLM, we should be careful not to force it into an incompatible `LLMChain`

Implementation note:

- if `RetrievalQA` proves awkward with a pure extractive HuggingFace QA pipeline, we should keep LangChain involved for orchestration and prompt structure but call the QA pipeline directly for the actual answer extraction
- this is the safest practical interpretation of the design while preserving the local tri-model architecture

## 8. Detailed Build Steps

### Step 1. Create Project Files

- create `app.py`
- create `requirements.txt`
- create or update `README.md`
- optionally create `utils/prompts.py` for prompt text and constants

### Step 2. Define Shared Constants

In `app.py` or `utils/prompts.py`, define:

- model names
- summary length presets
- terminal labels
- exit keyword

Example length mapping:

```python
LENGTH_CONFIGS = {
    "short": {"min_length": 30, "max_length": 60},
    "medium": {"min_length": 60, "max_length": 130},
    "long": {"min_length": 130, "max_length": 250},
}
```

### Step 3. Implement Model Loader Functions

Create:

- `load_summarizer()`
- `load_qa_model()`

`load_summarizer()` responsibilities:

- load BART tokenizer
- load BART seq2seq model
- build a Transformers summarization pipeline
- wrap it with `HuggingFacePipeline`

`load_qa_model()` responsibilities:

- load RoBERTa tokenizer
- load RoBERTa QA model
- build a Transformers question-answering pipeline
- return the pipeline and any LangChain-compatible wrapper needed for orchestration

### Step 4. Implement Summarization Logic

Create a function:

- `generate_initial_summary(text: str) -> str`

Behavior:

- sanitize input
- call BART summarizer with a reasonable default range
- return a compressed summary

Suggested defaults:

- `min_length=60`
- `max_length=180`
- `do_sample=False`

Rationale:

- deterministic summarization is better than creative generation for this task

### Step 5. Implement Refinement Logic

Create a function:

- `refine_summary(summary: str, length_choice: str) -> str`

Behavior:

- validate `length_choice`
- read `min_length` and `max_length` from the config map
- run the same BART pipeline on the first summary
- return the resized summary

Implementation note:

- although the design describes this as a separate model stage, we should reuse the already loaded BART model for efficiency

### Step 6. Implement QA Logic

Create a function:

- `answer_question(context: str, question: str) -> str`

Behavior:

- send `{"question": question, "context": context}` to the QA pipeline
- return the extracted answer text
- if confidence is too low or answer is empty, return a fallback message

Suggested fallback behavior:

- if no meaningful answer is found, print:
  `I could not find a reliable answer in the summary.`

### Step 7. Add LangChain Integration

Use LangChain where it adds clear structure:

- wrap summarization pipeline with `HuggingFacePipeline`
- optionally define prompt templates for summarization/refinement framing
- organize calls in a modular chain-like flow

Practical note:

- newer LangChain versions may prefer `RunnableSequence` and prompt templates over legacy `LLMChain`
- implementation should choose the currently installed compatible pattern rather than forcing outdated syntax

### Step 8. Implement CLI Input Flow

Main flow:

1. print application banner
2. collect multiline input
3. validate that text is not empty
4. ask for summary length
5. generate initial summary
6. refine summary according to selection
7. display refined summary
8. enter QA loop
9. exit cleanly when the user types `exit`

### Step 9. Implement Multiline Text Capture

Create a helper:

- `read_multiline_input() -> str`

Behavior:

- let the user paste multiple lines
- stop when the user presses Enter on a blank line twice, or use a single blank line if that is simpler and clearly documented

Recommended simple approach:

- keep reading lines
- stop on first blank line
- join lines with newline characters

This is easier to implement reliably in terminal environments.

### Step 10. Implement Input Validation

Validate:

- empty text input
- invalid summary length choice
- empty question input

Behavior:

- re-prompt for invalid length
- skip empty questions
- reject empty source text before loading the full workflow

### Step 11. Add Offline-Friendly Notes

Document clearly:

- first run downloads models
- later runs use HuggingFace local cache
- no cloud API keys are required

### Step 12. Add Error Handling

Handle these cases:

- missing dependencies
- model download failures
- insufficient memory
- unsupported CPU speed expectations
- user interrupt with `Ctrl+C`

Recommended behavior:

- catch exceptions in `main()`
- print short actionable error messages

## 9. Suggested Function Breakdown

```python
def load_summarizer():
    pass

def load_qa_model():
    pass

def read_multiline_input():
    pass

def generate_initial_summary(text, summarizer):
    pass

def refine_summary(summary, summarizer, length_choice):
    pass

def answer_question(question, context, qa_pipeline):
    pass

def select_summary_length():
    pass

def run_qa_loop(context, qa_pipeline):
    pass

def main():
    pass
```

## 10. Execution Order

### Phase 1 — Setup

- create project files
- add dependencies
- verify imports

### Phase 2 — Summarization

- load BART
- generate initial summary
- validate output

### Phase 3 — Refinement

- implement length presets
- refine summary
- verify short, medium, and long outputs

### Phase 4 — QA

- load RoBERTa QA model
- run question answering against summary context
- verify fallback behavior for missing answers

### Phase 5 — CLI Experience

- add banner
- add multiline input
- add looped questions
- polish prompts and error messages

### Phase 6 — Documentation

- write README
- add run instructions
- note offline behavior and limitations

## 11. Testing Plan

### Functional Tests

- test with a short article
- test with a long article
- test each summary length option
- test at least three QA questions
- test `exit`

### Edge Case Tests

- empty input
- invalid length choice
- question with no answer in summary
- very short source text

### Performance Tests

- confirm that first run downloads correctly
- confirm that second run uses cache
- observe CPU inference latency

## 12. Known Risks And Mitigations

### Risk 1. BART is slow on CPU

Mitigation:

- warn the user before inference
- keep summarization deterministic
- avoid unnecessarily long generation settings

### Risk 2. High RAM usage

Mitigation:

- load models once and reuse them
- avoid duplicating model instances
- reuse BART for both summarization stages

### Risk 3. LangChain QA abstraction mismatch

Mitigation:

- use LangChain for orchestration, but call the extractive QA pipeline directly if `RetrievalQA` is not a clean fit for the RoBERTa pipeline

### Risk 4. Poor QA answer quality from overly compressed summary

Mitigation:

- recommend `medium` or `long` for QA-heavy usage
- add fallback when no reliable answer is found

## 13. Recommended Implementation Decisions

- use one loaded BART model for both Model 1 and Model 2
- use deterministic summarization with `do_sample=False`
- use direct Transformers QA inference for answer extraction
- keep LangChain in the architecture for wrapping and flow organization, not for forcing unsupported abstractions
- build a single-file version first, then refactor only if needed

## 14. Minimum Viable Version

The first working version should include:

- `app.py`
- local BART summarization
- length-based refinement
- RoBERTa extractive QA
- terminal Q&A loop

Anything beyond that should be treated as a polish phase.

## 15. Completion Criteria

The implementation is complete when:

- the app accepts user text and generates a summary
- the user can choose `short`, `medium`, or `long`
- the refined summary is displayed
- the user can ask multiple questions
- answers are returned from the summary context
- the app runs locally from the terminal
- the README explains setup and offline behavior
