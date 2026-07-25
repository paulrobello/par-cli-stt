"""Emit :class:`~par_stt.providers.base.Transcript` results in common formats.

Supports plain text, JSON (a full structural dump of the transcript and its
chunks), and the timed subtitle formats SRT and WebVTT.  Timed formats use the
``start_ms``/``end_ms`` on each :class:`~par_stt.providers.base.TranscriptChunk`;
when chunks carry no timing, a single cue is synthesised spanning the whole
text.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from par_stt.errors import ErrorType, SttError, handle_error

if TYPE_CHECKING:
    from os import PathLike

    from par_stt.providers.base import Transcript


class TranscriptFormat(StrEnum):
    """Supported transcript output formats."""

    TEXT = "text"
    SRT = "srt"
    VTT = "vtt"
    JSON = "json"

    @classmethod
    def from_value(cls, value: str) -> TranscriptFormat:
        """Resolve a case-insensitive format name to a member.

        Raises:
            SttError: If *value* is not a recognised format.
        """
        normalised = value.strip().lower().lstrip(".")
        try:
            return cls(normalised)
        except ValueError as exc:
            valid = ", ".join(member.value for member in cls)
            handle_error(
                f"Unknown transcript format '{value}'. Valid: {valid}",
                ErrorType.INVALID_INPUT,
                exception=exc,
            )
            raise  # pragma: no cover -- handle_error raises


def render_transcript(transcript: Transcript, fmt: TranscriptFormat | str) -> str:
    """Render *transcript* to a string in the requested format.

    Args:
        transcript: The :class:`~par_stt.providers.base.Transcript` to emit.
        fmt: One of ``"text"``, ``"srt"``, ``"vtt"``, ``"json"`` (case- and
            dot-insensitive).

    Returns:
        The rendered transcript as a string.
    """
    fmt_enum = fmt if isinstance(fmt, TranscriptFormat) else TranscriptFormat.from_value(fmt)
    if fmt_enum is TranscriptFormat.TEXT:
        return transcript.text
    if fmt_enum is TranscriptFormat.JSON:
        return _render_json(transcript)
    if fmt_enum is TranscriptFormat.SRT:
        return _render_timed(transcript, vtt=False)
    if fmt_enum is TranscriptFormat.VTT:
        return _render_timed(transcript, vtt=True)
    # Unreachable: from_value guards the input space.
    raise SttError(f"Unsupported transcript format: {fmt}", ErrorType.INVALID_INPUT)  # pragma: no cover


def write_transcript(
    transcript: Transcript,
    fmt: TranscriptFormat | str,
    output_path: str | PathLike[str],
) -> Path:
    """Render *transcript* and write it to *output_path*.

    Args:
        transcript: The :class:`~par_stt.providers.base.Transcript` to emit.
        fmt: One of ``"text"``, ``"srt"``, ``"vtt"``, ``"json"``.
        output_path: Destination file path (parent directories are created).

    Returns:
        The resolved :class:`~pathlib.Path` that was written.
    """
    fmt_enum = fmt if isinstance(fmt, TranscriptFormat) else TranscriptFormat.from_value(fmt)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = render_transcript(transcript, fmt_enum)
    destination.write_text(content, encoding="utf-8")
    return destination


def _render_json(transcript: Transcript) -> str:
    payload = asdict(transcript) if is_dataclass(transcript) else {"text": str(transcript)}
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _render_timed(transcript: Transcript, *, vtt: bool) -> str:
    cues = _cues_from_transcript(transcript)
    if vtt:
        lines = ["WEBVTT", ""]
        timestamp = _vtt_timestamp
        sep = " --> "
    else:
        lines = []
        timestamp = _srt_timestamp
        sep = " --> "
    for index, (start_ms, end_ms, text) in enumerate(cues, start=1):
        if not vtt:
            lines.append(str(index))
        lines.append(f"{timestamp(start_ms)}{sep}{timestamp(end_ms)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _cues_from_transcript(transcript: Transcript) -> list[tuple[float, float, str]]:
    """Build (start_ms, end_ms, text) cues from transcript chunks.

    Falls back to a single whole-text cue at 0 when chunks lack timing or text.
    """
    timed = [(chunk.start_ms, chunk.end_ms, chunk.text) for chunk in transcript.chunks if chunk.text]
    if timed:
        return timed
    if transcript.text:
        return [(0.0, 0.0, transcript.text)]
    return []


def _srt_timestamp(ms: float) -> str:
    return _format_timestamp(ms, comma=True)


def _vtt_timestamp(ms: float) -> str:
    return _format_timestamp(ms, comma=False)


def _format_timestamp(ms: float, *, comma: bool) -> str:
    total_ms = max(0, int(round(ms)))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    sep = "," if comma else "."
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{sep}{millis:03d}"
