# Phase 3 Cost Report

## Pricing Basis
- Analysis date: `2026-05-10`
- Simulated request volume: `1000000`
- Baseline pricing source: [OpenAI GPT-4o model page](https://developers.openai.com/api/docs/models/gpt-4o)
- Fine-tuned inference pricing source: [OpenAI GPT-4.1 mini model page](https://developers.openai.com/api/docs/models/gpt-4.1-mini)
- Training pricing source note: `A current official gpt-4.1-mini supervised fine-tuning training rate was not confirmed from the latest pricing pages during implementation, so this value must be supplied explicitly for exact ROI.`

## Cost Matrix

| Approach | Model | Avg input tokens/request | Avg output tokens/request | Input price/1M | Output price/1M | Cost/request | Cost for 1,000,000 requests |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Few-shot prompt baseline | gpt-4o | 1006.6 | 51.1 | $2.50 | $10.00 | $0.003027 | $3027.50 |
| Fine-tuned zero-shot | ft:gpt-4.1-mini-2025-04-14:kickdrum:ops-phase1:DdsePiWJ | 40.6 | 50.9 | $0.40 | $1.60 | $0.000098 | $97.68 |

## ROI Summary
- Baseline total inference cost: `$3027.50`
- Fine-tuned total inference cost: `$97.68`
- Fine-tuning training cost: `$0.05`
- Fine-tuned all-in cost: `$97.73`
- Total savings after training cost: `$2929.77`
- Cost reduction: `96.77%`
- Break-even requests: `16`

