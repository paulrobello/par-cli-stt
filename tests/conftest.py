"""Shared pytest fixtures for PAR CLI STT tests."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf


@pytest.fixture
def mock_env_api_keys(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Set mock API keys in the environment for both providers."""
    keys = {
        "DEEPGRAM_API_KEY": "test_deepgram_key_12345",
        "DG_API_KEY": "test_dg_key_67890",
        "ELEVENLABS_API_KEY": "test_elevenlabs_key_12345",
    }
    for name, value in keys.items():
        monkeypatch.setenv(name, value)
    return keys


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def temp_audio_file(tmp_path: Path) -> Path:
    """Write a small valid 16 kHz mono WAV file (0.5 s sine) for loader tests."""
    sample_rate = 16_000
    duration = 0.5
    t = np.linspace(0.0, duration, int(sample_rate * duration), endpoint=False, dtype=np.float32)
    waveform = (0.2 * np.sin(2.0 * np.pi * 220.0 * t)).astype(np.float32)
    audio_path = tmp_path / "test_audio.wav"
    buffer = io.BytesIO()
    sf.write(buffer, waveform, sample_rate, format="WAV", subtype="PCM_16")
    audio_path.write_bytes(buffer.getvalue())
    return audio_path


@pytest.fixture
def fake_pcm_bytes() -> bytes:
    """Return raw 16 kHz mono int16 PCM bytes (1 s of silence)."""
    return (np.zeros(16_000, dtype=np.int16)).tobytes()


@pytest.fixture
def fake_transcript() -> object:
    """Return a populated Transcript for CLI/pipeline tests (typed loosely to avoid import cycles)."""
    from par_stt.providers.base import Transcript, TranscriptChunk

    chunk = TranscriptChunk(text="hello world", start_ms=0.0, end_ms=1500.0, is_final=True)
    return Transcript(
        text="hello world",
        chunks=[chunk],
        language="en",
        detected_language="eng",
    )
