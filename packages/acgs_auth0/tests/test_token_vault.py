"""Unit tests for ConstitutionalTokenVault.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

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
# Auth0 configuration validation
# ---------------------------------------------------------------------------


class TestAuth0ConfigValidation:
    @pytest.mark.asyncio
    async def test_exchange_raises_when_domain_not_configured(self) -> None:
        """exchange() must raise RuntimeError early when domain is empty."""
        empty_vault = ConstitutionalTokenVault(
            policy=MACIScopePolicy(
                rules=[
                    ConnectionScopeRule(
                        connection="github",
                        role="EXECUTIVE",
                        permitted_scopes=["repo:read"],
                    )
                ]
            ),
            auth0_domain="",
            auth0_client_id="",
        )
        with pytest.raises(RuntimeError, match="AUTH0_DOMAIN|domain and client_id"):
            await empty_vault.exchange(
                TokenVaultRequest(
                    agent_id="planner",
                    role="EXECUTIVE",
                    connection="github",
                    scopes=["repo:read"],
                    refresh_token="rt_test",
                )
            )


# ---------------------------------------------------------------------------
# YAML edge cases
# ---------------------------------------------------------------------------


class TestYAMLEdgeCases:
    def test_yaml_without_token_vault_key_falls_back_to_root(self, tmp_path) -> None:
        """YAML without 'token_vault' key uses root dict (fallback behaviour)."""
        yaml_content = """
connections:
  github:
    EXECUTIVE:
      permitted_scopes: ["repo:read"]
      high_risk_scopes: []
"""
        yaml_file = tmp_path / "flat.yaml"
        yaml_file.write_text(yaml_content)
        policy = MACIScopePolicy.from_yaml(yaml_file)
        rule = policy.get_rule(connection="github", role="EXECUTIVE")
        assert rule is not None
        assert "repo:read" in rule.permitted_scopes

    def test_yaml_with_empty_connections_loads_empty_policy(self, tmp_path) -> None:
        """A YAML with no connections loads without error."""
        yaml_content = """
token_vault:
  constitutional_hash: "608508a9bd224290"
  connections: {}
"""
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text(yaml_content)
        policy = MACIScopePolicy.from_yaml(yaml_file)
        assert policy.constitutional_hash == "608508a9bd224290"
        assert policy.get_rule(connection="github", role="EXECUTIVE") is None


# ---------------------------------------------------------------------------
# ConstitutionalAuth0AI (after bug fix)
# ---------------------------------------------------------------------------


class TestConstitutionalAuth0AI:
    def test_with_token_vault_returns_callable(self) -> None:
        """with_token_vault() must return a decorator, not raise."""
        from acgs_auth0.governed_tool import ConstitutionalAuth0AI

        auth0_ai = ConstitutionalAuth0AI(
            policy=MACIScopePolicy(
                rules=[
                    ConnectionScopeRule(
                        connection="github",
                        role="EXECUTIVE",
                        permitted_scopes=["repo:read"],
                    )
                ]
            ),
            auth0_domain="test.auth0.com",
            auth0_client_id="client123",
            auth0_client_secret="secret456",
        )
        decorator = auth0_ai.with_token_vault(connection="github", scopes=["repo:read"])
        assert callable(decorator)

    @pytest.mark.asyncio
    async def test_with_token_vault_denies_unauthorized_scope(self) -> None:
        """ConstitutionalAuth0AI.with_token_vault must enforce MACI policy."""
        from acgs_auth0.exceptions import ConstitutionalScopeViolation
        from acgs_auth0.governed_tool import ConstitutionalAuth0AI

        policy = MACIScopePolicy(
            rules=[
                ConnectionScopeRule(
                    connection="github",
                    role="EXECUTIVE",
                    permitted_scopes=["repo:read"],
                    high_risk_scopes=[],
                )
            ]
        )
        auth0_ai = ConstitutionalAuth0AI(policy=policy)

        def get_agent_context() -> tuple[str, str]:
            return ("planner", "EXECUTIVE")

        def get_refresh_token() -> str:
            return "rt_test"

        with_write = auth0_ai.with_token_vault(
            connection="github",
            scopes=["repo:write"],  # EXECUTIVE not permitted
            get_agent_context=get_agent_context,
            get_refresh_token=get_refresh_token,
        )

        async def dummy_tool(query: str) -> str:
            return "should not reach here"

        governed = with_write(dummy_tool)
        with pytest.raises(ConstitutionalScopeViolation):
            await governed(query="test")


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
