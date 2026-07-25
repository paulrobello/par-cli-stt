"""ElevenLabs Scribe STT provider (batch REST via the ElevenLabs SDK).

Scribe is a batch (file-in, full-transcript-out) API: it accepts a complete
audio file and returns the transcribed text with detected language and word
timing.  This provider therefore implements :meth:`transcribe` synchronously
and inherits the default async-wrapper :meth:`~par_stt.providers.base.SttProvider.transcribe_async`
so consumers always have a uniform async surface.
"""

from __future__ import annotations

import logging
import warnings
from typing import Any

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="Core Pydantic V1 functionality", category=UserWarning)
    from elevenlabs import ElevenLabs
    from elevenlabs.core import File as ElevenLabsFile

from par_stt.audio_input import materialise
from par_stt.defaults import DEFAULT_MODELS
from par_stt.errors import ErrorType, SttError
from par_stt.http_client import create_http_client
from par_stt.providers.base import (
    AudioInput,
    ScribeOptions,
    SttProvider,
    Transcript,
    TranscriptChunk,
)
from par_stt.retry import run_with_retries

_logger = logging.getLogger(__name__)

DEFAULT_SCRIBE_MODEL = DEFAULT_MODELS.get("elevenlabs", "scribe_v1")


class ElevenLabsProvider(SttProvider):
    """ElevenLabs Scribe speech-to-text provider."""

    PROVIDER_KWARGS: dict[str, Any] = {
        "language_code": None,
        "diarize": False,
        "tag_audio_events": False,
    }

    def __init__(self, api_key: str, **kwargs: Any) -> None:
        """Initialize the ElevenLabs Scribe provider.

        Args:
            api_key: ElevenLabs API key.
            **kwargs: ``timeout`` overrides the shared HTTP client timeout;
                ``retry_attempts`` / ``retry_backoff`` configure the
                :class:`~par_stt.retry.RetryPolicy`.
        """
        super().__init__(api_key=api_key, **kwargs)
        http_client = create_http_client(timeout=kwargs.get("timeout", 60.0))
        self.client = ElevenLabs(api_key=api_key, httpx_client=http_client)

    @property
    def name(self) -> str:
        return "ElevenLabs"

    @property
    def supported_formats(self) -> list[str]:
        return ["mp3", "wav", "m4a", "ogg", "flac", "webm"]

    @property
    def default_model(self) -> str:
        return DEFAULT_SCRIBE_MODEL

    @property
    def supports_streaming(self) -> bool:
        return False

    def transcribe(
        self,
        audio: AudioInput,
        *,
        language: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> Transcript:
        """Transcribe a complete audio file with ElevenLabs Scribe.

        Args:
            audio: Full audio bytes, or a sync iterator of byte chunks that will
                be concatenated.  Pass raw 16 kHz mono int16 PCM with
                ``file_format="pcm_s16le_16"``; container formats (wav/mp3/...)
                are auto-detected.
            language: Optional ISO-639 language hint (mapped to Scribe's
                ``language_code``).
            model: Optional Scribe model override (defaults to ``scribe_v1``).
            **kwargs: ``language_code``, ``diarize``, ``tag_audio_events``,
                ``num_speakers``, ``file_format``; an explicit
                ``options=ScribeOptions(...)`` is also accepted.

        Returns:
            A :class:`~par_stt.providers.base.Transcript` with the full text,
            detected language, and a single timed chunk spanning the audio.
        """
        if not self.api_key:
            raise SttError("ElevenLabs API key required", ErrorType.MISSING_API_KEY)

        options = _coerce_scribe_options(kwargs, language=language)
        active_model = model or options.model or self.default_model
        audio_bytes = materialise(audio)
        if not audio_bytes:
            raise SttError("Cannot transcribe empty audio input", ErrorType.INVALID_AUDIO)

        file_payload: ElevenLabsFile = ("audio", audio_bytes, "application/octet-stream")

        def _call() -> Any:
            return self.client.speech_to_text.convert(
                model_id=active_model,
                file=file_payload,
                language_code=options.language_code,
                diarize=options.diarize or None,
                tag_audio_events=options.tag_audio_events or None,
                file_format=kwargs.get("file_format"),
                num_speakers=kwargs.get("num_speakers"),
            )

        try:
            response = run_with_retries(_call, self.retry_policy, operation="ElevenLabs Scribe transcription")
        except SttError:
            raise
        except Exception as exc:  # noqa: BLE001 -- normalise SDK/network failures
            raise SttError(
                f"ElevenLabs Scribe transcription failed: {exc}",
                ErrorType.NETWORK_ERROR,
            ) from exc

        return _response_to_transcript(response, language=language)


def _coerce_scribe_options(kwargs: dict[str, Any], *, language: str | None) -> ScribeOptions:
    explicit = kwargs.get("options")
    if isinstance(explicit, ScribeOptions):
        merged_language = explicit.language_code or language
        return ScribeOptions(
            model=explicit.model,
            language_code=merged_language,
            diarize=explicit.diarize,
            tag_audio_events=explicit.tag_audio_events,
        )
    accepted = {"model", "language_code", "diarize", "tag_audio_events"}
    picked = {key: kwargs[key] for key in accepted if key in kwargs}
    if language and not picked.get("language_code"):
        picked["language_code"] = language
    return ScribeOptions(**picked)


def _response_to_transcript(response: Any, *, language: str | None) -> Transcript:
    """Map a Scribe convert response onto a :class:`Transcript`.

    Scribe returns one chunk model for mono input and a ``transcripts`` list for
    multichannel input; both are handled.  Each chunk model collapses to a
    single finalized :class:`~par_stt.providers.base.TranscriptChunk` spanning
    its audio duration.
    """
    chunk_models: list[Any] = []
    transcripts = getattr(response, "transcripts", None)
    if transcripts:
        chunk_models.extend(transcripts)
    else:
        chunk_models.append(response)

    parts: list[str] = []
    chunks: list[TranscriptChunk] = []
    detected_language: str | None = None
    for chunk_model in chunk_models:
        text = (getattr(chunk_model, "text", "") or "").strip()
        if not text:
            continue
        parts.append(text)
        if detected_language is None:
            detected_language = getattr(chunk_model, "language_code", None)
        duration_s = getattr(chunk_model, "audio_duration_secs", None)
        end_ms = (float(duration_s) * 1000.0) if duration_s else 0.0
        chunks.append(TranscriptChunk(text=text, start_ms=0.0, end_ms=end_ms, is_final=True))

    full_text = " ".join(parts).strip()
    if not chunks and full_text:
        chunks = [TranscriptChunk(text=full_text, is_final=True)]

    return Transcript(
        text=full_text,
        chunks=chunks,
        language=language,
        detected_language=detected_language,
    )
