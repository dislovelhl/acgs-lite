"""MACI role-matrix invariant tests.

Constitutional Hash: 608508a9bd224290
"""

import pytest

from enhanced_agent_bus.maci_enforcement import (
    MACIAction,
    MACIRole,
    validate_maci_role_matrix,
)


@pytest.mark.constitutional
def test_default_maci_role_matrix_has_no_conflicts() -> None:
    violations = validate_maci_role_matrix()
    assert violations == []


@pytest.mark.constitutional
def test_matrix_detects_propose_validate_conflict() -> None:
    custom_permissions = {
        MACIRole.EXECUTIVE: {MACIAction.PROPOSE, MACIAction.VALIDATE},
        MACIRole.JUDICIAL: {MACIAction.VALIDATE},
    }

    violations = validate_maci_role_matrix(role_permissions=custom_permissions)

    assert any("propose and validate" in message for message in violations)


@pytest.mark.constitutional
def test_matrix_detects_self_validation_constraint() -> None:
    custom_permissions = {
        MACIRole.JUDICIAL: {MACIAction.VALIDATE},
    }
    custom_constraints = {
        MACIRole.JUDICIAL: {MACIRole.JUDICIAL},
    }

    violations = validate_maci_role_matrix(
        role_permissions=custom_permissions,
        validation_constraints=custom_constraints,
    )

    assert any("can validate itself" in message for message in violations)
