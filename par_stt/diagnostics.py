"""Offline diagnostics for PAR CLI STT.

Every check here is safe to run without a network connection or an API key.
The CLI exposes them for programmatic use and future ``doctor`` surfaces; the
factory/registry diagnostics (``par_stt.get_plugin_diagnostics``) complement
these with plugin-discovery messages.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import platformdirs

from par_stt.providers import get_provider_plugins


@dataclass(frozen=True)
class DiagnosticCheck:
    """One diagnostic check result."""

    name: str
    ok: bool
    detail: str


def check_environment() -> list[DiagnosticCheck]:
    """Check provider API-key environment variables without revealing values."""
    checks: list[DiagnosticCheck] = []
    seen: set[str] = set()
    for plugin in get_provider_plugins().values():
        if not plugin.requires_api_key:
            continue
        for env_var in plugin.api_key_env_vars:
            if env_var in seen:
                continue
            seen.add(env_var)
            value = os.getenv(env_var)
            checks.append(
                DiagnosticCheck(
                    env_var,
                    bool(value),
                    "set" if value else "not set",
                )
            )
    return checks


def check_config_file() -> list[DiagnosticCheck]:
    """Check whether a par-stt config file exists and is readable."""
    config_path = Path(platformdirs.user_config_dir("par-stt")) / "config.yaml"
    exists = config_path.exists()
    if not exists:
        return [DiagnosticCheck("config file", False, f"not found at {config_path}")]
    return [DiagnosticCheck("config file", True, str(config_path))]


def check_audio_input() -> list[DiagnosticCheck]:
    """Check that the audio loader backend (libsndfile via soundfile) is importable."""
    try:
        import soundfile  # noqa: F401 -- import probe
    except Exception as exc:  # noqa: BLE001 -- any import failure is a backend failure
        return [DiagnosticCheck("soundfile (libsndfile)", False, f"import failed: {exc}")]
    # Report the bundled libsndfile version when available.
    detail = getattr(soundfile, "__version__", "available")
    return [DiagnosticCheck("soundfile (libsndfile)", True, detail)]


def check_streaming_backend() -> list[DiagnosticCheck]:
    """Check for the optional ``ffmpeg`` binary used by some audio conversions."""
    ffmpeg = shutil.which("ffmpeg")
    return [
        DiagnosticCheck(
            "ffmpeg",
            ffmpeg is not None,
            ffmpeg or "not found (only required for some container formats)",
        )
    ]


def collect_diagnostics() -> list[DiagnosticCheck]:
    """Collect all offline diagnostics as a flat list.

    Each entry is a :class:`DiagnosticCheck` with a descriptive ``name``, an
    ``ok`` flag, and a human-readable ``detail`` string. Safe to run without
    network access or API keys.
    """
    checks: list[DiagnosticCheck] = []
    checks.extend(check_environment())
    checks.extend(check_config_file())
    checks.extend(check_audio_input())
    checks.extend(check_streaming_backend())
    return checks
