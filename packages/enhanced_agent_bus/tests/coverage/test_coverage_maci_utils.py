"""
ACGS-2 Enhanced Agent Bus - MACI Utils Coverage Tests
Constitutional Hash: 608508a9bd224290

Covers: enhanced_agent_bus/maci/utils.py (44 stmts, 0% -> target 80%+)
Tests validate_maci_role_matrix() and _ModelProxy lazy loading.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.governance, pytest.mark.constitutional, pytest.mark.maci]


class TestValidateMaciRoleMatrix:
    def test_default_matrix_valid(self) -> None:
        """The shipped MACI role matrix must pass validation (no violations)."""
        from enhanced_agent_bus.maci.utils import validate_maci_role_matrix

        violations = validate_maci_role_matrix()
        assert violations == []

    def test_conflicting_propose_and_validate(self) -> None:
        from enhanced_agent_bus.maci.models import MACIAction, MACIRole
        from enhanced_agent_bus.maci.utils import validate_maci_role_matrix

        # Create a matrix with a role that has both PROPOSE and VALIDATE
        bad_permissions = {
            MACIRole.EXECUTIVE: {MACIAction.PROPOSE, MACIAction.VALIDATE},
        }
        violations = validate_maci_role_matrix(role_permissions=bad_permissions)
        assert any("conflicting duties" in v for v in violations)
        assert any("propose and validate" in v for v in violations)

    def test_conflicting_synthesize_and_validate(self) -> None:
        from enhanced_agent_bus.maci.models import MACIAction, MACIRole
        from enhanced_agent_bus.maci.utils import validate_maci_role_matrix

        bad_permissions = {
            MACIRole.IMPLEMENTER: {MACIAction.SYNTHESIZE, MACIAction.VALIDATE},
        }
        violations = validate_maci_role_matrix(role_permissions=bad_permissions)
        assert any("synthesize and validate" in v for v in violations)

    def test_self_validation_detected(self) -> None:
        from enhanced_agent_bus.maci.models import MACIAction, MACIRole
        from enhanced_agent_bus.maci.utils import validate_maci_role_matrix

        permissions = {
            MACIRole.JUDICIAL: {MACIAction.VALIDATE, MACIAction.AUDIT},
        }
        # Constraint: JUDICIAL can validate itself
        bad_constraints = {
            MACIRole.JUDICIAL: {MACIRole.JUDICIAL},
        }
        violations = validate_maci_role_matrix(
            role_permissions=permissions,
            validation_constraints=bad_constraints,
        )
        assert any("validate itself" in v for v in violations)

    def test_constraint_without_validate_permission(self) -> None:
        from enhanced_agent_bus.maci.models import MACIAction, MACIRole
        from enhanced_agent_bus.maci.utils import validate_maci_role_matrix

        permissions = {
            MACIRole.EXECUTIVE: {MACIAction.PROPOSE},
        }
        # EXECUTIVE has validation constraints but no validate/audit permission
        constraints = {
            MACIRole.EXECUTIVE: {MACIRole.IMPLEMENTER},
        }
        violations = validate_maci_role_matrix(
            role_permissions=permissions,
            validation_constraints=constraints,
        )
        assert any("no validate/audit permission" in v for v in violations)


class TestModelProxy:
    def test_get_agent_message(self) -> None:
        from enhanced_agent_bus.maci.utils import _ModelProxy

        cls = _ModelProxy.get_agent_message()
        assert cls is not None

    def test_get_message_type(self) -> None:
        from enhanced_agent_bus.maci.utils import _ModelProxy

        cls = _ModelProxy.get_message_type()
        assert cls is not None

    def test_get_enum_value(self) -> None:
        from enhanced_agent_bus.maci.utils import _ModelProxy

        func = _ModelProxy.get_enum_value()
        # May be None or callable depending on environment
        assert func is None or callable(func)
