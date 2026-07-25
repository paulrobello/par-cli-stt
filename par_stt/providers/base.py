"""Base class for STT providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, TypeAlias

from par_stt.retry import RetryPolicy

# Input audio may be a complete byte blob or a streaming iterator of chunks.
AudioInput: TypeAlias = bytes | Iterator[bytes]
# Result of a transcription: a complete transcript, or an iterator of chunks
# emitted as the audio is processed (streaming providers).
TranscribeResult: TypeAlias = "Transcript | Iterator[TranscriptChunk]"
# Async streaming surface (see ``SttProvider.transcribe_async``). Streaming
# providers override it natively; batch providers inherit a sync-wrapping
# default. Kept as a type alias so consumers can annotate uniformly.
TranscribeAsyncResult: TypeAlias = "AsyncIterator[TranscriptChunk]"


@dataclass
class TranscriptChunk:
    """A single unit of transcribed text emitted by a provider.

    Attributes:
        text: The transcribed text for this chunk.
        start_ms: Start time of the chunk in milliseconds.
        end_ms: End time of the chunk in milliseconds.
        is_final: True for finalized chunks, False for streaming partials.
    """

    text: str
    start_ms: float = 0.0
    end_ms: float = 0.0
    is_final: bool = True


@dataclass
class Transcript:
    """Aggregate transcription result.

    Attributes:
        text: Full transcribed text.
        chunks: Ordered list of transcript chunks with timing.
        language: Language hint requested for transcription, if any.
        detected_language: Language auto-detected by the provider, if any.
    """

    text: str
    chunks: list[TranscriptChunk] = field(default_factory=list)
    language: str | None = None
    detected_language: str | None = None


@dataclass(frozen=True)
class ProviderCapabilities:
    """Static provider capability metadata used without instantiation."""

    formats: list[str]
    supports_streaming: bool = False
    supports_language_detection: bool = False
    supports_diarization: bool = False
    supports_punctuation: bool = False
    supports_profanity_filter: bool = False
    supports_smart_format: bool = False


@dataclass(frozen=True)
class ProviderPlugin:
    """Provider plugin descriptor.

    Descriptors are intentionally static so commands like ``--capabilities`` can
    inspect providers without requiring API keys or creating network clients.
    """

    name: str
    provider_class: type[SttProvider]
    description: str
    capabilities: ProviderCapabilities
    default_model: str
    requires_api_key: bool = True
    api_key_env_vars: tuple[str, ...] = ()
    source: str = "builtin"
    cost_per_million_minutes: float | None = None


class SttProvider(ABC):
    """Abstract base class for streaming speech-to-text providers."""

    # Subclasses override this to declare which kwargs they accept for
    # ``transcribe()``.  Keys are kwarg names; values are defaults.  The CLI
    # uses this mapping to build provider-specific option dicts without
    # if/elif chains.
    PROVIDER_KWARGS: dict[str, Any] = {}

    def __init__(self, api_key: str | None = None, **kwargs: Any):
        """
        Initialize the STT provider.

        Args:
            api_key: Optional API key for the provider. Offline providers do not need it.
            **kwargs: Additional provider-specific configuration. Recognized
                keys include ``retry_attempts`` (int) and ``retry_backoff``
                (float) which configure the provider's :class:`RetryPolicy`.
        """
        self.api_key = api_key
        self.retry_policy = RetryPolicy(
            retry_attempts=int(kwargs.get("retry_attempts", 0)),
            backoff_seconds=float(kwargs.get("retry_backoff", 0.0)),
        )

    @abstractmethod
    def transcribe(
        self,
        audio: AudioInput,
        *,
        language: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> TranscribeResult:
        """
        Transcribe audio into text.

        Args:
            audio: Input audio as bytes or an iterator of byte chunks.
            language: Optional language hint (e.g. ``"en"``).
            model: Optional model override (provider-specific).
            **kwargs: Additional provider-specific parameters.

        Returns:
            A :class:`Transcript` for batch providers, or an iterator of
            :class:`TranscriptChunk` for streaming providers.
        """
        pass

    async def transcribe_async(
        self,
        audio: AudioInput,
        *,
        language: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[TranscriptChunk]:
        """Transcribe audio as an async stream of :class:`TranscriptChunk`.

        Streaming providers (e.g. Deepgram Nova-3 over WebSocket) override
        this with a native implementation. Batch providers do not need to
        override it: the default wraps the synchronous :meth:`transcribe`
        call, yielding the resulting chunks (or a single chunk synthesised
        from a returned :class:`Transcript`) so callers always have a uniform
        async-streaming surface.

        Args:
            audio: Input audio as bytes or a sync iterator of byte chunks.
            language: Optional language hint (e.g. ``"en"``).
            model: Optional model override (provider-specific).
            **kwargs: Additional provider-specific parameters.

        Yields:
            :class:`TranscriptChunk` instances as they are produced. For
            batch providers every chunk is finalized (``is_final=True``).
        """
        result = self.transcribe(audio, language=language, model=model, **kwargs)
        if isinstance(result, Transcript):
            if result.chunks:
                for chunk in result.chunks:
                    yield chunk
            elif result.text:
                yield TranscriptChunk(text=result.text, is_final=True)
            return
        for chunk in result:
            yield chunk

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass

    @property
    @abstractmethod
    def supported_formats(self) -> list[str]:
        """List of supported input audio formats (e.g. ``["wav", "mp3"]``)."""
        pass

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Default model for this provider."""
        pass

    @property
    @abstractmethod
    def supports_streaming(self) -> bool:
        """Whether this provider streams partial transcript chunks."""
        pass


@dataclass
class DeepgramOptions:
    """Deepgram Nova-3 transcription options.

    Attributes:
        model: Deepgram model name (default handled by the provider).
        smart_format: Apply Deepgram "smart format" post-processing.
        punctuate: Add punctuation to the transcript.
        profanity_filter: Mask profanity in the transcript.
        diarize: Label distinct speakers in the transcript.
        filler_words: Include filler words (um, uh) in the transcript.
    """

    model: str | None = None
    smart_format: bool = True
    punctuate: bool = True
    profanity_filter: bool = False
    diarize: bool = False
    filler_words: bool = False

    def __post_init__(self) -> None:
        if self.model is not None and not isinstance(self.model, str):
            raise TypeError("model must be a string or None")


@dataclass
class ScribeOptions:
    """ElevenLabs Scribe transcription options.

    Attributes:
        model: Scribe model name (default handled by the provider).
        language_code: Optional ISO-639-1 language hint.
        diarize: Label distinct speakers in the transcript.
        tag_audio_events: Tag non-speech audio events in the transcript.
    """

    model: str | None = None
    language_code: str | None = None
    diarize: bool = False
    tag_audio_events: bool = False

    def __post_init__(self) -> None:
        if self.language_code is not None and not isinstance(self.language_code, str):
            raise TypeError("language_code must be a string or None")


ProviderOptions: TypeAlias = DeepgramOptions | ScribeOptions
ProviderOptionSchema: TypeAlias = type[DeepgramOptions] | type[ScribeOptions]

PROVIDER_OPTION_SCHEMAS: dict[str, ProviderOptionSchema] = {
    "deepgram": DeepgramOptions,
    "elevenlabs": ScribeOptions,
}


def get_provider_option_schema(provider: str) -> ProviderOptionSchema:
    """Return the typed option dataclass for a provider name.

    Raises:
        ValueError: If *provider* is not a known provider name.
    """
    try:
        return PROVIDER_OPTION_SCHEMAS[provider]
    except KeyError as exc:
        raise ValueError(
            f"Unknown provider '{provider}'. Available: {', '.join(sorted(PROVIDER_OPTION_SCHEMAS))}"
        ) from exc


def options_to_kwargs(options: ProviderOptions | dict[str, Any], *, include_none: bool = False) -> dict[str, Any]:
    """Convert typed provider options to ``transcribe`` keyword arguments.

    Args:
        options: A provider options dataclass instance or a plain dict.
        include_none: When True, keep keys whose value is None.

    Returns:
        Dict of keyword arguments suitable for :meth:`SttProvider.transcribe`.

    Raises:
        TypeError: If *options* is not a dataclass instance or dict.
    """
    if isinstance(options, dict):
        data = dict(options)
    elif is_dataclass(options) and not isinstance(options, type):
        data = asdict(options)
    else:
        raise TypeError("options must be a provider options dataclass or dict")
    if include_none:
        return data
    return {key: value for key, value in data.items() if value is not None}
