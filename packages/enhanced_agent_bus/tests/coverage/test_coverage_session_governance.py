"""
ACGS-2 Enhanced Agent Bus - Session Governance Coverage Tests
Constitutional Hash: 608508a9bd224290

Covers: enhanced_agent_bus/session_governance.py (11 stmts, 0% -> target 100%)
Tests backward-compatibility exception shims.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestSessionGovernanceExceptions:
    def test_session_governance_error(self) -> None:
        from enhanced_agent_bus.session_governance import SessionGovernanceError

        err = SessionGovernanceError("test error")
        assert err.http_status_code == 500
        assert err.error_code == "SESSION_GOVERNANCE_ERROR"
        assert "test error" in str(err)

    def test_session_not_found_error(self) -> None:
        from enhanced_agent_bus.session_governance import SessionNotFoundError

        err = SessionNotFoundError("session xyz not found")
        assert err.http_status_code == 404
        assert err.error_code == "SESSION_NOT_FOUND"
        assert "session xyz not found" in str(err)

    def test_policy_resolution_error(self) -> None:
        from enhanced_agent_bus.session_governance import PolicyResolutionError

        err = PolicyResolutionError("policy failed")
        assert err.http_status_code == 500
        assert err.error_code == "POLICY_RESOLUTION_ERROR"
        assert "policy failed" in str(err)

    def test_inheritance_chain(self) -> None:
        from enhanced_agent_bus.session_governance import (
            PolicyResolutionError,
            SessionGovernanceError,
            SessionNotFoundError,
        )

        assert issubclass(SessionNotFoundError, SessionGovernanceError)
        assert issubclass(PolicyResolutionError, SessionGovernanceError)

    def test_exception_is_catchable(self) -> None:
        from enhanced_agent_bus.session_governance import (
            SessionGovernanceError,
            SessionNotFoundError,
        )

        with pytest.raises(SessionGovernanceError):
            raise SessionNotFoundError("not found")

    def test_all_exports(self) -> None:
        from enhanced_agent_bus import session_governance

        assert "SessionGovernanceError" in session_governance.__all__
        assert "SessionNotFoundError" in session_governance.__all__
        assert "PolicyResolutionError" in session_governance.__all__
