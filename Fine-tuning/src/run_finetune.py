from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from openai import OpenAI
from env_loader import load_local_env


TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def require_api_key() -> None:
    load_local_env()
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set.")


def upload_file(client: OpenAI, path: Path) -> Any:
    with path.open("rb") as handle:
        return client.files.create(file=handle, purpose="fine-tune")


def checkpoint_summaries(client: OpenAI, job_id: str) -> list[dict[str, Any]]:
    page = client.fine_tuning.jobs.checkpoints.list(job_id, limit=100)
    summaries = []
    for item in page:
        summaries.append(
            {
                "id": item.id,
                "step_number": item.step_number,
                "created_at": item.created_at,
                "metrics": item.metrics.model_dump(),
                "checkpoint_model": item.fine_tuned_model_checkpoint,
            }
        )
    return summaries


def download_result_files(client: OpenAI, result_file_ids: list[str], directory: Path) -> list[str]:
    directory.mkdir(parents=True, exist_ok=True)
    downloaded = []
    for file_id in result_file_ids:
        contents = client.files.retrieve_content(file_id)
        target = directory / f"{file_id}.csv"
        target.write_text(contents, encoding="utf-8")
        downloaded.append(str(target))
    return downloaded


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 1 supervised fine-tuning with the raw OpenAI SDK.")
    parser.add_argument("--train-file", type=Path, default=Path("data/processed/train.jsonl"))
    parser.add_argument("--validation-file", type=Path)
    parser.add_argument("--model", default="gpt-4.1-mini-2025-04-14")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--suffix", default="ops-phase1")
    parser.add_argument("--wait", action="store_true", help="Poll until the job reaches a terminal status.")
    parser.add_argument("--poll-interval", type=int, default=30)
    parser.add_argument("--output", type=Path, default=Path("reports/phase1_finetune_job.json"))
    parser.add_argument("--result-dir", type=Path, default=Path("reports/fine_tune_results"))
    args = parser.parse_args()

    require_api_key()
    client = OpenAI()

    train_upload = upload_file(client, args.train_file)
    validation_upload = upload_file(client, args.validation_file) if args.validation_file and args.validation_file.exists() else None

    job = client.fine_tuning.jobs.create(
        model=args.model,
        training_file=train_upload.id,
        validation_file=validation_upload.id if validation_upload else None,
        suffix=args.suffix,
        method={
            "type": "supervised",
            "supervised": {"hyperparameters": {"n_epochs": args.epochs}},
        },
    )

    artifact: dict[str, Any] = {
        "job_id": job.id,
        "status": job.status,
        "base_model": args.model,
        "train_upload_id": train_upload.id,
        "validation_upload_id": validation_upload.id if validation_upload else None,
        "suffix": args.suffix,
    }

    if args.wait:
        while job.status not in TERMINAL_STATUSES:
            time.sleep(args.poll_interval)
            job = client.fine_tuning.jobs.retrieve(job.id)

        checkpoints = checkpoint_summaries(client, job.id) if job.status == "succeeded" else []
        final_checkpoint = checkpoints[-1] if checkpoints else None
        result_paths = (
            download_result_files(client, job.result_files, args.result_dir)
            if getattr(job, "result_files", None)
            else []
        )
        artifact.update(
            {
                "status": job.status,
                "fine_tuned_model": getattr(job, "fine_tuned_model", None),
                "trained_tokens": getattr(job, "trained_tokens", None),
                "result_files": list(getattr(job, "result_files", [])),
                "downloaded_result_files": result_paths,
                "checkpoints": checkpoints,
                "final_train_loss": final_checkpoint["metrics"].get("train_loss") if final_checkpoint else None,
                "final_valid_loss": final_checkpoint["metrics"].get("valid_loss") if final_checkpoint else None,
            }
        )

    ensure_parent(args.output)
    args.output.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(json.dumps(artifact, indent=2))


if __name__ == "__main__":
    main()
