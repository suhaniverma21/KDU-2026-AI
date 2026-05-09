import os
import json
from pathlib import Path
from time import perf_counter

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv


class BedrockCloudSafety:
    """Phase 2 Bedrock Guardrails wrapper for threshold experiments."""

    def __init__(self) -> None:
        self.env_path = Path(__file__).resolve().parent.parent / ".env"

    def _load_runtime_config(self) -> tuple[str | None, dict[str, dict[str, str | None]]]:
        load_dotenv(dotenv_path=self.env_path, override=True)
        region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
        profiles = {
            "strict": {
                "guardrail_id": os.getenv("BEDROCK_GUARDRAIL_ID_STRICT"),
                "guardrail_version": os.getenv("BEDROCK_GUARDRAIL_VERSION_STRICT"),
            },
            "relaxed": {
                "guardrail_id": os.getenv("BEDROCK_GUARDRAIL_ID_RELAXED"),
                "guardrail_version": os.getenv("BEDROCK_GUARDRAIL_VERSION_RELAXED"),
            },
        }
        return region, profiles

    def _create_client(self, region: str):
        return boto3.client("bedrock-runtime", region_name=region)

    def _get_profile_config(self, profile: str) -> tuple[dict[str, str], object]:
        region, profiles = self._load_runtime_config()
        normalized = profile.lower()
        if normalized not in profiles:
            raise ValueError(
                f"Unsupported Bedrock profile '{profile}'. Use one of: {', '.join(profiles)}."
            )

        config = profiles[normalized]
        if not region:
            raise RuntimeError(
                "AWS region is not configured. Set AWS_REGION or AWS_DEFAULT_REGION."
            )
        if not config["guardrail_id"] or not config["guardrail_version"]:
            raise RuntimeError(
                f"Bedrock guardrail settings for profile '{normalized}' are missing."
            )
        client = self._create_client(region)
        return (
            {
                "profile": normalized,
                "guardrail_id": str(config["guardrail_id"]),
                "guardrail_version": str(config["guardrail_version"]),
            },
            client,
        )

    @staticmethod
    def _summarize_assessments(response: dict) -> list[dict]:
        summaries = []
        for assessment in response.get("assessments", []):
            content_policy = assessment.get("contentPolicy", {})
            for filter_result in content_policy.get("filters", []):
                summaries.append(
                    {
                        "type": filter_result.get("type"),
                        "confidence": filter_result.get("confidence"),
                        "filter_strength": filter_result.get("filterStrength"),
                        "action": filter_result.get("action"),
                        "detected": filter_result.get("detected"),
                    }
                )
        return summaries

    def evaluate_text(self, text: str, profile: str = "strict") -> dict:
        config, client = self._get_profile_config(profile)
        start = perf_counter()
        try:
            response = client.apply_guardrail(
                guardrailIdentifier=config["guardrail_id"],
                guardrailVersion=config["guardrail_version"],
                source="INPUT",
                content=[
                    {
                        "text": {
                            "text": text,
                        }
                    }
                ],
            )
        except (ClientError, BotoCoreError) as exc:
            raise RuntimeError(f"Bedrock Guardrails request failed: {exc}") from exc

        print(json.dumps(response, indent=2, default=str))

        latency_ms = round((perf_counter() - start) * 1000, 3)
        assessments = self._summarize_assessments(response)
        action = response.get("action", "NONE")
        blocked_message = None
        outputs = response.get("outputs", [])
        if outputs:
            first_text = outputs[0].get("text")
            if first_text:
                blocked_message = first_text

        return {
            "allowed": action != "GUARDRAIL_INTERVENED",
            "action": action,
            "profile": config["profile"],
            "source": "bedrock-guardrails",
            "blocked_message": blocked_message,
            "assessments": assessments,
            "usage": response.get("usage"),
            "latency_ms": latency_ms,
            "raw_response": response,
        }
