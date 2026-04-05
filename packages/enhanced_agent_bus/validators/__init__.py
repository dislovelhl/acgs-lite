"""Independent MACI validators — separated from proposer modules."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from .approvals import ApprovalRequirementsValidator
from .constitutional import ConstitutionalHashValidator
from .governance import GovernanceDecisionValidator

_MODULE = sys.modules[__name__]
sys.modules.setdefault("enhanced_agent_bus.validators", _MODULE)
sys.modules.setdefault("packages.enhanced_agent_bus.validators", _MODULE)


def _load_legacy_validators_module() -> ModuleType | None:
    legacy_path = Path(__file__).resolve().parent.parent / "validators.py"
    legacy_module_names = (
        "enhanced_agent_bus._legacy_validators",
        "packages.enhanced_agent_bus._legacy_validators",
    )

    for module_name in legacy_module_names:
        existing = sys.modules.get(module_name)
        if existing is not None:
            for alias in legacy_module_names:
                sys.modules.setdefault(alias, existing)
            return existing

    spec = importlib.util.spec_from_file_location(legacy_module_names[0], legacy_path)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    for alias in legacy_module_names[1:]:
        sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


_legacy_validators = _load_legacy_validators_module()

if _legacy_validators is not None:
    _legacy_constitutional_hash = _legacy_validators.CONSTITUTIONAL_HASH
    ValidationResult = _legacy_validators.ValidationResult
    validate_constitutional_hash = _legacy_validators.validate_constitutional_hash
    validate_message_content = _legacy_validators.validate_message_content
    validate_payload_integrity = _legacy_validators.validate_payload_integrity
else:
    _legacy_constitutional_hash = "608508a9bd224290"
    ValidationResult = Any

    def validate_constitutional_hash(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("Legacy validator module unavailable")

    def validate_message_content(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("Legacy validator module unavailable")

    def validate_payload_integrity(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("Legacy validator module unavailable")


CONSTITUTIONAL_HASH: str = _legacy_constitutional_hash


__all__ = [
    "CONSTITUTIONAL_HASH",
    "ApprovalRequirementsValidator",
    "ConstitutionalHashValidator",
    "GovernanceDecisionValidator",
    "ValidationResult",
    "validate_constitutional_hash",
    "validate_message_content",
    "validate_payload_integrity",
]
