"""Detects speech boundaries and silence using RMS threshold logic."""

from __future__ import annotations

import math

import numpy as np


def calculate_rms(chunk: np.ndarray) -> float:
    """Compute RMS volume for a PCM chunk."""
    float_chunk = chunk.astype(np.float32)
    mean_square = float(np.mean(np.square(float_chunk)))
    return math.sqrt(mean_square)


def required_silent_chunks(
    sample_rate: int,
    chunk_size: int,
    silence_duration_seconds: float,
) -> int:
    """Convert silence duration into a chunk count threshold."""
    chunks = (sample_rate * silence_duration_seconds) / chunk_size
    return max(1, int(chunks))
