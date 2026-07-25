"""Provider option dataclass tests (DeepgramOptions / ScribeOptions)."""

from __future__ import annotations

from typing import Any

import pytest

from par_stt.providers.base import (
    DeepgramOptions,
    ScribeOptions,
    get_provider_option_schema,
    options_to_kwargs,
)


def test_deepgram_options_defaults() -> None:
    """Deepgram options should ship sensible defaults."""
    options = DeepgramOptions()
    assert options.model is None
    assert options.smart_format is True
    assert options.punctuate is True
    assert options.profanity_filter is False
    assert options.diarize is False
    assert options.filler_words is False


def test_scribe_options_defaults() -> None:
    """Scribe options should ship sensible defaults."""
    options = ScribeOptions()
    assert options.model is None
    assert options.language_code is None
    assert options.diarize is False
    assert options.tag_audio_events is False


def test_deepgram_options_accepts_model_override() -> None:
    """Model overrides should round-trip through the dataclass."""
    options = DeepgramOptions(model="nova-2", diarize=True)
    assert options.model == "nova-2"
    assert options.diarize is True


def test_scribe_options_accepts_language_code() -> None:
    """Language code overrides should round-trip through the dataclass."""
    options = ScribeOptions(language_code="en", diarize=True, tag_audio_events=True)
    assert options.language_code == "en"
    assert options.diarize is True
    assert options.tag_audio_events is True


def test_deepgram_options_model_must_be_str_or_none() -> None:
    """Non-string model values should raise TypeError in ``__post_init__``."""
    with pytest.raises(TypeError):
        DeepgramOptions(model=123)  # type: ignore[arg-type]


def test_scribe_options_language_code_must_be_str_or_none() -> None:
    """Non-string language_code values should raise TypeError in ``__post_init__``."""
    with pytest.raises(TypeError):
        ScribeOptions(language_code=42)  # type: ignore[arg-type]


def test_options_to_kwargs_drops_none_from_dataclass() -> None:
    """``options_to_kwargs`` should drop None-valued keys by default."""
    kwargs = options_to_kwargs(DeepgramOptions(model=None, diarize=True))
    assert "model" not in kwargs
    assert kwargs["diarize"] is True
    assert kwargs["smart_format"] is True


def test_options_to_kwargs_include_none_keeps_none() -> None:
    """``include_none=True`` should preserve None-valued keys."""
    kwargs = options_to_kwargs(DeepgramOptions(model=None), include_none=True)
    assert kwargs["model"] is None
    assert kwargs["smart_format"] is True


def test_options_to_kwargs_accepts_dict() -> None:
    """Plain dicts should pass through (None still dropped by default)."""
    kwargs = options_to_kwargs({"diarize": True, "model": None})
    assert kwargs == {"diarize": True}


def test_options_to_kwargs_rejects_non_dataclass_non_dict() -> None:
    """Anything that is not a dataclass instance or dict should raise TypeError."""
    with pytest.raises(TypeError):
        options_to_kwargs("not-options")  # type: ignore[arg-type]
    # A dataclass *class* (not instance) should also be rejected.
    with pytest.raises(TypeError):
        options_to_kwargs(DeepgramOptions)  # type: ignore[arg-type]


def test_options_to_kwargs_dict_include_none() -> None:
    """Dict input with ``include_none`` should keep None values."""
    kwargs = options_to_kwargs({"a": 1, "b": None}, include_none=True)
    assert kwargs == {"a": 1, "b": None}


def test_get_provider_option_schema_returns_dataclass() -> None:
    """``get_provider_option_schema`` returns the typed option class per provider."""
    assert get_provider_option_schema("deepgram") is DeepgramOptions
    assert get_provider_option_schema("elevenlabs") is ScribeOptions


def test_get_provider_option_schema_unknown_raises() -> None:
    """Unknown provider names should raise ValueError."""
    with pytest.raises(ValueError):
        get_provider_option_schema("nope")


def test_options_to_kwargs_roundtrips_full_scribe_options() -> None:
    """All populated Scribe fields should survive the kwargs conversion."""
    options = ScribeOptions(model="scribe_v1", language_code="fr", diarize=True, tag_audio_events=True)
    kwargs: dict[str, Any] = options_to_kwargs(options)
    assert kwargs == {
        "model": "scribe_v1",
        "language_code": "fr",
        "diarize": True,
        "tag_audio_events": True,
    }
