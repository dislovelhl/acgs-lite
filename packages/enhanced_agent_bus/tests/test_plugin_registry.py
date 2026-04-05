from __future__ import annotations

import pytest

from enhanced_agent_bus.plugin_registry import PluginNotAvailable, available, require


def test_available_known_dependency() -> None:
    assert available("numpy") is True


def test_require_returns_module_path_for_known_dependency() -> None:
    assert require("numpy") == "numpy"


def test_require_raises_with_install_hint_for_missing_plugin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        __import__("enhanced_agent_bus.plugin_registry").plugin_registry.PLUGINS,
        "fake_plugin",
        "fake.module",
    )
    monkeypatch.setitem(
        __import__("enhanced_agent_bus.plugin_registry").plugin_registry.EXTRAS,
        "fake_plugin",
        "fake-extra",
    )

    with pytest.raises(PluginNotAvailable, match="pip install fake-extra"):
        require("fake_plugin")
