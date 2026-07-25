"""Static transcription cost estimation helpers."""

from __future__ import annotations

from dataclasses import dataclass

from par_stt.defaults import DEFAULT_MODELS

# Approximate per-million-minute rates for quick estimates. Cloud provider
# billing changes over time, so treat these as planning numbers only.
# Deepgram Nova-3 streaming is ~$0.0043/min (= $4300 per million minutes).
# ElevenLabs Scribe is billed per minute of audio; the figure below is an
# approximation that should be verified against current ElevenLabs pricing.
COST_PER_MILLION_MINUTES: dict[str, dict[str, float]] = {
    "deepgram": {"default": 4300.0, "nova-3": 4300.0},
    "elevenlabs": {"default": 6500.0, "scribe_v1": 6500.0},
}


@dataclass(frozen=True)
class CostEstimate:
    """Static, approximate transcription cost estimate."""

    provider: str
    model: str
    audio_seconds: float
    cost_usd: float | None
    rate_per_minute: float | None


def estimate_transcription_cost(provider: str, model: str | None, audio_seconds: float) -> CostEstimate:
    """Estimate transcription cost from static provider/model pricing.

    Args:
        provider: Provider identifier (e.g. ``"deepgram"``, ``"elevenlabs"``).
        model: Provider model name, or None to use the provider default.
        audio_seconds: Duration of input audio in seconds.

    Returns:
        A :class:`CostEstimate` carrying the audio length and per-minute rate.
    """
    resolved_model = model or DEFAULT_MODELS.get(provider, "default")
    provider_rates = COST_PER_MILLION_MINUTES.get(provider, {})
    rate_per_million = provider_rates.get(resolved_model, provider_rates.get("default"))
    rate_per_minute = None if rate_per_million is None else rate_per_million / 1_000_000
    cost = None if rate_per_minute is None else rate_per_minute * (audio_seconds / 60.0)
    return CostEstimate(
        provider=provider,
        model=resolved_model,
        audio_seconds=audio_seconds,
        cost_usd=cost,
        rate_per_minute=rate_per_minute,
    )
