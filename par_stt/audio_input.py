"""Audio input loading and resampling helpers.

Both ElevenLabs Scribe and Deepgram Nova-3 expect audio near 16 kHz mono
16-bit PCM (Scribe accepts ``pcm_s16le_16``; Nova-3 streams 16 kHz Linear16
over its WebSocket).  These helpers normalise arbitrary input -- a file path,
raw bytes, or a streaming iterator of bytes -- into that canonical shape and
provide a chunk iterator for streaming consumers.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import soundfile as sf

from par_stt.errors import ErrorType, handle_error

if TYPE_CHECKING:
    from os import PathLike

_logger = logging.getLogger(__name__)

# Target delivery format for every provider we ship.
TARGET_SAMPLE_RATE = 16_000
TARGET_CHANNELS = 1
# int16 sample width, used when re-packing floats back into PCM bytes.
_INT16_DTYPE = np.int16

# How many bytes to emit per yielded chunk when iterating canonical PCM.
DEFAULT_CHUNK_BYTES = 8192


def read_audio(path: str | PathLike[str]) -> bytes:
    """Load audio from *path* and return 16 kHz mono 16-bit little-endian PCM.

    The file is read via :mod:`soundfile` (libsndfile backend), which handles
    WAV, FLAC, OGG/Vorbis, and (where the backend supports it) MP3.  The
    decoded samples are resampled to 16 kHz mono and packed back into int16
    PCM bytes suitable for both Scribe (``pcm_s16le_16``) and Deepgram's
    streaming Linear16 input.

    Args:
        path: Filesystem path to an audio file.

    Returns:
        Raw PCM bytes (16 kHz, mono, int16, little-endian).

    Raises:
        SttError: If the file cannot be read or decoded.
    """
    file_path = Path(path)
    try:
        data, sample_rate = sf.read(str(file_path), dtype="float32", always_2d=True)
    except FileNotFoundError as exc:
        handle_error(f"Audio file not found: {file_path}", ErrorType.FILE_NOT_FOUND, exception=exc)
    except Exception as exc:  # noqa: BLE001 -- surface any decoder failure uniformly
        handle_error(
            f"Could not decode audio file {file_path}: {exc}",
            ErrorType.INVALID_AUDIO,
            exception=exc,
        )

    # `always_2d=True` gives shape (frames, channels); downmix to mono.
    mono = _to_mono(data)
    resampled = _resample(mono, sample_rate, TARGET_SAMPLE_RATE)
    return (resampled * 32767.0).clip(-32768.0, 32767.0).astype(_INT16_DTYPE).tobytes()


def resample_pcm(
    samples: np.ndarray,
    in_rate: int,
    out_rate: int = TARGET_SAMPLE_RATE,
) -> np.ndarray:
    """Resample a 1-D float/buffer of *samples* to *out_rate* mono float32.

    Exposed primarily for tests and advanced callers; :func:`read_audio` uses
    this internally.  Uses linear interpolation -- sufficient for speech
    transcription and dependency-free.
    """
    return _resample(_to_mono(samples), in_rate, out_rate)


def iter_pcm_chunks(
    pcm_bytes: bytes,
    *,
    chunk_bytes: int = DEFAULT_CHUNK_BYTES,
) -> Iterator[bytes]:
    """Yield *pcm_bytes* in fixed-size slices for streaming to a provider.

    Args:
        pcm_bytes: Canonical PCM byte buffer (e.g. from :func:`read_audio`).
        chunk_bytes: Maximum bytes per yielded chunk. Defaults to 8 KiB.

    Yields:
        Successive byte slices of *pcm_bytes*. A final empty input yields
        nothing.
    """
    if chunk_bytes <= 0:
        raise ValueError("chunk_bytes must be positive")
    for start in range(0, len(pcm_bytes), chunk_bytes):
        yield pcm_bytes[start : start + chunk_bytes]


def materialise(audio: bytes | Iterator[bytes]) -> bytes:
    """Return *audio* as a flat ``bytes`` object.

    Accepts either a complete byte blob (returned as-is) or a sync iterator of
    byte chunks (concatenated).  Useful for batch providers like Scribe that
    require the whole file up front.
    """
    if isinstance(audio, (bytes, bytearray)):
        return bytes(audio)
    return b"".join(audio)


def _to_mono(samples: np.ndarray) -> np.ndarray:
    """Collapse a (frames, channels) or (frames,) array to 1-D mono float32."""
    arr = np.asarray(samples, dtype=np.float32)
    if arr.ndim == 1:
        return arr
    if arr.ndim == 2:
        return arr.mean(axis=1)
    raise ValueError(f"Unsupported sample array shape {arr.shape}; expected 1-D or 2-D")


def _resample(samples: np.ndarray, in_rate: int, out_rate: int) -> np.ndarray:
    """Linear-interpolation resample of 1-D float32 *samples* to *out_rate*."""
    if in_rate == out_rate:
        return np.ascontiguousarray(samples, dtype=np.float32)
    if in_rate <= 0:
        raise ValueError(f"Invalid source sample rate {in_rate}")
    if out_rate <= 0:
        raise ValueError(f"Invalid target sample rate {out_rate}")
    if samples.size == 0:
        return np.zeros(0, dtype=np.float32)
    n_out = int(round(len(samples) * out_rate / in_rate))
    if n_out < 1:
        return np.zeros(0, dtype=np.float32)
    idx = np.linspace(0.0, len(samples) - 1, num=n_out, dtype=np.float32)
    lower = np.floor(idx).astype(np.int64)
    upper = np.clip(lower + 1, 0, len(samples) - 1)
    frac = idx - lower
    return (samples[lower] * (1.0 - frac) + samples[upper] * frac).astype(np.float32, copy=False)
