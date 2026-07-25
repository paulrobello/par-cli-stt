"""PAR STT — Streaming speech-to-text library with multiple provider support.

Usage:

    import par_stt

    print(par_stt.__version__)
    print(par_stt.list_providers())

    # Get a provider class
    Deepgram = par_stt.get_provider("deepgram")
    provider = Deepgram(api_key=os.environ["DEEPGRAM_API_KEY"])

    # Batch transcription (sync)
    transcript = provider.transcribe(pcm_bytes, language="en")

    # Native async streaming (interim + final chunks)
    async for chunk in provider.transcribe_async(pcm_bytes):
        print(chunk.text, chunk.is_final)
"""

__version__ = "0.1.0"

from par_stt.audio_input import (
    DEFAULT_CHUNK_BYTES,
    TARGET_SAMPLE_RATE,
    iter_pcm_chunks,
    materialise,
    read_audio,
    resample_pcm,
)
from par_stt.costs import COST_PER_MILLION_MINUTES, CostEstimate, estimate_transcription_cost
from par_stt.defaults import DEFAULT_LANGUAGE, DEFAULT_MODELS, DEFAULT_PROVIDER
from par_stt.errors import ErrorType, SttError
from par_stt.provider_factory import create_provider
from par_stt.providers import PROVIDERS
from par_stt.providers.base import (
    PROVIDER_OPTION_SCHEMAS,
    AudioInput,
    DeepgramOptions,
    ProviderCapabilities,
    ProviderOptions,
    ProviderOptionSchema,
    ProviderPlugin,
    ScribeOptions,
    SttProvider,
    TranscribeAsyncResult,
    TranscribeResult,
    Transcript,
    TranscriptChunk,
    get_provider_option_schema,
    options_to_kwargs,
)
from par_stt.providers.registry import (
    get_builtin_provider_plugins,
    get_plugin_diagnostics,
    get_provider_plugin,
    get_provider_plugins,
    list_provider_plugins,
)
from par_stt.retry import RetryPolicy
from par_stt.transcript_writer import TranscriptFormat, render_transcript, write_transcript

__all__ = [
    "__version__",
    "SttProvider",
    "Transcript",
    "TranscriptChunk",
    "AudioInput",
    "TranscribeResult",
    "TranscribeAsyncResult",
    "ProviderCapabilities",
    "ProviderPlugin",
    "ProviderOptions",
    "ProviderOptionSchema",
    "PROVIDER_OPTION_SCHEMAS",
    "DeepgramOptions",
    "ScribeOptions",
    "PROVIDERS",
    "SttError",
    "ErrorType",
    "RetryPolicy",
    "CostEstimate",
    "COST_PER_MILLION_MINUTES",
    "TranscriptFormat",
    "DEFAULT_PROVIDER",
    "DEFAULT_MODELS",
    "DEFAULT_LANGUAGE",
    "TARGET_SAMPLE_RATE",
    "DEFAULT_CHUNK_BYTES",
    "get_provider",
    "create_provider",
    "list_providers",
    "get_provider_plugin",
    "get_provider_plugins",
    "get_builtin_provider_plugins",
    "list_provider_plugins",
    "get_plugin_diagnostics",
    "get_provider_option_schema",
    "options_to_kwargs",
    "read_audio",
    "iter_pcm_chunks",
    "materialise",
    "resample_pcm",
    "write_transcript",
    "render_transcript",
    "estimate_transcription_cost",
    "collect_diagnostics",
]


def get_provider(name: str) -> type[SttProvider]:
    """Get a provider class by name.

    Args:
        name: Provider identifier (e.g. ``"deepgram"``, ``"elevenlabs"``).

    Returns:
        The provider class (not an instance).

    Raises:
        ValueError: If the provider name is not recognized.
    """
    if name not in PROVIDERS:
        raise ValueError(f"Unknown provider '{name}'. Available: {', '.join(sorted(PROVIDERS))}")
    return PROVIDERS[name]


def list_providers() -> list[str]:
    """Return a sorted list of available provider names."""
    return sorted(PROVIDERS.keys())


def collect_diagnostics() -> list[str]:
    """Return a list of human-readable provider-registry diagnostic messages.

    Currently surfaces messages from the last entry-point plugin discovery
    pass. Exposed as a stable hook for the CLI and consumers; richer
    diagnostics land in a later chunk.
    """
    return get_plugin_diagnostics()
