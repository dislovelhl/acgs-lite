from __future__ import annotations

from typing import Any


class ApprovalRequirementsValidator:
    def validate_approvals(
        self,
        *,
        policy: Any,
        decisions: list[Any],
        approvers: dict[str, Any],
        requester_id: str,
    ) -> tuple[bool, str]:
        approved_decisions = [d for d in decisions if d.decision.value == "approved"]

        if len(approved_decisions) < policy.min_approvers:
            return False, f"Need {policy.min_approvers} approvers, got {len(approved_decisions)}"

        if not policy.allow_self_approval:
            for decision in approved_decisions:
                if decision.approver_id == requester_id:
                    return False, "Self-approval not allowed"

        if not policy.required_roles:
            return True, "All requirements met"

        approved_roles = set()
        for decision in approved_decisions:
            approver = approvers.get(decision.approver_id)
            if approver:
                approved_roles.update(approver.roles)

        if policy.require_all_roles:
            missing_roles = set(policy.required_roles) - approved_roles
            if missing_roles:
                return False, f"Missing approvals from roles: {[r.value for r in missing_roles]}"
            return True, "All requirements met"

        if any(role in approved_roles for role in policy.required_roles):
            return True, "All requirements met"

        return False, f"No approver with required role: {[r.value for r in policy.required_roles]}"
