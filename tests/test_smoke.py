"""Smoke tests for the par_stt package surface."""

import par_stt


def test_version_is_nonempty_string() -> None:
    """The package version must be exposed as a non-empty string."""
    assert isinstance(par_stt.__version__, str)
    assert par_stt.__version__


def test_all_exports_version() -> None:
    """``__version__`` must be part of the public ``__all__`` surface."""
    assert "__version__" in par_stt.__all__
