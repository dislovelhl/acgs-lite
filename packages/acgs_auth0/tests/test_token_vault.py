"""Unit tests for ConstitutionalTokenVault.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from acgs_auth0.audit import TokenAccessOutcome, TokenAuditLog
from acgs_auth0.exceptions import (
    ConstitutionalScopeViolation,
    MACIRoleNotPermittedError,
    StepUpAuthRequiredError,
)
from acgs_auth0.scope_policy import ConnectionScopeRule, MACIScopePolicy
from acgs_auth0.token_vault import (
    ConstitutionalTokenVault,
    TokenVaultRequest,
    TokenVaultResponse,
    get_token_vault_credentials,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def policy() -> MACIScopePolicy:
    return MACIScopePolicy(
        rules=[
            ConnectionScopeRule(
                connection="github",
                role="EXECUTIVE",
                permitted_scopes=["read:user", "repo:read"],
                high_risk_scopes=[],
            ),
            ConnectionScopeRule(
                connection="github",
                role="IMPLEMENTER",
                permitted_scopes=["read:user", "repo:read", "repo:write"],
                high_risk_scopes=["repo:write"],
            ),
        ]
    )


@pytest.fixture()
def audit_log() -> TokenAuditLog:
    return TokenAuditLog()


@pytest.fixture()
def vault(policy: MACIScopePolicy, audit_log: TokenAuditLog) -> ConstitutionalTokenVault:
    return ConstitutionalTokenVault(
        policy=policy,
        audit_log=audit_log,
        auth0_domain="test.auth0.com",
        auth0_client_id="client123",
        auth0_client_secret="secret456",
    )


def _make_request(
    role: str = "EXECUTIVE",
    scopes: list[str] | None = None,
    connection: str = "github",
) -> TokenVaultRequest:
    return TokenVaultRequest(
        agent_id="planner",
        role=role,
        connection=connection,
        scopes=scopes or ["repo:read"],
        refresh_token="rt_test",
        user_id="auth0|test",
    )


# ---------------------------------------------------------------------------
# validate() — pre-flight checks
# ---------------------------------------------------------------------------


class TestConstitutionalTokenVaultValidate:
    def test_permitted_request_passes(
        self, vault: ConstitutionalTokenVault
    ) -> None:
        result = vault.validate(_make_request(role="EXECUTIVE", scopes=["repo:read"]))
        assert result.permitted is True

    def test_denied_scope_fails(self, vault: ConstitutionalTokenVault) -> None:
        result = vault.validate(_make_request(role="EXECUTIVE", scopes=["repo:write"]))
        assert result.permitted is False
        assert isinstance(result.error, ConstitutionalScopeViolation)

    def test_unknown_role_fails(self, vault: ConstitutionalTokenVault) -> None:
        result = vault.validate(_make_request(role="JUDICIAL", scopes=["read:user"]))
        assert result.permitted is False
        assert isinstance(result.error, MACIRoleNotPermittedError)


# ---------------------------------------------------------------------------
# exchange() — full async exchange
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestConstitutionalTokenVaultExchange:
    async def test_permitted_exchange_calls_token_vault(
        self, vault: ConstitutionalTokenVault, audit_log: TokenAuditLog
    ) -> None:
        mock_response = {
            "access_token": "gha_test_token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "repo:read",
            "issued_token_type": "http://auth0.com/oauth/token-type/federated-connection-access-token",
        }

        with patch.object(vault, "_call_token_vault", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = TokenVaultResponse(
                access_token=mock_response["access_token"],
                token_type=mock_response["token_type"],
                expires_in=mock_response["expires_in"],
                scope=mock_response["scope"],
                issued_token_type=mock_response["issued_token_type"],
            )
            response = await vault.exchange(
                _make_request(role="EXECUTIVE", scopes=["repo:read"])
            )

        assert response.access_token == "gha_test_token"
        mock_call.assert_called_once()
        granted = audit_log.get_entries(outcome=TokenAccessOutcome.GRANTED)
        assert len(granted) == 1
        assert granted[0].agent_id == "planner"

    async def test_denied_scope_raises_and_audits(
        self, vault: ConstitutionalTokenVault, audit_log: TokenAuditLog
    ) -> None:
        with pytest.raises(ConstitutionalScopeViolation):
            await vault.exchange(
                _make_request(role="EXECUTIVE", scopes=["repo:write"])
            )
        denied = audit_log.get_entries(outcome=TokenAccessOutcome.DENIED_SCOPE_VIOLATION)
        assert len(denied) == 1

    async def test_role_not_permitted_raises_and_audits(
        self, vault: ConstitutionalTokenVault, audit_log: TokenAuditLog
    ) -> None:
        with pytest.raises(MACIRoleNotPermittedError):
            await vault.exchange(
                _make_request(role="JUDICIAL", scopes=["read:user"])
            )
        denied = audit_log.get_entries(
            outcome=TokenAccessOutcome.DENIED_ROLE_NOT_PERMITTED
        )
        assert len(denied) == 1

    async def test_high_risk_scope_triggers_step_up(
        self, vault: ConstitutionalTokenVault, audit_log: TokenAuditLog
    ) -> None:
        with pytest.raises(StepUpAuthRequiredError) as exc_info:
            await vault.exchange(
                _make_request(role="IMPLEMENTER", scopes=["repo:read", "repo:write"])
            )
        err = exc_info.value
        assert "repo:write" in err.high_risk_scopes
        assert err.connection == "github"
        # Step-up should be audited
        step_up = audit_log.get_entries(outcome=TokenAccessOutcome.STEP_UP_INITIATED)
        assert len(step_up) == 1


# ---------------------------------------------------------------------------
# get_token_vault_credentials()
# ---------------------------------------------------------------------------


class TestGetTokenVaultCredentials:
    def test_raises_outside_context(self) -> None:
        with pytest.raises(RuntimeError, match="governed tool context"):
            get_token_vault_credentials()

    def test_returns_credentials_inside_context(self) -> None:
        from acgs_auth0.token_vault import _token_vault_credentials_ctx

        token = _token_vault_credentials_ctx.set(
            {"access_token": "abc", "token_type": "Bearer"}
        )
        try:
            creds = get_token_vault_credentials()
            assert creds["access_token"] == "abc"
        finally:
            _token_vault_credentials_ctx.reset(token)
