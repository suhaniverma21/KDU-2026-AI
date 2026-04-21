from __future__ import annotations

import ctypes
import os
import sys
from typing import Any

import torch


def configure_output() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def choose_device() -> int:
    return 0 if torch.cuda.is_available() else -1


def get_torch_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def get_model_load_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if not torch.cuda.is_available():
        kwargs["low_cpu_mem_usage"] = True
    return kwargs


def get_total_ram_gb() -> float | None:
    try:
        if os.name == "nt":
            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_phys", ctypes.c_ulonglong),
                    ("avail_phys", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("avail_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("avail_virtual", ctypes.c_ulonglong),
                    ("avail_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(MemoryStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return round(status.total_phys / (1024**3), 1)

        if hasattr(os, "sysconf"):
            page_size = os.sysconf("SC_PAGE_SIZE")
            page_count = os.sysconf("SC_PHYS_PAGES")
            return round((page_size * page_count) / (1024**3), 1)
    except Exception:
        return None

    return None


def format_model_error(exc: Exception) -> str:
    message = str(exc).strip()
    lowered = message.lower()

    if any(
        keyword in lowered
        for keyword in ["huggingface", "download", "resolve/main", "timed out", "connection", "network"]
    ):
        return (
            "Could not download or reach the HuggingFace model files. "
            "Check your internet connection for the first run, or make sure the models already exist in the local cache."
        )

    if "sentencepiece" in lowered:
        return "A required package is missing. Install dependencies again with: pip install -r requirements.txt"

    if any(keyword in lowered for keyword in ["memory", "out of memory", "not enough memory"]):
        return "The machine may not have enough memory to load the models. Try closing other apps or use a smaller model."

    return f"Model loading failed. {message}"
