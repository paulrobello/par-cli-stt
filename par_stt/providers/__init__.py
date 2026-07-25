"""STT Provider implementations."""

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
from par_stt.providers.deepgram import DeepgramProvider
from par_stt.providers.elevenlabs import ElevenLabsProvider
from par_stt.providers.registry import (
    get_builtin_provider_plugins,
    get_plugin_diagnostics,
    get_provider_classes,
    get_provider_plugin,
    get_provider_plugins,
    list_provider_plugins,
)

__all__ = [
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
    "get_provider_option_schema",
    "options_to_kwargs",
    "DeepgramProvider",
    "ElevenLabsProvider",
    "get_builtin_provider_plugins",
    "get_plugin_diagnostics",
    "get_provider_classes",
    "get_provider_plugin",
    "get_provider_plugins",
    "list_provider_plugins",
]

PROVIDERS = get_provider_classes()
