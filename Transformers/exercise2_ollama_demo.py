from __future__ import annotations

import json
from urllib import error, request


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "tinyllama"

PROMPTS = [
    "Explain what a quantized model is in simple terms.",
    "Write three bullet points about transformers.",
]


def generate(prompt: str, model: str = MODEL_NAME) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }

    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        OLLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
    except error.URLError as exc:
        raise SystemExit(
            "Could not reach Ollama at http://localhost:11434.\n"
            "Make sure Ollama is installed, running, and that the model has been pulled.\n"
            f"Original error: {exc}"
        ) from exc

    return body["response"].strip()


def main() -> None:
    print(f"Using model: {MODEL_NAME}\n")

    for index, prompt in enumerate(PROMPTS, start=1):
        print(f"Prompt {index}: {prompt}")
        output = generate(prompt)
        print("Response:")
        print(output)
        print("\n" + "-" * 60 + "\n")


if __name__ == "__main__":
    main()
