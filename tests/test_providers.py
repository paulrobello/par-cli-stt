"""Pure-logic unit tests for provider helpers (no network calls).

The live WebSocket (Deepgram) and REST (ElevenLabs Scribe) transports are
integration-gated, but the frame parsers, URL/option builders, response
mappers, audio loader, and transcript writer are pure functions exercised here
with canned inputs.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from par_stt.providers.base import (
    DeepgramOptions,
    ScribeOptions,
    Transcript,
    TranscriptChunk,
)
from par_stt.transcript_writer import TranscriptFormat, render_transcript, write_transcript


# -- Deepgram pure helpers -----------------------------------------------------


def test_deepgram_parse_results_frame_maps_final() -> None:
    from par_stt.providers.deepgram import _parse_results_frame

    frame = json.dumps(
        {
            "type": "Results",
            "start": 1.5,
            "duration": 0.25,
            "is_final": True,
            "channel": {"alternatives": [{"transcript": "hello world", "confidence": 0.99}]},
        }
    )
    chunk = _parse_results_frame(frame)
    assert chunk is not None
    assert chunk.text == "hello world"
    assert chunk.is_final is True
    assert chunk.start_ms == pytest.approx(1500.0)
    assert chunk.end_ms == pytest.approx(1750.0)


def test_deepgram_parse_results_frame_maps_interim_partial() -> None:
    from par_stt.providers.deepgram import _parse_results_frame

    frame = json.dumps(
        {
            "type": "Results",
            "start": 0.0,
            "duration": 0.1,
            "is_final": False,
            "channel": {"alternatives": [{"transcript": "hel"}]},
        }
    )
    chunk = _parse_results_frame(frame)
    assert chunk is not None
    assert chunk.text == "hel"
    assert chunk.is_final is False


def test_deepgram_parse_results_frame_ignores_non_results_and_empty() -> None:
    from par_stt.providers.deepgram import _parse_results_frame

    metadata = json.dumps({"type": "Metadata", "request_id": "abc"})
    assert _parse_results_frame(metadata) is None
    assert _parse_results_frame("not json") is None
    empty = json.dumps(
        {"type": "Results", "is_final": True, "channel": {"alternatives": [{"transcript": ""}]}}
    )
    assert _parse_results_frame(empty) is None


def test_deepgram_build_listen_url_carries_model_options_and_language() -> None:
    from par_stt.providers.deepgram import _build_listen_url

    url = _build_listen_url(
        "nova-3",
        language="en-US",
        options=DeepgramOptions(smart_format=True, punctuate=True, profanity_filter=True, diarize=True),
    )
    assert url.startswith("wss://api.deepgram.com/v1/listen?")
    assert "model=nova-3" in url
    assert "language=en-US" in url
    assert "encoding=linear16" in url
    assert "sample_rate=16000" in url
    assert "interim_results=true" in url
    assert "smart_format=true" in url
    assert "punctuate=true" in url
    assert "profanity_filter=true" in url
    assert "diarize=true" in url


def test_deepgram_coerce_options_accepts_kwargs_and_explicit_dataclass() -> None:
    from par_stt.providers.deepgram import _coerce_deepgram_options

    coerced = _coerce_deepgram_options({"punctuate": False, "diarize": True, "ignored": "x"})
    assert isinstance(coerced, DeepgramOptions)
    assert coerced.punctuate is False
    assert coerced.diarize is True

    explicit = DeepgramOptions(smart_format=False)
    assert _coerce_deepgram_options({"options": explicit, "punctuate": True}) is explicit


# -- ElevenLabs pure helpers ---------------------------------------------------


def test_elevenlabs_response_to_transcript_mono() -> None:
    from par_stt.providers.elevenlabs import _response_to_transcript

    response = SimpleNamespace(
        text="hello world",
        language_code="eng",
        language_probability=0.99,
        words=[],
        audio_duration_secs=2.5,
    )
    transcript = _response_to_transcript(response, language="en")
    assert transcript.text == "hello world"
    assert transcript.detected_language == "eng"
    assert transcript.language == "en"
    assert len(transcript.chunks) == 1
    assert transcript.chunks[0].is_final is True
    assert transcript.chunks[0].end_ms == pytest.approx(2500.0)


def test_elevenlabs_response_to_transcript_multichannel() -> None:
    from par_stt.providers.elevenlabs import _response_to_transcript

    response = SimpleNamespace(
        transcripts=[
            SimpleNamespace(text="channel one", language_code="eng", words=[], audio_duration_secs=None),
            SimpleNamespace(text="channel two", language_code="eng", words=[], audio_duration_secs=None),
        ]
    )
    transcript = _response_to_transcript(response, language=None)
    assert transcript.text == "channel one channel two"
    assert len(transcript.chunks) == 2


def test_elevenlabs_coerce_scribe_options_merges_language_hint() -> None:
    from par_stt.providers.elevenlabs import _coerce_scribe_options

    opts = _coerce_scribe_options({"diarize": True}, language="fr")
    assert isinstance(opts, ScribeOptions)
    assert opts.language_code == "fr"
    assert opts.diarize is True

    explicit = _coerce_scribe_options({"options": ScribeOptions(language_code="de")}, language="fr")
    assert explicit.language_code == "de"  # explicit options win over the language hint


# -- Audio input ---------------------------------------------------------------


def test_read_audio_returns_16k_mono_int16_pcm(temp_audio_file: Any) -> None:
    from par_stt.audio_input import read_audio

    pcm = read_audio(str(temp_audio_file))
    assert isinstance(pcm, bytes)
    # int16 frames -> byte length is even and corresponds to ~0.5 s at 16 kHz.
    assert len(pcm) % 2 == 0
    frames = len(pcm) // 2
    assert 7_000 <= frames <= 9_000  # ~8000 frames for 0.5s @ 16kHz with some slack
    samples = np.frombuffer(pcm, dtype=np.int16)
    assert samples.dtype == np.int16
    assert int(np.max(np.abs(samples))) > 0  # the sine wave is non-trivial


def test_iter_pcm_chunks_slices_buffer() -> None:
    from par_stt.audio_input import iter_pcm_chunks

    buf = bytes(range(20))
    chunks = list(iter_pcm_chunks(buf, chunk_bytes=8))
    assert b"".join(chunks) == buf
    assert all(len(c) == 8 for c in chunks[:-1])
    with pytest.raises(ValueError):
        list(iter_pcm_chunks(buf, chunk_bytes=0))


def test_materialise_handles_bytes_and_iterator() -> None:
    from par_stt.audio_input import materialise

    assert materialise(b"abc") == b"abc"
    assert materialise(iter([b"ab", b"c"])) == b"abc"


# -- Transcript writer ---------------------------------------------------------


def _sample_transcript() -> Transcript:
    return Transcript(
        text="hello world",
        chunks=[TranscriptChunk(text="hello world", start_ms=0.0, end_ms=1500.0, is_final=True)],
        language="en",
        detected_language="eng",
    )


def test_render_transcript_text_and_json() -> None:
    text_out = render_transcript(_sample_transcript(), TranscriptFormat.TEXT)
    assert text_out == "hello world"

    json_out = render_transcript(_sample_transcript(), "json")
    payload = json.loads(json_out)
    assert payload["text"] == "hello world"
    assert payload["detected_language"] == "eng"
    assert payload["chunks"][0]["end_ms"] == 1500.0


def test_render_transcript_srt_and_vtt_timing() -> None:
    srt = render_transcript(_sample_transcript(), "srt")
    assert srt.startswith("1\n")
    assert "00:00:00,000 --> 00:00:01,500" in srt
    assert srt.rstrip().endswith("hello world")

    vtt = render_transcript(_sample_transcript(), "vtt")
    assert vtt.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:01.500" in vtt


def test_render_transcript_accepts_dot_prefixed_format() -> None:
    assert render_transcript(_sample_transcript(), ".text") == "hello world"


def test_write_transcript_writes_file(tmp_path: Any) -> None:
    out = write_transcript(_sample_transcript(), "srt", tmp_path / "nested" / "out.srt")
    assert out.exists()
    assert "hello world" in out.read_text(encoding="utf-8")


def test_render_transcript_unknown_format_raises() -> None:
    from par_stt.errors import ErrorType, SttError

    with pytest.raises(SttError) as exc_info:
        render_transcript(_sample_transcript(), "pdf")
    assert exc_info.value.error_type is ErrorType.INVALID_INPUT


def test_render_transcript_handles_empty_chunks() -> None:
    empty = Transcript(text="fallback only")
    assert render_transcript(empty, "text") == "fallback only"
    srt = render_transcript(empty, "srt")
    assert "fallback only" in srt
