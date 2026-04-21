from __future__ import annotations

from dataclasses import dataclass
import sys

import torch
from transformers import AutoModel, AutoModelForCausalLM, AutoTokenizer


MODEL_NAME = "gpt2"
PROMPT = "Transformers are powerful because"


@dataclass
class GenerationConfig:
    label: str
    temperature: float
    top_p: float
    max_tokens: int


def print_header(title: str) -> None:
    print(f"\n{'=' * 20} {title} {'=' * 20}")


def configure_output() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def load_components(model_name: str):
    print_header("Loading Model And Tokenizer")
    print(f"Model name: {model_name}")

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    base_model = AutoModel.from_pretrained(model_name)
    generation_model = AutoModelForCausalLM.from_pretrained(model_name)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    generation_model = generation_model.to(device)
    generation_model.eval()

    print(f"Tokenizer vocab size: {tokenizer.vocab_size}")
    print(f"Base model class: {base_model.__class__.__name__}")
    print(f"Generation model class: {generation_model.__class__.__name__}")
    print(f"Device: {device}")

    return tokenizer, base_model, generation_model, device


def show_tokenization_flow(tokenizer, text: str):
    print_header("Tokenization Flow")
    print(f"Input text: {text}")

    tokens = tokenizer.tokenize(text)
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    decoded_text = tokenizer.decode(token_ids)

    safe_tokens = [repr(token) for token in tokens]

    print(f"Tokens: {safe_tokens}")
    print(f"Token IDs: {token_ids}")
    print(f"Decoded from IDs: {decoded_text}")

    return token_ids


def run_base_model_inference(tokenizer, base_model, text: str):
    print_header("Base Model Inference")

    inputs = tokenizer(text, return_tensors="pt")

    with torch.no_grad():
        outputs = base_model(**inputs)

    print(f"Last hidden state shape: {tuple(outputs.last_hidden_state.shape)}")


def generate_text(tokenizer, generation_model, device: str, text: str, config: GenerationConfig):
    print_header(f"Generation - {config.label}")
    print(
        f"Parameters: temperature={config.temperature}, "
        f"top_p={config.top_p}, max_tokens={config.max_tokens}"
    )

    inputs = tokenizer(text, return_tensors="pt").to(device)

    with torch.no_grad():
        output_ids = generation_model.generate(
            **inputs,
            do_sample=True,
            temperature=config.temperature,
            top_p=config.top_p,
            max_new_tokens=config.max_tokens,
            pad_token_id=tokenizer.eos_token_id,
        )

    new_token_ids = output_ids[0][inputs["input_ids"].shape[1] :].tolist()
    generated_text = tokenizer.decode(output_ids[0], skip_special_tokens=True)

    print(f"New output token IDs: {new_token_ids}")
    print(f"Generated text: {generated_text}")


def main():
    configure_output()
    tokenizer, base_model, generation_model, device = load_components(MODEL_NAME)

    show_tokenization_flow(tokenizer, PROMPT)
    run_base_model_inference(tokenizer, base_model, PROMPT)

    configs = [
        GenerationConfig(
            label="Low Temperature",
            temperature=0.7,
            top_p=0.9,
            max_tokens=20,
        ),
        GenerationConfig(
            label="Balanced Sampling",
            temperature=1.0,
            top_p=0.95,
            max_tokens=30,
        ),
        GenerationConfig(
            label="More Creative Sampling",
            temperature=1.3,
            top_p=0.98,
            max_tokens=40,
        ),
    ]

    for config in configs:
        generate_text(tokenizer, generation_model, device, PROMPT, config)


if __name__ == "__main__":
    main()
