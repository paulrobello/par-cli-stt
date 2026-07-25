"""Deepgram STT provider (Nova-3 streaming over WebSocket).

Streaming-first: :meth:`transcribe_async` opens a WebSocket to
``wss://api.deepgram.com/v1/listen`` and yields
:class:`~par_stt.providers.base.TranscriptChunk` instances as Deepgram returns
results (both interim partials and finals).  The synchronous
:meth:`transcribe` is a bridge that drives the async stream to completion and
returns a single aggregated :class:`~par_stt.providers.base.Transcript`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlencode

from websockets.asyncio.client import connect

from par_stt.audio_input import TARGET_SAMPLE_RATE
from par_stt.defaults import DEFAULT_MODELS
from par_stt.errors import ErrorType, SttError
from par_stt.providers.base import (
    AudioInput,
    DeepgramOptions,
    SttProvider,
    Transcript,
    TranscriptChunk,
)
from par_stt.retry import RetryPolicy, run_with_retries

_logger = logging.getLogger(__name__)

DEEPGRAM_STT_WS = "wss://api.deepgram.com/v1/listen"
# Bytes per WebSocket frame when streaming a buffered blob of audio.
_WS_CHUNK_BYTES = 8192
# Deepgram flushes pending finals when it receives this control message.
_CLOSE_STREAM_MESSAGE = json.dumps({"type": "CloseStream"})


class DeepgramProvider(SttProvider):
    """Deepgram Nova-3 streaming speech-to-text provider.

    The constructor performs no network I/O so the provider can be instantiated
    for capability inspection without a key round-trip; the WebSocket is opened
    lazily inside :meth:`transcribe_async`.
    """

    PROVIDER_KWARGS: dict[str, Any] = {
        "smart_format": True,
        "punctuate": True,
        "profanity_filter": False,
        "diarize": False,
        "filler_words": False,
    }

    def __init__(self, api_key: str, **kwargs: Any) -> None:
        """Initialize the Deepgram provider.

        Args:
            api_key: Deepgram API key (sent as ``Authorization: Token <key>``).
            **kwargs: ``retry_attempts`` / ``retry_backoff`` configure the
                :class:`~par_stt.retry.RetryPolicy` used by the sync bridge.
        """
        super().__init__(api_key=api_key, **kwargs)

    @property
    def name(self) -> str:
        return "Deepgram"

    @property
    def supported_formats(self) -> list[str]:
        return ["wav", "mp3", "ogg", "webm", "flac"]

    @property
    def default_model(self) -> str:
        return DEFAULT_MODELS.get("deepgram", "nova-3")

    @property
    def supports_streaming(self) -> bool:
        return True

    async def transcribe_async(
        self,
        audio: AudioInput,
        *,
        language: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[TranscriptChunk]:
        """Stream audio to Deepgram and yield transcript chunks as they arrive.

        Args:
            audio: Canonical PCM bytes (16 kHz mono int16) or a sync iterator
                of byte chunks.  Blocking live-stream iterators should be
                bridged via a thread by the caller; in-memory iterators are
                drained cooperatively.
            language: Optional BCP-47 language hint (e.g. ``"en"`` or ``"en-US"``).
            model: Optional Deepgram model override (defaults to Nova-3).
            **kwargs: Recognised keys mirror :class:`~par_stt.providers.base.DeepgramOptions`
                (``smart_format``, ``punctuate``, ``profanity_filter``,
                ``diarize``, ``filler_words``); an explicit
                ``options=DeepgramOptions(...)`` is also accepted.

        Yields:
            :class:`~par_stt.providers.base.TranscriptChunk` for every
            non-empty Deepgram ``Results`` frame (interim or final).
        """
        if not self.api_key:
            raise SttError("Deepgram API key required", ErrorType.MISSING_API_KEY)

        options = _coerce_deepgram_options(kwargs)
        active_model = model or options.model or self.default_model
        url = _build_listen_url(active_model, language=language, options=options)
        headers = {"Authorization": f"Token {self.api_key}"}

        try:
            async with connect(url, additional_headers=headers) as ws:
                sender = asyncio.create_task(self._stream_audio(ws, audio))
                try:
                    async for raw in ws:
                        parsed = _parse_results_frame(raw)
                        if parsed is not None:
                            yield parsed
                finally:
                    await _await_or_cancel(sender)
        except SttError:
            raise
        except Exception as exc:  # noqa: BLE001 -- map every WS/transport failure to SttError
            raise SttError(
                f"Deepgram streaming request failed: {exc}",
                ErrorType.NETWORK_ERROR,
            ) from exc

    def transcribe(
        self,
        audio: AudioInput,
        *,
        language: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> Transcript:
        """Transcribe *audio* synchronously by draining the async stream.

        Intended for CLI/batch callers that are not already inside an event
        loop.  Async callers should use :meth:`transcribe_async` directly.

        Raises:
            SttError: If called from within a running event loop (use
                :meth:`transcribe_async` instead) or if the stream fails.
        """
        return _drain_async_to_transcript(
            self,
            audio,
            language=language,
            model=model,
            transcribe_kwargs=kwargs,
            retry_policy=self.retry_policy,
        )

    async def _stream_audio(self, ws: Any, audio: AudioInput) -> None:
        """Push every chunk of *audio* to *ws*, then send the close control."""
        if isinstance(audio, (bytes, bytearray)):
            data = bytes(audio)
            for start in range(0, len(data), _WS_CHUNK_BYTES):
                await ws.send(data[start : start + _WS_CHUNK_BYTES])
                await asyncio.sleep(0)
        else:
            for chunk in audio:
                if chunk:
                    await ws.send(chunk)
                    await asyncio.sleep(0)
        await ws.send(_CLOSE_STREAM_MESSAGE)


def _build_listen_url(model: str, *, language: str | None, options: DeepgramOptions) -> str:
    params: dict[str, str] = {
        "model": model,
        "interim_results": "true",
        "punctuate": str(options.punctuate).lower(),
        "smart_format": str(options.smart_format).lower(),
        "profanity_filter": str(options.profanity_filter).lower(),
        "diarize": str(options.diarize).lower(),
        "filler_words": str(options.filler_words).lower(),
        "encoding": "linear16",
        "sample_rate": str(TARGET_SAMPLE_RATE),
        "channels": "1",
        "endpointing": "300",
    }
    if language:
        params["language"] = language
    return f"{DEEPGRAM_STT_WS}?{urlencode(params)}"


def _coerce_deepgram_options(kwargs: dict[str, Any]) -> DeepgramOptions:
    explicit = kwargs.get("options")
    if isinstance(explicit, DeepgramOptions):
        return explicit
    accepted = {"model", "smart_format", "punctuate", "profanity_filter", "diarize", "filler_words"}
    picked = {key: kwargs[key] for key in accepted if key in kwargs}
    return DeepgramOptions(**picked)


def _parse_results_frame(raw: str | bytes) -> TranscriptChunk | None:
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(msg, dict) or msg.get("type") != "Results":
        return None
    channel = msg.get("channel") or {}
    alternatives = channel.get("alternatives") or []
    if not alternatives:
        return None
    text = (alternatives[0].get("transcript") or "").strip()
    if not text:
        return None
    start_s = float(msg.get("start", 0.0) or 0.0)
    duration_s = float(msg.get("duration", 0.0) or 0.0)
    is_final = bool(msg.get("is_final", True))
    return TranscriptChunk(
        text=text,
        start_ms=start_s * 1000.0,
        end_ms=(start_s + duration_s) * 1000.0,
        is_final=is_final,
    )


async def _await_or_cancel(task: asyncio.Task[None]) -> None:
    """Await *task*, cancelling it first if still running.

    A completed task's real exception is re-raised by ``await``; a cancellation
    we triggered ourselves is swallowed.
    """
    if not task.done():
        task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def _collect_async(
    agen: AsyncIterator[TranscriptChunk],
    *,
    language: str | None,
) -> Transcript:
    chunks: list[TranscriptChunk] = []
    finals: list[str] = []
    async for chunk in agen:
        chunks.append(chunk)
        if chunk.is_final:
            finals.append(chunk.text)
    text = " ".join(finals).strip()
    if not text:
        text = " ".join(chunk.text for chunk in chunks).strip()
    return Transcript(text=text, chunks=chunks, language=language)


def _drain_async_to_transcript(
    provider: DeepgramProvider,
    audio: AudioInput,
    *,
    language: str | None,
    model: str | None,
    transcribe_kwargs: dict[str, Any],
    retry_policy: RetryPolicy,
) -> Transcript:
    """Run :meth:`transcribe_async` to completion from a sync context."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise SttError(
            "Deepgram.transcribe() must not be called from a running event loop; await transcribe_async() instead.",
            ErrorType.INVALID_INPUT,
        )

    def _run() -> Transcript:
        return asyncio.run(
            _collect_async(
                provider.transcribe_async(audio, language=language, model=model, **transcribe_kwargs),
                language=language,
            )
        )

    try:
        return run_with_retries(_run, retry_policy, operation="Deepgram transcription")
    except SttError:
        raise
    except Exception as exc:  # noqa: BLE001 -- wrap final retry failure
        raise SttError(f"Deepgram transcription failed: {exc}", ErrorType.NETWORK_ERROR) from exc
