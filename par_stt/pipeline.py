"""Reusable transcription pipeline objects for library integrations.

A pipeline keeps one provider instance plus default model/language/options so
long-running applications can issue repeated transcription requests without
rebuilding the same configuration each time.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from par_stt.audio_input import read_audio
from par_stt.provider_factory import create_provider
from par_stt.providers import get_provider_classes
from par_stt.providers.base import (
    AudioInput,
    ProviderOptions,
    SttProvider,
    Transcript,
    TranscriptChunk,
    options_to_kwargs,
)


@dataclass
class TranscriptionPipeline:
    """Pre-configured reusable transcription pipeline.

    Attributes:
        provider: An initialized :class:`~par_stt.providers.base.SttProvider`.
        model: Default model override passed to every transcription call.
        language: Default language hint passed to every transcription call.
        options: Default provider options (dataclass or dict) merged into every
            transcription call.
    """

    provider: SttProvider
    model: str | None = None
    language: str | None = None
    options: ProviderOptions | dict[str, Any] | None = None
    _provider_names: list[str] = field(default_factory=list, init=False, repr=False)

    @classmethod
    def from_provider_name(
        cls,
        provider_name: str,
        *,
        api_key: str | None = None,
        provider_kwargs: dict[str, Any] | None = None,
        model: str | None = None,
        language: str | None = None,
        options: ProviderOptions | dict[str, Any] | None = None,
    ) -> TranscriptionPipeline:
        """Create a pipeline by provider registry name.

        Args:
            provider_name: Provider registry name (e.g. ``"deepgram"``).
            api_key: Optional API key. If omitted, declared environment
                variables are consulted for providers that require keys.
            provider_kwargs: Provider constructor keyword arguments.
            model: Default model override.
            language: Default language hint.
            options: Default provider options.

        Raises:
            ValueError: If ``provider_name`` is not a registered provider.
        """
        providers = get_provider_classes()
        if provider_name not in providers:
            raise ValueError(f"Unknown provider '{provider_name}'. Available: {', '.join(sorted(providers))}")
        provider = create_provider(provider_name, api_key=api_key, provider_kwargs=provider_kwargs)
        return cls(provider=provider, model=model, language=language, options=options)

    def transcribe(
        self,
        audio: AudioInput,
        *,
        language: str | None = None,
        model: str | None = None,
        options: ProviderOptions | dict[str, Any] | None = None,
    ) -> Transcript:
        """Transcribe *audio* with the pipeline defaults plus per-call overrides.

        Always returns a :class:`~par_stt.providers.base.Transcript`. Streaming
        providers drain their async stream into a single transcript here; use
        :meth:`transcribe_async` for native streaming.
        """
        result = self.provider.transcribe(
            audio,
            language=language if language is not None else self.language,
            model=model if model is not None else self.model,
            **self._merged_options(options),
        )
        return _as_transcript(result, language=language)

    def transcribe_file(
        self,
        path: str | Path,
        *,
        language: str | None = None,
        model: str | None = None,
        options: ProviderOptions | dict[str, Any] | None = None,
    ) -> Transcript:
        """Read *path* to canonical PCM and transcribe it."""
        pcm = read_audio(path)
        return self.transcribe(pcm, language=language, model=model, options=options)

    async def transcribe_async(
        self,
        audio: AudioInput,
        *,
        language: str | None = None,
        model: str | None = None,
        options: ProviderOptions | dict[str, Any] | None = None,
    ) -> AsyncIterator[TranscriptChunk]:
        """Native async streaming surface; delegates to the provider."""
        async for chunk in self.provider.transcribe_async(
            audio,
            language=language if language is not None else self.language,
            model=model if model is not None else self.model,
            **self._merged_options(options),
        ):
            yield chunk

    def _merged_options(self, options: ProviderOptions | dict[str, Any] | None) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        if self.options is not None:
            merged.update(options_to_kwargs(self.options))
        if options is not None:
            merged.update(options_to_kwargs(options))
        return merged


def _as_transcript(
    result: Transcript | Iterator[TranscriptChunk],
    *,
    language: str | None,
) -> Transcript:
    """Collapse a provider result into a :class:`Transcript`."""
    if isinstance(result, Transcript):
        return result
    chunks = list(result)
    text = (
        " ".join(chunk.text for chunk in chunks if chunk.is_final).strip()
        or " ".join(chunk.text for chunk in chunks).strip()
    )
    return Transcript(text=text, chunks=chunks, language=language)
