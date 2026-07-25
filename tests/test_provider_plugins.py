"""Provider plugin registry tests."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from par_stt.providers.base import (
    ProviderCapabilities,
    ProviderPlugin,
    SttProvider,
    Transcript,
    TranscriptChunk,
)


class FakeEntryPoint:
    """Minimal entry point test double."""

    def __init__(self, name: str, loaded: Any = None, error: Exception | None = None) -> None:
        self.name = name
        self._loaded = loaded
        self._error = error

    def load(self) -> Any:
        if self._error is not None:
            raise self._error
        return self._loaded


class MinimalSttProvider(SttProvider):
    """Provider class used to test entry-point normalization and async wrapping."""

    plugin_name = "minimal"
    plugin_description = "Minimal STT provider"
    plugin_capabilities = {
        "formats": ["wav"],
        "supports_streaming": False,
        "supports_language_detection": True,
    }
    plugin_default_model = "minimal-model"
    plugin_requires_api_key = False

    def transcribe(
        self,
        audio: bytes | Iterator[bytes],
        *,
        language: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> Transcript:
        del audio, kwargs
        chunk = TranscriptChunk(text="hello world", start_ms=0.0, end_ms=1000.0, is_final=True)
        return Transcript(
            text="hello world",
            chunks=[chunk],
            language=language,
            detected_language="eng",
        )

    @property
    def name(self) -> str:
        return "Minimal"

    @property
    def supported_formats(self) -> list[str]:
        return ["wav"]

    @property
    def default_model(self) -> str:
        return "minimal-model"

    @property
    def supports_streaming(self) -> bool:
        return False


def test_builtin_provider_plugins_are_discoverable() -> None:
    """Built-in providers should be plugin descriptors with capability metadata."""
    from par_stt.providers.registry import get_provider_plugins

    plugins = get_provider_plugins(refresh=True, include_entry_points=False)

    assert set(plugins) == {"deepgram", "elevenlabs"}
    assert plugins["deepgram"].capabilities.supports_streaming is True
    assert plugins["deepgram"].capabilities.supports_language_detection is True
    assert plugins["deepgram"].capabilities.supports_punctuation is True
    assert "wav" in plugins["deepgram"].capabilities.formats
    assert plugins["deepgram"].default_model == "nova-3"
    assert plugins["deepgram"].api_key_env_vars == ("DEEPGRAM_API_KEY", "DG_API_KEY")
    assert plugins["deepgram"].cost_per_million_minutes == 4300.0

    assert plugins["elevenlabs"].capabilities.supports_streaming is False
    assert plugins["elevenlabs"].default_model == "scribe_v1"
    assert plugins["elevenlabs"].api_key_env_vars == ("ELEVENLABS_API_KEY",)


def test_providers_mapping_is_derived_from_plugins() -> None:
    """``PROVIDERS`` should map names to the built-in provider classes."""
    from par_stt.providers import PROVIDERS
    from par_stt.providers.deepgram import DeepgramProvider
    from par_stt.providers.elevenlabs import ElevenLabsProvider

    assert PROVIDERS["deepgram"] is DeepgramProvider
    assert PROVIDERS["elevenlabs"] is ElevenLabsProvider
    assert set(PROVIDERS) == {"deepgram", "elevenlabs"}


def test_builtin_providers_instantiate_without_network() -> None:
    """Constructors must not perform network I/O so capability inspection is safe."""
    from par_stt.providers.deepgram import DeepgramProvider
    from par_stt.providers.elevenlabs import ElevenLabsProvider

    deepgram = DeepgramProvider("dummy-key")
    elevenlabs = ElevenLabsProvider("dummy-key")

    assert deepgram.name == "Deepgram"
    assert deepgram.supports_streaming is True
    assert deepgram.default_model == "nova-3"
    assert elevenlabs.name == "ElevenLabs"
    assert elevenlabs.supports_streaming is False
    assert elevenlabs.default_model == "scribe_v1"


def test_transcribe_async_is_available_on_both_providers() -> None:
    """Every provider exposes the async streaming surface."""
    from par_stt.providers.deepgram import DeepgramProvider
    from par_stt.providers.elevenlabs import ElevenLabsProvider

    assert callable(getattr(DeepgramProvider, "transcribe_async", None))
    assert callable(getattr(ElevenLabsProvider, "transcribe_async", None))


def test_batch_provider_inherits_async_wrapping_sync() -> None:
    """The default ``transcribe_async`` should unwrap a sync ``Transcript``."""
    provider = MinimalSttProvider()
    chunks: list[TranscriptChunk] = []

    async def _drain() -> None:
        async for chunk in provider.transcribe_async(b"audio"):
            chunks.append(chunk)

    asyncio.run(_drain())

    assert len(chunks) == 1
    assert chunks[0].text == "hello world"
    assert chunks[0].is_final is True


def test_entry_point_provider_plugin_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Entry point objects returning a ProviderPlugin should be registered."""
    from par_stt.providers.registry import metadata

    plugin = ProviderPlugin(
        name="external",
        provider_class=MinimalSttProvider,
        description="External provider",
        capabilities=ProviderCapabilities(formats=["mp3"]),
        default_model="external-model",
        requires_api_key=False,
        source="test",
    )
    monkeypatch.setattr(
        metadata, "entry_points", lambda group=None: [FakeEntryPoint("external", plugin)] if group else []
    )

    from par_stt.providers.registry import get_provider_plugins

    plugins = get_provider_plugins(refresh=True)

    assert plugins["external"].provider_class is MinimalSttProvider
    assert plugins["external"].source == "test"


def test_entry_point_provider_class_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Entry point provider classes should be normalized to a ProviderPlugin."""
    from par_stt.providers.registry import get_provider_plugins, metadata

    monkeypatch.setattr(
        metadata, "entry_points", lambda group=None: [FakeEntryPoint("minimal", MinimalSttProvider)] if group else []
    )

    plugins = get_provider_plugins(refresh=True)

    assert plugins["minimal"].provider_class is MinimalSttProvider
    assert plugins["minimal"].description == "Minimal STT provider"
    assert plugins["minimal"].capabilities.supports_language_detection is True
    assert plugins["minimal"].default_model == "minimal-model"
    assert plugins["minimal"].requires_api_key is False


def test_broken_entry_point_is_ignored_with_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bad plugins should not block built-ins and should expose diagnostics."""
    from par_stt.providers.registry import get_plugin_diagnostics, get_provider_plugins, metadata

    monkeypatch.setattr(
        metadata, "entry_points", lambda group=None: [FakeEntryPoint("broken", error=RuntimeError("boom"))] if group else []
    )

    plugins = get_provider_plugins(refresh=True)
    diagnostics = get_plugin_diagnostics()

    assert "deepgram" in plugins
    assert "broken" not in plugins
    assert any("broken" in diagnostic and "boom" in diagnostic for diagnostic in diagnostics)


def test_factory_resolves_env_var_api_key(mock_env_api_keys: dict[str, str]) -> None:
    """The factory should pick up declared env vars when no key is passed."""
    from par_stt.provider_factory import create_provider

    provider = create_provider("deepgram")
    assert provider.api_key == mock_env_api_keys["DEEPGRAM_API_KEY"]


def test_factory_raises_for_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A key-less instantiation of a key-requiring provider must raise SttError."""
    from par_stt.errors import ErrorType, SttError
    from par_stt.provider_factory import create_provider

    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.delenv("DG_API_KEY", raising=False)

    with pytest.raises(SttError) as exc_info:
        create_provider("deepgram")
    assert exc_info.value.error_type is ErrorType.MISSING_API_KEY


def test_factory_raises_for_unknown_provider() -> None:
    """An unknown provider name must raise an INVALID_PROVIDER SttError."""
    from par_stt.errors import ErrorType, SttError
    from par_stt.provider_factory import create_provider

    with pytest.raises(SttError) as exc_info:
        create_provider("nope")
    assert exc_info.value.error_type is ErrorType.INVALID_PROVIDER


def test_get_provider_and_list_providers_public_api() -> None:
    """``get_provider`` returns the class; ``list_providers`` returns sorted names."""
    import par_stt
    from par_stt.providers.deepgram import DeepgramProvider

    assert par_stt.get_provider("deepgram") is DeepgramProvider
    assert par_stt.list_providers() == ["deepgram", "elevenlabs"]
    with pytest.raises(ValueError):
        par_stt.get_provider("nope")


def test_transcribe_async_alias_type_is_exported() -> None:
    """The async streaming type alias must be part of the public surface."""
    import par_stt

    assert "TranscribeAsyncResult" in par_stt.__all__
    assert hasattr(par_stt, "TranscribeAsyncResult")
