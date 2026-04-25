"""Tests for acgs_lite.engine.rust optional extension fallback."""

from __future__ import annotations

import builtins
import importlib
import sys


def test_rust_fallback_constants() -> None:
    from acgs_lite.engine.rust import _HAS_RUST, _RUST_ALLOW, _RUST_DENY, _RUST_DENY_CRITICAL

    # In CI without the Rust extension, these should be fallback values
    if not _HAS_RUST:
        assert _RUST_ALLOW == 0
        assert _RUST_DENY_CRITICAL == 1
        assert _RUST_DENY == 2
    else:
        # With Rust extension, constants come from the native module
        assert isinstance(_RUST_ALLOW, int)
        assert isinstance(_RUST_DENY_CRITICAL, int)
        assert isinstance(_RUST_DENY, int)


def test_has_aho_flag() -> None:
    from acgs_lite.engine.rust import _HAS_AHO

    assert isinstance(_HAS_AHO, bool)


def test_rust_module_importable() -> None:
    import acgs_lite.engine.rust as mod

    assert hasattr(mod, "_HAS_RUST")
    assert hasattr(mod, "_HAS_AHO")
    assert hasattr(mod, "_RUST_ALLOW")


def test_rust_fallback_import_when_extension_absent(monkeypatch) -> None:
    import acgs_lite.engine.rust as rust_mod

    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "acgs_lite_rust":
            raise ImportError("blocked for fallback contract test")
        return real_import(name, *args, **kwargs)

    with monkeypatch.context() as mp:
        mp.delitem(sys.modules, "acgs_lite_rust", raising=False)
        mp.setattr(builtins, "__import__", blocked_import)
        reloaded = importlib.reload(rust_mod)
        assert reloaded._HAS_RUST is False
        assert reloaded._RUST_ALLOW == 0
        assert reloaded._RUST_DENY_CRITICAL == 1
        assert reloaded._RUST_DENY == 2

    importlib.reload(rust_mod)


def test_rust_extension_supported_exports_when_installed() -> None:
    from acgs_lite.engine.rust import _HAS_RUST

    if not _HAS_RUST:
        return

    import acgs_lite_rust

    assert hasattr(acgs_lite_rust, "GovernanceValidator")
    assert acgs_lite_rust.ALLOW == 0
    assert acgs_lite_rust.DENY_CRITICAL == 1
    assert acgs_lite_rust.DENY == 2
    assert not hasattr(acgs_lite_rust, "ImpactScorer")
