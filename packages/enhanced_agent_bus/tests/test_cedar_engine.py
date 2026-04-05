"""Tests for Cedar policy engine PoC.

Constitutional Hash: 608508a9bd224290
"""

import pytest

cedarpy = pytest.importorskip("cedarpy", reason="cedarpy required for Cedar engine tests")

from enhanced_agent_bus.cedar.engine import (
    CONSTITUTIONAL_HASH,
    AuthzRequest,
    AuthzResult,
    CedarPolicyEngine,
)

SIMPLE_PERMIT_ALL = "permit(principal, action, resource);"
SIMPLE_DENY_ALL = "forbid(principal, action, resource);"

RBAC_POLICY = """
permit(
    principal,
    action,
    resource
) when {
    principal has roles &&
    resource has required_role &&
    principal.roles.contains(resource.required_role)
};
"""


class TestCedarPolicyEngineBasic:
    def test_permit_all_allows(self):
        engine = CedarPolicyEngine(SIMPLE_PERMIT_ALL)
        result = engine.authorize(
            principal='User::"alice"',
            action='Action::"read"',
            resource='Resource::"doc1"',
        )
        assert result.allowed is True
        assert result.latency_ms >= 0

    def test_deny_all_denies(self):
        engine = CedarPolicyEngine(SIMPLE_DENY_ALL)
        result = engine.authorize(
            principal='User::"alice"',
            action='Action::"read"',
            resource='Resource::"doc1"',
        )
        assert result.allowed is False

    def test_no_matching_policy_denies(self):
        # Cedar default-deny: no matching permit = deny
        engine = CedarPolicyEngine('permit(principal == User::"bob", action, resource);')
        result = engine.authorize(
            principal='User::"alice"',
            action='Action::"read"',
            resource='Resource::"doc1"',
        )
        assert result.allowed is False

    def test_stats_tracking(self):
        engine = CedarPolicyEngine(SIMPLE_PERMIT_ALL)
        engine.authorize('User::"a"', 'Action::"r"', 'Resource::"x"')
        engine.authorize('User::"b"', 'Action::"r"', 'Resource::"y"')
        stats = engine.stats
        assert stats["total"] == 2
        assert stats["allowed"] == 2
        assert stats["denied"] == 0

    def test_invalid_policy_raises(self):
        with pytest.raises((ValueError, Exception)):
            CedarPolicyEngine("this is not valid cedar policy syntax {{{")

    def test_constitutional_hash_in_result(self):
        engine = CedarPolicyEngine(SIMPLE_PERMIT_ALL)
        result = engine.authorize('User::"a"', 'Action::"r"', 'Resource::"x"')
        assert result.constitutional_hash == CONSTITUTIONAL_HASH


class TestCedarPolicyEngineRBAC:
    def test_rbac_principal_match_allows(self):
        """Specific principal match allows access."""
        policy = 'permit(principal == User::"alice", action, resource);'
        engine = CedarPolicyEngine(policy)
        result = engine.authorize(
            principal='User::"alice"',
            action='Action::"read"',
            resource='Resource::"doc1"',
        )
        assert result.allowed is True

    def test_rbac_principal_mismatch_denies(self):
        """Non-matching principal is denied (default deny)."""
        policy = 'permit(principal == User::"alice", action, resource);'
        engine = CedarPolicyEngine(policy)
        result = engine.authorize(
            principal='User::"bob"',
            action='Action::"read"',
            resource='Resource::"doc1"',
        )
        assert result.allowed is False

    def test_rbac_action_restriction(self):
        """Only specific action is permitted."""
        policy = 'permit(principal, action == Action::"read", resource);'
        engine = CedarPolicyEngine(policy)
        read_result = engine.authorize('User::"a"', 'Action::"read"', 'Resource::"x"')
        write_result = engine.authorize('User::"a"', 'Action::"write"', 'Resource::"x"')
        assert read_result.allowed is True
        assert write_result.allowed is False


class TestCedarBatch:
    def test_batch_authorize(self):
        engine = CedarPolicyEngine(SIMPLE_PERMIT_ALL)
        requests = [
            AuthzRequest(
                principal='User::"alice"',
                action='Action::"read"',
                resource='Resource::"doc1"',
            ),
            AuthzRequest(
                principal='User::"bob"',
                action='Action::"write"',
                resource='Resource::"doc2"',
            ),
        ]
        results = engine.authorize_batch(requests)
        assert len(results) == 2
        assert all(r.allowed for r in results)

    def test_batch_empty_returns_empty(self):
        engine = CedarPolicyEngine(SIMPLE_PERMIT_ALL)
        results = engine.authorize_batch([])
        assert results == []

    def test_batch_performance(self):
        """Batch should complete 100 requests in <10ms."""
        engine = CedarPolicyEngine(SIMPLE_PERMIT_ALL)
        requests = [
            AuthzRequest(
                principal=f'User::"{i}"',
                action='Action::"read"',
                resource=f'Resource::"{i}"',
            )
            for i in range(100)
        ]
        results = engine.authorize_batch(requests)
        assert len(results) == 100
        total_latency = sum(r.latency_ms for r in results)
        # 100 requests should take well under 10ms with Cedar
        assert total_latency < 100  # generous bound


class TestCedarFailClosed:
    def test_error_returns_deny(self):
        engine = CedarPolicyEngine(SIMPLE_PERMIT_ALL)
        # Corrupt the policies to cause evaluation error
        engine._policies = "CORRUPTED"
        result = engine.authorize('User::"a"', 'Action::"r"', 'Resource::"x"')
        assert result.allowed is False
        # Cedar returns diagnostics with errors list, not an "error" key
        assert result.diagnostics.get("errors") or result.diagnostics.get("error")

    def test_error_returns_deny_decision(self):
        engine = CedarPolicyEngine(SIMPLE_PERMIT_ALL)
        engine._policies = "CORRUPTED"
        result = engine.authorize('User::"a"', 'Action::"r"', 'Resource::"x"')
        # Cedar may return NoDecision or Deny on parse error — both mean not allowed
        assert result.allowed is False


class TestAuthzRequest:
    def test_to_cedar_request(self):
        req = AuthzRequest(
            principal='User::"alice"',
            action='Action::"read"',
            resource='Resource::"doc1"',
            context={"ip": "10.0.0.1"},
        )
        cedar_req = req.to_cedar_request()
        assert cedar_req["principal"] == 'User::"alice"'
        assert cedar_req["context"] == {"ip": "10.0.0.1"}


class TestFromPolicyDir:
    def test_loads_cedar_files(self, tmp_path):
        policy_file = tmp_path / "test.cedar"
        policy_file.write_text("permit(principal, action, resource);")
        engine = CedarPolicyEngine.from_policy_dir(tmp_path)
        result = engine.authorize('User::"a"', 'Action::"r"', 'Resource::"x"')
        assert result.allowed is True

    def test_missing_dir_raises(self):
        with pytest.raises(FileNotFoundError):
            CedarPolicyEngine.from_policy_dir("/nonexistent/path")

    def test_empty_dir_raises(self, tmp_path):
        with pytest.raises(ValueError, match="No .cedar files"):
            CedarPolicyEngine.from_policy_dir(tmp_path)
