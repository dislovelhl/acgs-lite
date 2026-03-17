"""Independent MACI validators — separated from proposer modules."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

from .approvals import ApprovalRequirementsValidator
from .constitutional import ConstitutionalHashValidator
from .governance import GovernanceDecisionValidator


def _load_legacy_validators_module() -> ModuleType | None:
    legacy_path = Path(__file__).resolve().parent.parent / "validators.py"
    spec = importlib.util.spec_from_file_location(
        "packages.enhanced_agent_bus._legacy_validators", legacy_path
    )
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
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
    _legacy_constitutional_hash = "cdd01ef066bc6cf2"
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
