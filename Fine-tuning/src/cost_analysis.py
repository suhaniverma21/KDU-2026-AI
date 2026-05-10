from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CURRENT_DATE = "2026-05-10"
REQUEST_VOLUME_DEFAULT = 1_000_000


PRICING_DEFAULTS = {
    "baseline": {
        "model": "gpt-4o",
        "input_per_1m": 2.50,
        "output_per_1m": 10.00,
        "source_label": "OpenAI GPT-4o model page",
        "source_url": "https://developers.openai.com/api/docs/models/gpt-4o",
        "verified_on": CURRENT_DATE,
    },
    "fine_tuned_inference": {
        "model": "gpt-4.1-mini",
        "input_per_1m": 0.40,
        "output_per_1m": 1.60,
        "source_label": "OpenAI GPT-4.1 mini model page",
        "source_url": "https://developers.openai.com/api/docs/models/gpt-4.1-mini",
        "verified_on": CURRENT_DATE,
    },
    "fine_tune_training": {
        "model": "gpt-4.1-mini",
        "training_per_1m": None,
        "source_label": "Manual input required",
        "source_url": "https://openai.com/api/pricing/",
        "verified_on": CURRENT_DATE,
        "note": (
            "A current official gpt-4.1-mini supervised fine-tuning training rate "
            "was not confirmed from the latest pricing pages during implementation, "
            "so this value must be supplied explicitly for exact ROI."
        ),
    },
}


@dataclass
class TokenStats:
    input_tokens: float
    output_tokens: float


def safe_read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def average(values: list[int | float | None]) -> float | None:
    usable = [float(value) for value in values if value is not None]
    if not usable:
        return None
    return round(sum(usable) / len(usable), 4)


def average_usage_from_phase1(path: Path, prefix: str) -> TokenStats | None:
    payload = safe_read_json(path)
    if not payload:
        return None

    cases = payload.get("cases", [])
    input_avg = average([case.get(f"{prefix}_usage", {}).get("input_tokens") for case in cases])
    output_avg = average([case.get(f"{prefix}_usage", {}).get("output_tokens") for case in cases])
    if input_avg is None or output_avg is None:
        return None
    return TokenStats(input_tokens=input_avg, output_tokens=output_avg)


def average_usage_from_phase2(path: Path) -> TokenStats | None:
    payload = safe_read_json(path)
    if not payload:
        return None
    cases = payload.get("cases", payload if isinstance(payload, list) else [])
    input_avg = average([case.get("inference_usage", {}).get("input_tokens") for case in cases])
    output_avg = average([case.get("inference_usage", {}).get("output_tokens") for case in cases])
    if input_avg is None or output_avg is None:
        return None
    return TokenStats(input_tokens=input_avg, output_tokens=output_avg)


def trained_tokens_from_finetune_job(path: Path) -> int | None:
    payload = safe_read_json(path)
    if not payload:
        return None
    trained_tokens = payload.get("trained_tokens")
    return int(trained_tokens) if trained_tokens is not None else None


def resolve_fine_tuned_model_name(phase1_results_path: Path, finetune_status_path: Path) -> str | None:
    phase1_payload = safe_read_json(phase1_results_path)
    if phase1_payload and phase1_payload.get("fine_tuned_model"):
        return str(phase1_payload["fine_tuned_model"])

    status_payload = safe_read_json(finetune_status_path)
    if status_payload and status_payload.get("fine_tuned_model"):
        return str(status_payload["fine_tuned_model"])

    return None


def resolve_token_stats(
    manual_input: float | None,
    manual_output: float | None,
    primary_source: TokenStats | None,
    fallback_source: TokenStats | None = None,
) -> TokenStats:
    input_tokens = manual_input
    output_tokens = manual_output

    if input_tokens is None and primary_source:
        input_tokens = primary_source.input_tokens
    if output_tokens is None and primary_source:
        output_tokens = primary_source.output_tokens

    if input_tokens is None and fallback_source:
        input_tokens = fallback_source.input_tokens
    if output_tokens is None and fallback_source:
        output_tokens = fallback_source.output_tokens

    if input_tokens is None or output_tokens is None:
        raise ValueError("Token stats could not be resolved. Provide manual token values or generate earlier artifacts.")

    return TokenStats(float(input_tokens), float(output_tokens))


def cost_per_request(token_stats: TokenStats, input_price_per_1m: float, output_price_per_1m: float) -> float:
    return round(
        (token_stats.input_tokens / 1_000_000) * input_price_per_1m
        + (token_stats.output_tokens / 1_000_000) * output_price_per_1m,
        8,
    )


def total_cost(cost_per_request_usd: float, requests: int) -> float:
    return round(cost_per_request_usd * requests, 4)


def percent_reduction(before: float, after: float) -> float:
    if before == 0:
        return 0.0
    return round(((before - after) / before) * 100, 2)


def break_even_requests(training_cost: float, baseline_cost: float, optimized_cost: float) -> int | None:
    savings_per_request = baseline_cost - optimized_cost
    if savings_per_request <= 0:
        return None
    return int((training_cost / savings_per_request) + 0.999999)


def maybe_float(value: str | None) -> float | None:
    return float(value) if value is not None else None


def write_markdown_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    matrix = payload["cost_matrix"]
    roi = payload["roi"]
    notes = payload["notes"]
    lines = [
        "# Phase 3 Cost Report",
        "",
        "## Pricing Basis",
        f"- Analysis date: `{payload['analysis_date']}`",
        f"- Simulated request volume: `{payload['request_volume']}`",
        f"- Baseline pricing source: [{payload['pricing_sources']['baseline']['label']}]({payload['pricing_sources']['baseline']['url']})",
        f"- Fine-tuned inference pricing source: [{payload['pricing_sources']['fine_tuned_inference']['label']}]({payload['pricing_sources']['fine_tuned_inference']['url']})",
        f"- Training pricing source note: `{payload['pricing_sources']['fine_tune_training']['note']}`",
        "",
        "## Cost Matrix",
        "",
        "| Approach | Model | Avg input tokens/request | Avg output tokens/request | Input price/1M | Output price/1M | Cost/request | Cost for 1,000,000 requests |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in matrix:
        lines.append(
            f"| {row['approach']} | {row['model']} | {row['avg_input_tokens_per_request']} | "
            f"{row['avg_output_tokens_per_request']} | ${row['input_price_per_1m']:.2f} | "
            f"${row['output_price_per_1m']:.2f} | ${row['cost_per_request_usd']:.6f} | "
            f"${row['cost_for_request_volume_usd']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## ROI Summary",
            f"- Baseline total inference cost: `${roi['baseline_total_inference_cost_usd']:.2f}`",
            f"- Fine-tuned total inference cost: `${roi['fine_tuned_total_inference_cost_usd']:.2f}`",
            f"- Fine-tuning training cost: `${roi['fine_tuning_training_cost_usd']:.2f}`",
            f"- Fine-tuned all-in cost: `${roi['fine_tuned_all_in_cost_usd']:.2f}`",
            f"- Total savings after training cost: `${roi['net_savings_usd']:.2f}`",
            f"- Cost reduction: `{roi['cost_reduction_percent']}%`",
            f"- Break-even requests: `{roi['break_even_requests']}`",
            "",
            "## Phase 3 Answers",
            f"- Fine-tuning becomes profitable after approximately `{roi['break_even_requests']}` requests, assuming the supplied training-cost input is accurate.",
            f"- The estimated cost reduction at `{payload['request_volume']}` requests is `{roi['cost_reduction_percent']}%`.",
            "- SFT is not suitable for teaching genuinely new knowledge because it mostly teaches the model to imitate patterns and task behavior from examples rather than reliably update its world knowledge or factual base.",
            "- With open-source QLoRA pipelines, extra DevOps work appears around GPU provisioning, adapter management, quantization compatibility, evaluation drift, and custom serving infrastructure.",
            "- With model versioning and deployment, the main challenges are reproducibility, rollback safety, dataset lineage, model registry discipline, and keeping evaluation and production versions aligned.",
            "",
            "## Notes",
        ]
    )
    for note in notes:
        lines.append(f"- {note}")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Phase 3 cost matrix and ROI analysis.")
    parser.add_argument("--request-volume", type=int, default=REQUEST_VOLUME_DEFAULT)
    parser.add_argument("--phase1-results", type=Path, default=Path("reports/phase1_results.json"))
    parser.add_argument("--phase2-results", type=Path, default=Path("reports/phase2_eval_results.json"))
    parser.add_argument("--finetune-job-artifact", type=Path, default=Path("reports/phase1_finetune_job.json"))
    parser.add_argument("--finetune-status-artifact", type=Path, default=Path("reports/phase1_finetune_status.json"))
    parser.add_argument("--baseline-input-tokens", type=float)
    parser.add_argument("--baseline-output-tokens", type=float)
    parser.add_argument("--ft-input-tokens", type=float)
    parser.add_argument("--ft-output-tokens", type=float)
    parser.add_argument("--trained-tokens", type=int)
    parser.add_argument("--ft-training-price-per-1m", type=float)
    parser.add_argument("--training-cost-usd", type=float)
    parser.add_argument("--output-json", type=Path, default=Path("reports/phase3_cost_report.json"))
    parser.add_argument("--output-md", type=Path, default=Path("reports/phase3_cost_report.md"))
    args = parser.parse_args()

    phase1_baseline = average_usage_from_phase1(args.phase1_results, "baseline")
    phase1_ft = average_usage_from_phase1(args.phase1_results, "ft")
    phase2_ft = average_usage_from_phase2(args.phase2_results)

    baseline_tokens = resolve_token_stats(
        manual_input=args.baseline_input_tokens,
        manual_output=args.baseline_output_tokens,
        primary_source=phase1_baseline,
    )
    ft_tokens = resolve_token_stats(
        manual_input=args.ft_input_tokens,
        manual_output=args.ft_output_tokens,
        primary_source=phase1_ft if phase1_ft else phase2_ft,
        fallback_source=phase2_ft,
    )

    baseline_cost_request = cost_per_request(
        baseline_tokens,
        PRICING_DEFAULTS["baseline"]["input_per_1m"],
        PRICING_DEFAULTS["baseline"]["output_per_1m"],
    )
    ft_cost_request = cost_per_request(
        ft_tokens,
        PRICING_DEFAULTS["fine_tuned_inference"]["input_per_1m"],
        PRICING_DEFAULTS["fine_tuned_inference"]["output_per_1m"],
    )

    baseline_total = total_cost(baseline_cost_request, args.request_volume)
    ft_total = total_cost(ft_cost_request, args.request_volume)

    trained_tokens = (
        args.trained_tokens
        if args.trained_tokens is not None
        else trained_tokens_from_finetune_job(args.finetune_status_artifact) or trained_tokens_from_finetune_job(args.finetune_job_artifact)
    )
    actual_fine_tuned_model = resolve_fine_tuned_model_name(args.phase1_results, args.finetune_status_artifact)
    training_rate = args.ft_training_price_per_1m
    notes: list[str] = []

    if args.training_cost_usd is not None:
        training_cost = round(args.training_cost_usd, 4)
    elif trained_tokens is not None and training_rate is not None:
        training_cost = round((trained_tokens / 1_000_000) * training_rate, 4)
    else:
        training_cost = 0.0
        notes.append(
            "Exact fine-tuning training cost was not computed automatically. "
            "Pass either --training-cost-usd or both --trained-tokens and --ft-training-price-per-1m."
        )

    break_even = break_even_requests(training_cost, baseline_cost_request, ft_cost_request)
    if break_even is None:
        notes.append("Break-even could not be computed because per-request savings were not positive or training cost was unresolved.")

    if trained_tokens is None:
        notes.append("Trained token count was not found in reports/phase1_finetune_job.json, so training cost may require manual input.")
    if training_rate is None and args.training_cost_usd is None:
        notes.append(PRICING_DEFAULTS["fine_tune_training"]["note"])
    cost_matrix = [
        {
            "approach": "Few-shot prompt baseline",
            "model": PRICING_DEFAULTS["baseline"]["model"],
            "avg_input_tokens_per_request": round(baseline_tokens.input_tokens, 2),
            "avg_output_tokens_per_request": round(baseline_tokens.output_tokens, 2),
            "input_price_per_1m": PRICING_DEFAULTS["baseline"]["input_per_1m"],
            "output_price_per_1m": PRICING_DEFAULTS["baseline"]["output_per_1m"],
            "cost_per_request_usd": baseline_cost_request,
            "cost_for_request_volume_usd": baseline_total,
        },
        {
            "approach": "Fine-tuned zero-shot",
            "model": actual_fine_tuned_model or f"ft:{PRICING_DEFAULTS['fine_tuned_inference']['model']}",
            "avg_input_tokens_per_request": round(ft_tokens.input_tokens, 2),
            "avg_output_tokens_per_request": round(ft_tokens.output_tokens, 2),
            "input_price_per_1m": PRICING_DEFAULTS["fine_tuned_inference"]["input_per_1m"],
            "output_price_per_1m": PRICING_DEFAULTS["fine_tuned_inference"]["output_per_1m"],
            "cost_per_request_usd": ft_cost_request,
            "cost_for_request_volume_usd": ft_total,
        },
    ]

    payload = {
        "analysis_date": CURRENT_DATE,
        "request_volume": args.request_volume,
        "token_inputs": {
            "baseline": baseline_tokens.__dict__,
            "fine_tuned": ft_tokens.__dict__,
            "trained_tokens": trained_tokens,
        },
        "pricing_sources": {
            "baseline": {
                "label": PRICING_DEFAULTS["baseline"]["source_label"],
                "url": PRICING_DEFAULTS["baseline"]["source_url"],
                "verified_on": PRICING_DEFAULTS["baseline"]["verified_on"],
            },
            "fine_tuned_inference": {
                "label": PRICING_DEFAULTS["fine_tuned_inference"]["source_label"],
                "url": PRICING_DEFAULTS["fine_tuned_inference"]["source_url"],
                "verified_on": PRICING_DEFAULTS["fine_tuned_inference"]["verified_on"],
            },
            "fine_tune_training": {
                "label": PRICING_DEFAULTS["fine_tune_training"]["source_label"],
                "url": PRICING_DEFAULTS["fine_tune_training"]["source_url"],
                "verified_on": PRICING_DEFAULTS["fine_tune_training"]["verified_on"],
                "note": PRICING_DEFAULTS["fine_tune_training"]["note"],
                "training_price_per_1m_tokens": training_rate,
            },
        },
        "cost_matrix": cost_matrix,
        "roi": {
            "baseline_total_inference_cost_usd": baseline_total,
            "fine_tuned_total_inference_cost_usd": ft_total,
            "fine_tuning_training_cost_usd": training_cost,
            "fine_tuned_all_in_cost_usd": round(ft_total + training_cost, 4),
            "net_savings_usd": round(baseline_total - (ft_total + training_cost), 4),
            "cost_reduction_percent": percent_reduction(baseline_total, ft_total + training_cost),
            "break_even_requests": break_even,
        },
        "notes": notes,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_markdown_report(args.output_md, payload)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
