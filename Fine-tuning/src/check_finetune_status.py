from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI

from env_loader import load_local_env


def require_api_key() -> None:
    load_local_env()
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set.")


def load_job_id(cli_job_id: str | None, artifact_path: Path) -> str:
    if cli_job_id:
        return cli_job_id
    if not artifact_path.exists():
        raise ValueError("No job id provided and no fine-tune artifact file was found.")
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    job_id = payload.get("job_id")
    if not job_id:
        raise ValueError("Fine-tune artifact does not contain a job_id.")
    return job_id


def checkpoint_summaries(client: OpenAI, job_id: str) -> list[dict[str, Any]]:
    page = client.fine_tuning.jobs.checkpoints.list(job_id, limit=100)
    rows = []
    for item in page:
        rows.append(
            {
                "id": item.id,
                "step_number": item.step_number,
                "created_at": item.created_at,
                "checkpoint_model": item.fine_tuned_model_checkpoint,
                "metrics": item.metrics.model_dump(),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Check OpenAI fine-tuning job status.")
    parser.add_argument("--job-id", help="Fine-tuning job id, for example ftjob-abc123.")
    parser.add_argument("--artifact", type=Path, default=Path("reports/phase1_finetune_job.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/phase1_finetune_status.json"))
    args = parser.parse_args()

    require_api_key()
    client = OpenAI()
    job_id = load_job_id(args.job_id, args.artifact)
    job = client.fine_tuning.jobs.retrieve(job_id)
    checkpoints = checkpoint_summaries(client, job_id)
    latest_checkpoint = checkpoints[-1] if checkpoints else None

    payload = {
        "job_id": job.id,
        "status": job.status,
        "base_model": getattr(job, "model", None),
        "fine_tuned_model": getattr(job, "fine_tuned_model", None),
        "created_at": getattr(job, "created_at", None),
        "finished_at": getattr(job, "finished_at", None),
        "trained_tokens": getattr(job, "trained_tokens", None),
        "result_files": list(getattr(job, "result_files", [])),
        "error": job.error.model_dump() if getattr(job, "error", None) else None,
        "latest_checkpoint": latest_checkpoint,
        "num_checkpoints": len(checkpoints),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
