from __future__ import annotations

from src.core.shared.errors.exceptions import MACIEnforcementError


class RoleMatrixValidator:
    def validate(self, *, violations: list[str], strict_mode: bool) -> None:
        if not violations:
            return

        err = "; ".join(violations)
        if strict_mode:
            raise MACIEnforcementError(
                f"Invalid MACI role matrix: {err}",
                error_code="MACI_ROLE_MATRIX_INVALID",
                details={"violations": violations},
            )
