"""Central default values for PAR CLI STT.

This module provides default configuration values for all providers
to avoid duplication and ensure consistency.
"""

import os

# Default provider (Deepgram Nova-3 — streaming-first).
DEFAULT_PROVIDER = "deepgram"

# Default models by provider.
DEFAULT_MODELS: dict[str, str] = {
    "deepgram": "nova-3",
    "elevenlabs": "scribe_v1",
}

# Default language hint passed to providers. None lets the provider
# auto-detect the spoken language.
DEFAULT_LANGUAGE: str | None = os.getenv("STT_LANGUAGE") or None
