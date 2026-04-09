"""Tests for acgs_lite.engine.rust optional extension fallback."""

from __future__ import annotations


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
