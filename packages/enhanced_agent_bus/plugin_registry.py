"""Central registry for optional module availability checks."""

from __future__ import annotations

from importlib.util import find_spec


class PluginNotAvailable(ImportError):
    """Raised when an optional plugin module is unavailable."""

    def __init__(self, name: str, module_path: str, install_hint: str | None = None) -> None:
        message = f"Plugin '{name}' is not available ({module_path})"
        if install_hint:
            message = f"{message}. Install with: pip install {install_hint}"
        super().__init__(message)
        self.name = name
        self.module_path = module_path
        self.install_hint = install_hint


PLUGINS: dict[str, str] = {
    "ab_testing": "enhanced_agent_bus.ab_testing",
    "anomaly_monitoring": "src.core.integrations.anomaly_monitoring",
    "dfc_metrics": "src.core.shared.governance.metrics.dfc",
    "drift_monitoring": "drift_monitoring",
    "feedback_handler": "enhanced_agent_bus.feedback_handler",
    "governance_mhc": "enhanced_agent_bus.governance.stability.mhc",
    "hotl_manager": "src.core.services.hitl_approvals.hotl_manager",
    "maci_enforcement": "enhanced_agent_bus.maci_enforcement",
    "maci_strategy": "enhanced_agent_bus.maci.strategy",
    "mlflow": "mlflow",
    "numpy": "numpy",
    "online_learning": "enhanced_agent_bus.online_learning",
    "opa_guard_mixin": "enhanced_agent_bus.deliberation_layer.opa_guard_mixin",
    "pandas": "pandas",
    "sklearn": "sklearn.ensemble",
    "z3": "z3",
}

EXTRAS: dict[str, str] = {
    "mlflow": "mlflow",
    "numpy": "numpy",
    "pandas": "pandas",
    "sklearn": "scikit-learn",
    "z3": "z3-solver",
}


def available(name: str) -> bool:
    """Return True when the configured module spec can be resolved."""

    module_path = PLUGINS[name]
    try:
        return find_spec(module_path) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def require(name: str) -> str:
    """Return the module path when available, otherwise raise PluginNotAvailable."""

    module_path = PLUGINS[name]
    if not available(name):
        raise PluginNotAvailable(name, module_path, EXTRAS.get(name))
    return module_path


__all__ = ["EXTRAS", "PLUGINS", "PluginNotAvailable", "available", "require"]
