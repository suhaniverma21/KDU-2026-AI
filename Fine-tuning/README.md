# Fine-Tuning, Evals, and ROI Lab

## Overview

This project implements a three-phase lab for replacing a prompt-heavy large-model workflow with a fine-tuned smaller model, evaluating the result with an LLM judge, and measuring the ROI of the optimization.

The lab workflow is:
- Phase 1: Generate a proprietary DSL dataset with `gpt-4o`, fine-tune a smaller model, and test zero-shot behavior
- Phase 2: Evaluate the fine-tuned model on a validation set using `gpt-4o` as an LLM judge
- Phase 3: Compare token usage and cost before vs after fine-tuning, then compute ROI

## Source Of Truth

The original lab brief is stored in:
- [context.md](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/context.md:1)

## Repo Structure

- [src](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/src:1): scripts for generation, fine-tuning, evaluation, and cost analysis
- [prompts](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/prompts:1): DSL prompt assets and grader prompt
- [data/raw](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/data/raw:1): generated dataset artifacts
- [data/processed](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/data/processed:1): train, validation, and experiment datasets
- [reports](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/reports:1): phase outputs and analysis reports

## Environment Setup

Create your local secret file:

```env
OPENAI_API_KEY=your_openai_api_key_here
```

Files already provided:
- [.env.example](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/.env.example:1)
- [.gitignore](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/.gitignore:1)
- [.codexignore](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/.codexignore:1)

## Phase 1

### Goal

Use `gpt-4o` plus a large few-shot prompt to generate 50 DSL training records, fine-tune a smaller model, and test zero-shot behavior.

### Key Files

- Few-shot prompt: [prompts/baseline_fewshot.txt](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/prompts/baseline_fewshot.txt:1)
- DSL spec: [prompts/dsl_spec.md](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/prompts/dsl_spec.md:1)
- Dataset generation: [src/generate_dataset.py](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/src/generate_dataset.py:1)
- Phase 1 train prep: [src/prepare_finetune_data.py](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/src/prepare_finetune_data.py:1)
- Fine-tuning: [src/run_finetune.py](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/src/run_finetune.py:1)
- Fine-tune status check: [src/check_finetune_status.py](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/src/check_finetune_status.py:1)
- Zero-shot test: [src/test_phase1.py](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/src/test_phase1.py:1)

### Run Order

Generate 50 fine-tuning-ready records with `gpt-4o`:

```powershell
python src\generate_dataset.py --model gpt-4o --count 50
```

Prepare the Phase 1 training dataset using all 50 examples:

```powershell
python src\prepare_finetune_data.py
```

Start fine-tuning:

```powershell
python src\run_finetune.py
```

Poll job status:

```powershell
python src\check_finetune_status.py --job-id <YOUR_JOB_ID>
```

After the job succeeds, test the fine-tuned model in zero-shot mode:

```powershell
python src\test_phase1.py --fine-tuned-model <YOUR_FINE_TUNED_MODEL_ID>
```

### Outputs

- Generated dataset metadata: [data/raw/generated_examples.json](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/data/raw/generated_examples.json:1)
- Generated JSONL records: [data/raw/generated_examples.jsonl](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/data/raw/generated_examples.jsonl:1)
- Training file: [data/processed/train.jsonl](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/data/processed/train.jsonl:1)
- Contaminated experiment file: [data/processed/train_bad_sample.jsonl](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/data/processed/train_bad_sample.jsonl:1)
- Fine-tune status: [reports/phase1_finetune_status.json](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/reports/phase1_finetune_status.json:1)


## Phase 2

### Goal

Split the dataset, run validation evaluation, and use `gpt-4o` as a strict binary judge.

### Key Files

- Phase 2 split prep: [src/prepare_phase2_eval_data.py](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/src/prepare_phase2_eval_data.py:1)
- Judge prompt: [prompts/grader_prompt.txt](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/prompts/grader_prompt.txt:1)
- Judge helper: [src/grade_with_llm.py](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/src/grade_with_llm.py:1)
- Validation evaluator: [src/run_validation_eval.py](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/src/run_validation_eval.py:1)

### Run Order

Create the Phase 2 split:

```powershell
python src\prepare_phase2_eval_data.py
```

Run evaluation on the fine-tuned model:

```powershell
python src\run_validation_eval.py --fine-tuned-model <YOUR_FINE_TUNED_MODEL_ID>
```

### Outputs

- Phase 2 train split: [data/processed/phase2_train.jsonl](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/data/processed/phase2_train.jsonl:1)
- Validation split: [data/processed/validation.jsonl](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/data/processed/validation.jsonl:1)
- Prediction artifact: [reports/phase2_predictions.json](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/reports/phase2_predictions.json:1)
- Evaluation summary: [reports/phase2_eval_results.md](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/reports/phase2_eval_results.md:1)
- Error analysis: [reports/phase2_error_analysis.md](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/reports/phase2_error_analysis.md:1)

## Phase 3

### Goal

Compute cost before vs after optimization and calculate ROI for 1,000,000 requests.

### Key Files

- Cost analysis: [src/cost_analysis.py](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/src/cost_analysis.py:1)
- Cost report: [reports/phase3_cost_report.md](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/reports/phase3_cost_report.md:1)

### Run Order

Run the cost analysis:

```powershell
python src\cost_analysis.py --ft-training-price-per-1m 3
```

If you want to supply the one-time fine-tuning cost directly instead of a per-1M training rate:

```powershell
python src\cost_analysis.py --training-cost-usd <YOUR_TOTAL_TRAINING_COST>
```

### Outputs

- Structured cost report: [reports/phase3_cost_report.json](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/reports/phase3_cost_report.json:1)
- Markdown cost report: [reports/phase3_cost_report.md](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/reports/phase3_cost_report.md:1)

## Final Results Snapshot

### Phase 1

- Fine-tuned zero-shot exact-match accuracy: `0.3`
- Fine-tuned valid DSL rate: `1.0`
- Filler-free behavior: `true` across the evaluated Phase 1 cases
- Input-token reduction vs few-shot baseline: `95.97%`

### Phase 2

- Validation accuracy: `0.9`
- Valid DSL rate: `1.0`
- Filler-free rate: `1.0`
- Main remaining failures: `PRIORITY` and `APPROVAL` field-value mismatches on `DEPLOY`

### Phase 3

- Baseline cost for `1,000,000` requests: `$3027.50`
- Fine-tuned all-in cost: `$97.73`
- Cost reduction: `96.77%`
- Break-even point: `16` requests

## Important Notes

- The live fine-tuning API did not accept `gpt-4o-mini` during implementation, so the actual fine-tuned model used was `gpt-4.1-mini-2025-04-14`.
- Phase 1 now strictly trains on all 50 generated examples.
- Phase 2 owns the 20-example validation split, matching the lab wording.
- Your `.env` file is ignored and should never be committed.

## Main Submission Files

- [reports/phase2_eval_results.md](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/reports/phase2_eval_results.md:1)
- [reports/phase2_error_analysis.md](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/reports/phase2_error_analysis.md:1)
- [reports/phase3_cost_report.md](C:/Users/Dell/Documents/KDU-internship/AI/Fine-tuning/reports/phase3_cost_report.md:1)
