"""Central default values for PAR CLI STT.

This module provides default configuration values for all providers
to avoid duplication and ensure consistency.
"""

import os

# Default provider (ElevenLabs Scribe — batch, high accuracy).
DEFAULT_PROVIDER = "elevenlabs"

# Default models by provider.
DEFAULT_MODELS: dict[str, str] = {
    "deepgram": "nova-3",
    "elevenlabs": "scribe_v1",
}

# Default language hint passed to providers. None lets the provider
# auto-detect the spoken language.
DEFAULT_LANGUAGE: str | None = os.getenv("STT_LANGUAGE") or None
