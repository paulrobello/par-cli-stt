"""Provider plugin registry and discovery."""

from __future__ import annotations

import inspect
from importlib import metadata
from typing import Any

from par_stt.providers.base import ProviderCapabilities, ProviderPlugin, SttProvider
from par_stt.providers.deepgram import DeepgramProvider
from par_stt.providers.elevenlabs import ElevenLabsProvider

ENTRY_POINT_GROUP = "par_stt.providers"

# Per-million-minute rates mirror :mod:`par_stt.costs` so the registry's
# metadata and the cost estimator agree.  Deepgram Nova-3 ~= $0.0043/min ->
# $4300 / 1M min; ElevenLabs Scribe is an approximation pending current pricing.
_builtin_plugins: tuple[ProviderPlugin, ...] = (
    ProviderPlugin(
        name="deepgram",
        provider_class=DeepgramProvider,
        description="Deepgram Nova-3 (streaming)",
        capabilities=ProviderCapabilities(
            formats=["wav", "mp3", "ogg", "webm", "flac"],
            supports_streaming=True,
            supports_language_detection=True,
            supports_diarization=True,
            supports_punctuation=True,
            supports_profanity_filter=True,
            supports_smart_format=True,
        ),
        default_model="nova-3",
        api_key_env_vars=("DEEPGRAM_API_KEY", "DG_API_KEY"),
        cost_per_million_minutes=4300.0,
    ),
    ProviderPlugin(
        name="elevenlabs",
        provider_class=ElevenLabsProvider,
        description="ElevenLabs Scribe (batch)",
        capabilities=ProviderCapabilities(
            formats=["mp3", "wav", "m4a", "ogg", "flac", "webm"],
            supports_streaming=False,
            supports_language_detection=True,
            supports_diarization=True,
        ),
        default_model="scribe_v1",
        api_key_env_vars=("ELEVENLABS_API_KEY",),
        cost_per_million_minutes=6500.0,
    ),
)

_plugins_cache: dict[str, ProviderPlugin] | None = None
_plugin_diagnostics: list[str] = []


def get_builtin_provider_plugins() -> dict[str, ProviderPlugin]:
    """Return built-in provider plugin descriptors keyed by name."""
    return {plugin.name: plugin for plugin in _builtin_plugins}


def get_provider_plugins(*, refresh: bool = False, include_entry_points: bool = True) -> dict[str, ProviderPlugin]:
    """Return discovered provider plugins keyed by provider name.

    Args:
        refresh: Rebuild the registry cache.
        include_entry_points: Include third-party entry-point plugins.

    Returns:
        Provider plugin descriptors keyed by name.
    """
    global _plugins_cache

    if refresh or _plugins_cache is None or not include_entry_points:
        plugins = get_builtin_provider_plugins()
        _plugin_diagnostics.clear()
        if include_entry_points:
            plugins.update(_load_entry_point_plugins())
        if include_entry_points:
            _plugins_cache = plugins
        return dict(plugins)

    return dict(_plugins_cache)


def get_provider_classes(*, refresh: bool = False) -> dict[str, type[SttProvider]]:
    """Return provider classes keyed by provider name."""
    return {name: plugin.provider_class for name, plugin in get_provider_plugins(refresh=refresh).items()}


def get_provider_plugin(name: str) -> ProviderPlugin:
    """Return one provider plugin descriptor by name.

    Raises:
        ValueError: If *name* is not a registered provider.
    """
    plugins = get_provider_plugins()
    if name not in plugins:
        raise ValueError(f"Unknown provider '{name}'. Available: {', '.join(sorted(plugins))}")
    return plugins[name]


def list_provider_plugins() -> list[str]:
    """Return sorted provider plugin names."""
    return sorted(get_provider_plugins())


def get_plugin_diagnostics() -> list[str]:
    """Return diagnostics collected during the latest plugin discovery."""
    return list(_plugin_diagnostics)


def _load_entry_point_plugins() -> dict[str, ProviderPlugin]:
    plugins: dict[str, ProviderPlugin] = {}
    try:
        entry_points = metadata.entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:
        entry_points = metadata.entry_points().select(group=ENTRY_POINT_GROUP)  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001 -- any discovery failure is non-fatal
        _plugin_diagnostics.append(f"Could not discover provider entry points: {exc}")
        return plugins

    for entry_point in entry_points:
        entry_point_name = getattr(entry_point, "name", "<unknown>")
        try:
            loaded = entry_point.load()
            plugin = _normalize_plugin(entry_point_name, loaded)
            plugins[plugin.name] = plugin
        except Exception as exc:  # noqa: BLE001 -- broken plugins must not block built-ins
            _plugin_diagnostics.append(f"Failed to load provider plugin '{entry_point_name}': {exc}")
    return plugins


def _normalize_plugin(entry_point_name: str, loaded: Any) -> ProviderPlugin:
    if isinstance(loaded, ProviderPlugin):
        return loaded

    if inspect.isclass(loaded) and issubclass(loaded, SttProvider):
        return _provider_class_to_plugin(entry_point_name, loaded)

    if callable(loaded):
        produced = loaded()
        if isinstance(produced, ProviderPlugin):
            return produced
        if inspect.isclass(produced) and issubclass(produced, SttProvider):
            return _provider_class_to_plugin(entry_point_name, produced)

    raise TypeError(
        "Provider entry point must load a ProviderPlugin, a ProviderPlugin factory, or an SttProvider subclass"
    )


def _provider_class_to_plugin(entry_point_name: str, provider_class: type[SttProvider]) -> ProviderPlugin:
    capabilities = _coerce_capabilities(getattr(provider_class, "plugin_capabilities", {}))
    plugin_name = getattr(provider_class, "plugin_name", entry_point_name)
    return ProviderPlugin(
        name=plugin_name,
        provider_class=provider_class,
        description=getattr(provider_class, "plugin_description", plugin_name),
        capabilities=capabilities,
        default_model=getattr(provider_class, "plugin_default_model", "default"),
        requires_api_key=bool(getattr(provider_class, "plugin_requires_api_key", True)),
        api_key_env_vars=tuple(getattr(provider_class, "plugin_api_key_env_vars", ())),
        source="entry-point",
        cost_per_million_minutes=getattr(provider_class, "plugin_cost_per_million_minutes", None),
    )


def _coerce_capabilities(value: ProviderCapabilities | dict[str, Any]) -> ProviderCapabilities:
    if isinstance(value, ProviderCapabilities):
        return value
    if isinstance(value, dict):
        return ProviderCapabilities(
            formats=list(value.get("formats", [])),
            supports_streaming=bool(value.get("supports_streaming", False)),
            supports_language_detection=bool(value.get("supports_language_detection", False)),
            supports_diarization=bool(value.get("supports_diarization", False)),
            supports_punctuation=bool(value.get("supports_punctuation", False)),
            supports_profanity_filter=bool(value.get("supports_profanity_filter", False)),
            supports_smart_format=bool(value.get("supports_smart_format", False)),
        )
    raise TypeError("plugin_capabilities must be ProviderCapabilities or dict")
