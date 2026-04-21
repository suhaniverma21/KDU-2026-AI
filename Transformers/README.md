# Tri-Model AI Assistant

A local command-line AI assistant built with HuggingFace Transformers and LangChain.

It can:

- summarize long text
- refine the summary to a selected length
- answer questions using the refined summary as context

The project is designed to run on your own machine. After the first model download, it can work offline using the HuggingFace cache.

## Project Overview

This project uses three model stages:

1. Initial summarization using `facebook/bart-large-cnn`
2. Summary refinement using `google/flan-t5-base` with different length settings
3. Question answering using `deepset/roberta-base-squad2`

The user pastes a long text, chooses a summary length, reads the final summary, and then asks questions about that summary in an interactive loop.

## Features

- local command-line application
- no cloud API key required
- long text summarization
- summary length control: short, medium, long
- interactive question-answering loop
- runs offline after first model download
- beginner-friendly terminal flow

## Tech Stack

- `transformers`
- `torch`
- `langchain`
- `langchain-community`
- `sentencepiece`

## Models Used

### 1. Summarization Model

- `facebook/bart-large-cnn`

This model creates the initial summary from the user's long text.

### 2. Refinement Model

- `google/flan-t5-base`

This model reshapes the initial summary based on the user's length choice.

Length settings:

- `short` -> `min_length=30`, `max_length=60`
- `medium` -> `min_length=60`, `max_length=130`
- `long` -> `min_length=130`, `max_length=250`

### 3. Question Answering Model

- `deepset/roberta-base-squad2`

This model answers questions using only the refined summary as context.

## Installation

1. Open a terminal in the project folder.
2. Install the required packages:

```bash
pip install -r requirements.txt
```

## How To Run

```bash
python app.py
```

## Project Structure

```text
Transformers/
├── app.py
├── requirements.txt
├── README.md
├── implementation-plan.md
├── implementation-prompt.md
└── tri_model_assistant/
    ├── __init__.py
    ├── adapters.py
    ├── cli.py
    ├── config.py
    ├── main.py
    ├── models.py
    ├── qa.py
    ├── schemas.py
    ├── summarization.py
    └── system.py
```

Production-style responsibility split:

- `app.py` is a thin entrypoint
- `config.py` stores constants and model names
- `models.py` loads the three models
- `summarization.py` handles initial summarization and refinement
- `qa.py` contains question-answering logic
- `cli.py` manages terminal interaction
- `main.py` orchestrates the full application flow
- `adapters.py` contains local adapters used to keep model execution stable across library versions

## Example Terminal Flow

```text
=== Tri-Model AI Assistant ===
Powered by HuggingFace Transformers + LangChain

Paste your text below.
Press Enter on a blank line when you are done.

[user pastes article text]

Select summary length: short / medium / long
> medium

Generating summary...

=== Your Summary ===
[refined summary appears here]

=== Q&A Session ===
Type 'exit' to quit.

Your question: What is the main topic?
Answer: [model answer]

Your question: Who is involved?
Answer: [model answer]

Your question: exit
Goodbye!
```

## First Run Note

The first time you run the application:

- HuggingFace downloads the required models
- this may take some time depending on internet speed
- model loading may also feel slow on CPU

## Offline Usage

After the first download:

- the models are stored in the local HuggingFace cache
- future runs can load models from disk
- internet is not required unless the cache is missing

Typical cache location on Windows:

```text
C:\Users\YourName\.cache\huggingface\hub\
```

## Known Limitations

- `facebook/bart-large-cnn` is large and can be slow on CPU
- the first run may take a while because the models must download
- the QA model is extractive, so it can only answer using information present in the refined summary
- if the summary is too short, some important details may be lost before the Q&A stage
- local inference may use a lot of RAM on some machines

## Summary

This project is a simple local AI assistant that combines summarization and question answering in one flow. It is useful for learning how HuggingFace Transformers and LangChain can work together in an offline application.
