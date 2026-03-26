"""
Comprehensive tests for batch D coverage targets:
- src.core.shared.security.oauth_state_manager
- src.core.shared.policy.unified_generator
- src.core.shared.auth.provisioning
- src.core.shared.database.utils

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# OAuth2 State Manager Tests
# ---------------------------------------------------------------------------
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.errors.exceptions import ValidationError as ACGSValidationError
from src.core.shared.security.oauth_state_manager import (
    OAuth2StateError,
    OAuth2StateExpiredError,
    OAuth2StateManager,
    OAuth2StateNotFoundError,
    OAuth2StateValidationError,
    _allow_degraded_mode_without_redis,
    _parse_bool_env,
)


class TestParseBoolEnv:
    def test_true_values(self):
        for val in ("true", "True", "TRUE", "1", "yes", "on", " true ", " YES "):
            assert _parse_bool_env(val) is True

    def test_false_values(self):
        for val in ("false", "0", "no", "off", "", "random"):
            assert _parse_bool_env(val) is False

    def test_none(self):
        assert _parse_bool_env(None) is False


class TestAllowDegradedMode:
    @patch.dict(os.environ, {"OAUTH_STATE_ALLOW_DEGRADED_MODE": "true"})
    def test_env_override_true(self):
        assert _allow_degraded_mode_without_redis() is True

    @patch.dict(os.environ, {"OAUTH_STATE_ALLOW_DEGRADED_MODE": ""}, clear=False)
    @patch("src.core.shared.security.oauth_state_manager.settings")
    def test_non_production_env(self, mock_settings):
        mock_settings.env = "test"
        assert _allow_degraded_mode_without_redis() is True

    @patch.dict(os.environ, {"OAUTH_STATE_ALLOW_DEGRADED_MODE": ""}, clear=False)
    @patch("src.core.shared.security.oauth_state_manager.settings")
    def test_production_env(self, mock_settings):
        mock_settings.env = "production"
        assert _allow_degraded_mode_without_redis() is False


class TestOAuth2StateExceptions:
    def test_base_error_attributes(self):
        err = OAuth2StateError("test")
        assert err.http_status_code == 400
        assert err.error_code == "OAUTH2_STATE_ERROR"

    def test_not_found_inherits(self):
        err = OAuth2StateNotFoundError("gone")
        assert isinstance(err, OAuth2StateError)

    def test_expired_inherits(self):
        err = OAuth2StateExpiredError("old")
        assert isinstance(err, OAuth2StateError)

    def test_validation_inherits(self):
        err = OAuth2StateValidationError("bad")
        assert isinstance(err, OAuth2StateError)


class TestOAuth2StateManagerInit:
    def test_init_with_redis(self):
        redis = MagicMock()
        mgr = OAuth2StateManager(redis_client=redis)
        assert mgr._use_redis is True
        assert mgr._redis_client is redis

    @patch(
        "src.core.shared.security.oauth_state_manager._allow_degraded_mode_without_redis",
        return_value=True,
    )
    def test_init_without_redis_degraded_allowed(self, _mock):
        mgr = OAuth2StateManager(redis_client=None)
        assert mgr._use_redis is False

    @patch(
        "src.core.shared.security.oauth_state_manager._allow_degraded_mode_without_redis",
        return_value=False,
    )
    @patch("src.core.shared.security.oauth_state_manager.settings")
    def test_init_without_redis_production_raises(self, mock_settings, _mock):
        mock_settings.env = "production"
        with pytest.raises(OSError, match="Redis is required"):
            OAuth2StateManager(redis_client=None)

    def test_state_ttl_constant(self):
        assert OAuth2StateManager.STATE_TTL_SECONDS == 300

    def test_min_entropy_bytes_constant(self):
        assert OAuth2StateManager.MIN_ENTROPY_BYTES == 32


class TestOAuth2StateManagerCreateState:
    @pytest.fixture()
    def redis_mock(self):
        mock = AsyncMock()
        mock.set = AsyncMock()
        return mock

    @pytest.fixture()
    def manager(self, redis_mock):
        return OAuth2StateManager(redis_client=redis_mock)

    async def test_create_state_success(self, manager, redis_mock):
        state = await manager.create_state(
            client_ip="10.0.0.1",
            user_agent="Mozilla/5.0",
            provider="okta",
            callback_url="/callback",
        )
        assert isinstance(state, str)
        assert len(state) > 20  # 256-bit base64 is ~43 chars
        redis_mock.set.assert_awaited_once()
        call_args = redis_mock.set.call_args
        assert call_args[0][0] == f"oauth:state:{state}"
        stored_data = json.loads(call_args[0][1])
        assert stored_data["provider"] == "okta"
        assert stored_data["client_ip"] == "10.0.0.1"
        assert stored_data["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert call_args[1]["ex"] == 300

    async def test_create_state_empty_client_ip(self, manager):
        with pytest.raises(ACGSValidationError, match="client_ip cannot be empty"):
            await manager.create_state(
                client_ip="", user_agent="ua", provider="okta", callback_url="/cb"
            )

    async def test_create_state_whitespace_client_ip(self, manager):
        with pytest.raises(ACGSValidationError, match="client_ip cannot be empty"):
            await manager.create_state(
                client_ip="   ", user_agent="ua", provider="okta", callback_url="/cb"
            )

    async def test_create_state_empty_user_agent(self, manager):
        with pytest.raises(ACGSValidationError, match="user_agent cannot be empty"):
            await manager.create_state(
                client_ip="1.2.3.4", user_agent="", provider="okta", callback_url="/cb"
            )

    async def test_create_state_empty_provider(self, manager):
        with pytest.raises(ACGSValidationError, match="provider cannot be empty"):
            await manager.create_state(
                client_ip="1.2.3.4", user_agent="ua", provider="", callback_url="/cb"
            )

    async def test_create_state_empty_callback_url(self, manager):
        with pytest.raises(ACGSValidationError, match="callback_url cannot be empty"):
            await manager.create_state(
                client_ip="1.2.3.4", user_agent="ua", provider="okta", callback_url=""
            )

    async def test_create_state_none_inputs(self, manager):
        with pytest.raises(ACGSValidationError):
            await manager.create_state(
                client_ip=None, user_agent="ua", provider="okta", callback_url="/cb"
            )

    async def test_create_state_redis_error(self, manager, redis_mock):
        redis_mock.set.side_effect = ConnectionError("connection refused")
        with pytest.raises(ConnectionError, match="Redis unavailable"):
            await manager.create_state(
                client_ip="1.2.3.4", user_agent="ua", provider="okta", callback_url="/cb"
            )

    async def test_create_state_redis_os_error(self, manager, redis_mock):
        redis_mock.set.side_effect = OSError("disk error")
        with pytest.raises(ConnectionError, match="Redis unavailable"):
            await manager.create_state(
                client_ip="1.2.3.4", user_agent="ua", provider="okta", callback_url="/cb"
            )

    @patch(
        "src.core.shared.security.oauth_state_manager._allow_degraded_mode_without_redis",
        return_value=True,
    )
    async def test_create_state_degraded_mode(self, _mock):
        mgr = OAuth2StateManager(redis_client=None)
        state = await mgr.create_state(
            client_ip="1.2.3.4", user_agent="ua", provider="okta", callback_url="/cb"
        )
        assert isinstance(state, str)
        assert len(state) > 20


class TestOAuth2StateManagerValidateState:
    @pytest.fixture()
    def redis_mock(self):
        mock = AsyncMock()
        mock.get = AsyncMock()
        mock.delete = AsyncMock(return_value=1)
        return mock

    @pytest.fixture()
    def manager(self, redis_mock):
        return OAuth2StateManager(redis_client=redis_mock)

    def _make_state_json(self, **overrides):
        data = {
            "provider": "okta",
            "callback_url": "/callback",
            "client_ip": "10.0.0.1",
            "user_agent": "Mozilla/5.0",
            "created_at": datetime.now(UTC).isoformat(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
        data.update(overrides)
        return json.dumps(data)

    async def test_validate_success(self, manager, redis_mock):
        redis_mock.get.return_value = self._make_state_json()
        result = await manager.validate_state(
            state="test_state_abc", client_ip="10.0.0.1", user_agent="Mozilla/5.0"
        )
        assert result["provider"] == "okta"
        redis_mock.delete.assert_awaited_once()

    async def test_validate_bytes_response(self, manager, redis_mock):
        redis_mock.get.return_value = self._make_state_json().encode("utf-8")
        result = await manager.validate_state(
            state="test_state_abc", client_ip="10.0.0.1", user_agent="Mozilla/5.0"
        )
        assert result["provider"] == "okta"

    async def test_validate_empty_state_raises(self, manager):
        with pytest.raises(ACGSValidationError, match="state cannot be empty"):
            await manager.validate_state(state="", client_ip="10.0.0.1", user_agent="ua")

    async def test_validate_whitespace_state_raises(self, manager):
        with pytest.raises(ACGSValidationError, match="state cannot be empty"):
            await manager.validate_state(state="   ", client_ip="10.0.0.1", user_agent="ua")

    @patch(
        "src.core.shared.security.oauth_state_manager._allow_degraded_mode_without_redis",
        return_value=True,
    )
    async def test_validate_no_redis_raises_not_found(self, _mock):
        mgr = OAuth2StateManager(redis_client=None)
        with pytest.raises(OAuth2StateNotFoundError, match="Redis unavailable"):
            await mgr.validate_state(state="abc", client_ip="1.2.3.4", user_agent="ua")

    async def test_validate_state_not_found_in_redis(self, manager, redis_mock):
        redis_mock.get.return_value = None
        with pytest.raises(OAuth2StateNotFoundError, match="not found or expired"):
            await manager.validate_state(state="missing", client_ip="1.2.3.4", user_agent="ua")

    async def test_validate_redis_connection_error(self, manager, redis_mock):
        redis_mock.get.side_effect = ConnectionError("refused")
        with pytest.raises(ConnectionError, match="Redis unavailable"):
            await manager.validate_state(state="abc", client_ip="1.2.3.4", user_agent="ua")

    async def test_validate_redis_os_error(self, manager, redis_mock):
        redis_mock.get.side_effect = OSError("disk")
        with pytest.raises(ConnectionError, match="Redis unavailable"):
            await manager.validate_state(state="abc", client_ip="1.2.3.4", user_agent="ua")

    async def test_validate_invalid_json(self, manager, redis_mock):
        redis_mock.get.return_value = "not-json{{"
        with pytest.raises(OAuth2StateValidationError, match="Invalid state data"):
            await manager.validate_state(state="abc", client_ip="1.2.3.4", user_agent="ua")

    async def test_validate_missing_constitutional_hash(self, manager, redis_mock):
        data = {
            "provider": "okta",
            "callback_url": "/cb",
            "client_ip": "1.2.3.4",
            "user_agent": "ua",
            "created_at": datetime.now(UTC).isoformat(),
        }
        redis_mock.get.return_value = json.dumps(data)
        with pytest.raises(OAuth2StateValidationError, match="Constitutional hash missing"):
            await manager.validate_state(state="abc", client_ip="1.2.3.4", user_agent="ua")

    async def test_validate_wrong_constitutional_hash(self, manager, redis_mock):
        redis_mock.get.return_value = self._make_state_json(constitutional_hash="wrong_hash")
        with pytest.raises(OAuth2StateValidationError, match="Constitutional hash mismatch"):
            await manager.validate_state(state="abc", client_ip="1.2.3.4", user_agent="ua")

    async def test_validate_expired_state(self, manager, redis_mock):
        old_time = (datetime.now(UTC) - timedelta(seconds=600)).isoformat()
        redis_mock.get.return_value = self._make_state_json(created_at=old_time)
        with pytest.raises(OAuth2StateExpiredError, match="expired"):
            await manager.validate_state(
                state="abc", client_ip="10.0.0.1", user_agent="Mozilla/5.0"
            )

    async def test_validate_no_created_at_skips_expiry(self, manager, redis_mock):
        data = {
            "provider": "okta",
            "callback_url": "/cb",
            "client_ip": "10.0.0.1",
            "user_agent": "Mozilla/5.0",
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
        redis_mock.get.return_value = json.dumps(data)
        result = await manager.validate_state(
            state="abc", client_ip="10.0.0.1", user_agent="Mozilla/5.0"
        )
        assert result["provider"] == "okta"

    async def test_validate_ip_mismatch(self, manager, redis_mock):
        redis_mock.get.return_value = self._make_state_json()
        with pytest.raises(OAuth2StateValidationError, match="Client IP mismatch"):
            await manager.validate_state(
                state="abc", client_ip="99.99.99.99", user_agent="Mozilla/5.0"
            )

    async def test_validate_user_agent_mismatch(self, manager, redis_mock):
        redis_mock.get.return_value = self._make_state_json()
        with pytest.raises(OAuth2StateValidationError, match="User agent mismatch"):
            await manager.validate_state(state="abc", client_ip="10.0.0.1", user_agent="BadBot/1.0")

    async def test_validate_delete_failure_logs_but_returns(self, manager, redis_mock):
        redis_mock.get.return_value = self._make_state_json()
        redis_mock.delete.side_effect = ConnectionError("delete failed")
        # Should still return data despite delete failure
        result = await manager.validate_state(
            state="abc", client_ip="10.0.0.1", user_agent="Mozilla/5.0"
        )
        assert result["provider"] == "okta"


class TestOAuth2StateManagerInvalidateState:
    @pytest.fixture()
    def redis_mock(self):
        mock = AsyncMock()
        mock.delete = AsyncMock()
        return mock

    @pytest.fixture()
    def manager(self, redis_mock):
        return OAuth2StateManager(redis_client=redis_mock)

    async def test_invalidate_success(self, manager, redis_mock):
        redis_mock.delete.return_value = 1
        result = await manager.invalidate_state("some_state")
        assert result is True
        redis_mock.delete.assert_awaited_once_with("oauth:state:some_state")

    async def test_invalidate_not_found(self, manager, redis_mock):
        redis_mock.delete.return_value = 0
        result = await manager.invalidate_state("nonexistent")
        assert result is False

    @patch(
        "src.core.shared.security.oauth_state_manager._allow_degraded_mode_without_redis",
        return_value=True,
    )
    async def test_invalidate_no_redis(self, _mock):
        mgr = OAuth2StateManager(redis_client=None)
        result = await mgr.invalidate_state("some_state")
        assert result is False

    async def test_invalidate_redis_error(self, manager, redis_mock):
        redis_mock.delete.side_effect = ConnectionError("conn refused")
        result = await manager.invalidate_state("some_state")
        assert result is False

    async def test_invalidate_os_error(self, manager, redis_mock):
        redis_mock.delete.side_effect = OSError("err")
        result = await manager.invalidate_state("some_state")
        assert result is False


# ---------------------------------------------------------------------------
# Unified Policy Generator Tests
# ---------------------------------------------------------------------------

from src.core.shared.policy.models import (
    PolicyLanguage,
    PolicySpecification,
    VerificationStatus,
    VerifiedPolicy,
)


class TestLLMProposer:
    @pytest.fixture()
    def proposer(self):
        from src.core.shared.policy.unified_generator import LLMProposer

        return LLMProposer()

    async def test_propose_harder_empty_corpus(self, proposer):
        results = await proposer.propose_harder([])
        assert len(results) == 3
        assert any("data integrity" in r for r in results)
        assert any("recursive" in r for r in results)
        assert any("temporal" in r for r in results)

    async def test_propose_harder_with_corpus(self, proposer):
        spec = PolicySpecification(spec_id="s1", natural_language="admin access only")
        vp = VerifiedPolicy(
            policy_id="p1",
            specification=spec,
            rego_policy="",
            dafny_spec="",
            smt_formulation="",
            verification_result={},
            generation_metadata={},
            verification_status=VerificationStatus.VERIFIED,
            confidence_score=0.8,
        )
        results = await proposer.propose_harder([vp])
        assert len(results) == 4
        assert "extends" in results[0]
        assert "admin access only" in results[0]


class TestAlphaVerusTranslator:
    @pytest.fixture()
    def translator(self):
        from src.core.shared.policy.unified_generator import AlphaVerusTranslator

        return AlphaVerusTranslator()

    async def test_translate_rego_admin(self, translator):
        spec = PolicySpecification(spec_id="abcd1234rest", natural_language="Admin users only")
        result = await translator.translate_policy(spec, PolicyLanguage.REGO)
        assert 'input.user.role == "admin"' in result
        assert CONSTITUTIONAL_HASH in result
        assert "package constitutional.abcd1234" in result

    async def test_translate_rego_owner(self, translator):
        spec = PolicySpecification(
            spec_id="own12345rest", natural_language="Only the owner can access"
        )
        result = await translator.translate_policy(spec, PolicyLanguage.REGO)
        assert "input.user.id == input.resource.owner_id" in result

    async def test_translate_rego_delete_without_owner(self, translator):
        spec = PolicySpecification(spec_id="del12345rest", natural_language="Cannot delete records")
        result = await translator.translate_policy(spec, PolicyLanguage.REGO)
        assert 'input.action != "delete"' in result

    async def test_translate_rego_delete_with_owner(self, translator):
        spec = PolicySpecification(spec_id="del12345rest", natural_language="owner can delete")
        result = await translator.translate_policy(spec, PolicyLanguage.REGO)
        assert 'input.action == "delete"' in result

    async def test_translate_rego_read(self, translator):
        spec = PolicySpecification(spec_id="read1234rest", natural_language="Allow read access")
        result = await translator.translate_policy(spec, PolicyLanguage.REGO)
        assert 'input.action == "read"' in result

    async def test_translate_rego_mfa(self, translator):
        spec = PolicySpecification(
            spec_id="mfa12345rest", natural_language="Require mfa for access"
        )
        result = await translator.translate_policy(spec, PolicyLanguage.REGO)
        assert "input.user.mfa_authenticated == true" in result

    async def test_translate_rego_multi_factor(self, translator):
        spec = PolicySpecification(
            spec_id="mf123456rest", natural_language="multi-factor auth required"
        )
        result = await translator.translate_policy(spec, PolicyLanguage.REGO)
        assert "input.user.mfa_authenticated == true" in result

    async def test_translate_rego_no_conditions(self, translator):
        spec = PolicySpecification(spec_id="gen12345rest", natural_language="general policy")
        result = await translator.translate_policy(spec, PolicyLanguage.REGO)
        assert "true" in result
        assert "default allow = false" in result

    async def test_translate_smt(self, translator):
        spec = PolicySpecification(
            spec_id="smt12345rest", natural_language="Admin access for delete with mfa"
        )
        result = await translator.translate_policy(spec, PolicyLanguage.SMT)
        assert "(set-logic QF_UF)" in result
        assert CONSTITUTIONAL_HASH in result
        assert "(check-sat)" in result
        assert "is_admin" in result
        assert "delete_action" in result
        assert "requires_mfa" in result

    async def test_translate_smt_read(self, translator):
        spec = PolicySpecification(spec_id="smt12345rest", natural_language="Allow read operations")
        result = await translator.translate_policy(spec, PolicyLanguage.SMT)
        assert "read_action" in result
        assert "(assert (not (is_critical read_action)))" in result

    async def test_translate_smt_owner(self, translator):
        spec = PolicySpecification(
            spec_id="smt12345rest", natural_language="owner can access resources"
        )
        result = await translator.translate_policy(spec, PolicyLanguage.SMT)
        assert "is_owner" in result

    async def test_translate_natural(self, translator):
        spec = PolicySpecification(spec_id="nat12345rest", natural_language="Some policy text")
        result = await translator.translate_policy(spec, PolicyLanguage.NATURAL)
        assert result == "Some policy text"

    def test_init_sets_history(self, translator):
        assert translator.translation_history == []
        assert translator.success_rate == 0.0


class TestDafnyProAnnotator:
    @pytest.fixture()
    def annotator(self):
        from src.core.shared.policy.unified_generator import DafnyProAnnotator

        return DafnyProAnnotator()

    def test_init_keywords(self, annotator):
        assert "critical" in annotator.high_impact_keywords
        assert "emergency" in annotator.high_impact_keywords
        assert annotator.max_refinements == 5

    def test_custom_max_refinements(self):
        from src.core.shared.policy.unified_generator import DafnyProAnnotator

        ann = DafnyProAnnotator(max_refinements=10)
        assert ann.max_refinements == 10

    async def test_annotate_basic(self, annotator):
        spec = PolicySpecification(spec_id="abc12345rest", natural_language="basic policy")
        result = await annotator.annotate("package test\nallow { true }", spec)
        assert CONSTITUTIONAL_HASH in result
        assert "Policy_abc12345" in result
        assert "ValidHash" in result

    async def test_annotate_critical_tag(self, annotator):
        spec = PolicySpecification(spec_id="crt12345rest", natural_language="basic policy")
        rego = "package test\n# critical security check\nallow { true }"
        result = await annotator.annotate(rego, spec)
        assert "[CRITICAL]" in result

    async def test_annotate_recursive(self, annotator):
        spec = PolicySpecification(spec_id="rec12345rest", natural_language="recursive swarm check")
        result = await annotator.annotate("package test\nallow { true }", spec)
        assert "[RECURSIVE]" in result
        assert "AgentSwarm" in result
        assert "ValidSwarm" in result

    async def test_annotate_resource_template(self, annotator):
        spec = PolicySpecification(
            spec_id="res12345rest", natural_language="resource ownership check"
        )
        result = await annotator.annotate("package test\nallow { true }", spec)
        assert "[RESOURCE]" in result
        assert "HasPermission" in result
        assert "IsOwner" in result

    async def test_annotate_owner_template(self, annotator):
        spec = PolicySpecification(
            spec_id="own12345rest", natural_language="only the owner can access"
        )
        result = await annotator.annotate("package test\nallow { true }", spec)
        assert "[RESOURCE]" in result

    def test_sync_with_rust_no_file(self, annotator):
        # Rust file doesn't exist in test env, should still have base keywords
        assert len(annotator.high_impact_keywords) >= 15

    @patch("builtins.open", side_effect=OSError("file error"))
    @patch("os.path.exists", return_value=True)
    def test_sync_with_rust_read_error(self, _exists, _open):
        from src.core.shared.policy.unified_generator import DafnyProAnnotator

        ann = DafnyProAnnotator()
        assert "critical" in ann.high_impact_keywords

    @patch("os.path.exists", return_value=True)
    def test_sync_with_rust_with_content(self, _exists):
        rust_content = """high_impact_keywords: vec!["custom_kw", "another_kw"]"""
        m = MagicMock()
        m.__enter__ = MagicMock(return_value=MagicMock(read=MagicMock(return_value=rust_content)))
        m.__exit__ = MagicMock(return_value=False)
        with patch("builtins.open", return_value=m):
            from src.core.shared.policy.unified_generator import DafnyProAnnotator

            ann = DafnyProAnnotator()
            assert "custom_kw" in ann.high_impact_keywords
            assert "another_kw" in ann.high_impact_keywords


class TestUnifiedVerifiedPolicyGenerator:
    @pytest.fixture()
    def generator(self):
        from src.core.shared.policy.unified_generator import UnifiedVerifiedPolicyGenerator

        return UnifiedVerifiedPolicyGenerator(max_iterations=2, dafny_path="/fake/dafny")

    def test_init_defaults(self):
        from src.core.shared.policy.unified_generator import UnifiedVerifiedPolicyGenerator

        gen = UnifiedVerifiedPolicyGenerator()
        assert gen.max_iterations == 5
        assert gen.verified_corpus == []

    @patch("src.core.shared.policy.unified_generator.UnifiedVerifiedPolicyGenerator._verify_smt")
    @patch("src.core.shared.policy.unified_generator.UnifiedVerifiedPolicyGenerator._verify_dafny")
    async def test_generate_verified_policy_success(self, mock_dafny, mock_smt, generator):
        mock_smt.return_value = {
            "status": "sat",
            "model": {},
            "alternative_paths": [],
            "solve_time_ms": 10,
            "unsat_core": [],
        }
        mock_dafny.return_value = {"status": "verified", "output": "ok", "verified": True}
        spec = PolicySpecification(spec_id="test1234rest", natural_language="Admin access only")

        result = await generator.generate_verified_policy(spec)
        assert result.verification_status == VerificationStatus.PROVEN
        assert result.confidence_score == 1.0
        assert "pol_" in result.policy_id
        assert len(generator.verified_corpus) == 1

    @patch("src.core.shared.policy.unified_generator.UnifiedVerifiedPolicyGenerator._verify_smt")
    @patch("src.core.shared.policy.unified_generator.UnifiedVerifiedPolicyGenerator._verify_dafny")
    async def test_generate_verified_policy_sat_not_proven(self, mock_dafny, mock_smt, generator):
        mock_smt.return_value = {"status": "sat", "model": {}, "alternative_paths": []}
        mock_dafny.return_value = {
            "status": "failed",
            "output": "",
            "error": "err",
            "verified": False,
        }
        spec = PolicySpecification(spec_id="test2345rest", natural_language="basic policy")

        result = await generator.generate_verified_policy(spec)
        assert result.verification_status == VerificationStatus.VERIFIED
        assert result.confidence_score == 0.8

    @patch("src.core.shared.policy.unified_generator.UnifiedVerifiedPolicyGenerator._verify_smt")
    @patch("src.core.shared.policy.unified_generator.UnifiedVerifiedPolicyGenerator._verify_dafny")
    async def test_generate_verified_policy_all_iterations_fail(
        self, mock_dafny, mock_smt, generator
    ):
        mock_smt.return_value = {"status": "unsat"}
        mock_dafny.return_value = {"status": "failed", "output": "", "error": "", "verified": False}
        spec = PolicySpecification(spec_id="fail1234rest", natural_language="impossible policy")

        result = await generator.generate_verified_policy(spec)
        assert result.verification_status == VerificationStatus.FAILED
        assert result.confidence_score == 0.0
        assert "failed_" in result.policy_id

    def test_verify_dafny_file_not_found(self, generator):
        result = generator._verify_dafny("module Test { }")
        assert result["status"] == "error"
        assert result["verified"] is False

    @patch("subprocess.run")
    def test_verify_dafny_success(self, mock_run, generator):
        mock_run.return_value = MagicMock(returncode=0, stdout="verified", stderr="")
        result = generator._verify_dafny("module Test { }")
        assert result["status"] == "verified"
        assert result["verified"] is True

    @patch("subprocess.run")
    def test_verify_dafny_failure(self, mock_run, generator):
        mock_run.return_value = MagicMock(returncode=1, stdout="out", stderr="error detail")
        result = generator._verify_dafny("module Test { }")
        assert result["status"] == "failed"
        assert result["verified"] is False
        assert result["error"] == "error detail"

    @patch("subprocess.run", side_effect=TimeoutError("timeout"))
    def test_verify_dafny_timeout(self, _mock, generator):
        # subprocess.TimeoutExpired needs specific args
        import subprocess as sp

        with patch("subprocess.run", side_effect=sp.TimeoutExpired(cmd="dafny", timeout=30)):
            result = generator._verify_dafny("module Test { }")
            assert result["status"] == "error"
            assert result["verified"] is False

    @patch("src.core.shared.policy.unified_generator.UnifiedVerifiedPolicyGenerator._verify_smt")
    @patch("src.core.shared.policy.unified_generator.UnifiedVerifiedPolicyGenerator._verify_dafny")
    async def test_generate_with_find_multiple(self, mock_dafny, mock_smt, generator):
        mock_smt.return_value = {
            "status": "sat",
            "model": {},
            "alternative_paths": ["path1"],
            "solve_time_ms": 5,
            "unsat_core": [],
        }
        mock_dafny.return_value = {"status": "verified", "verified": True, "output": "ok"}
        spec = PolicySpecification(spec_id="multi123rest", natural_language="Admin access only")

        # Mock the LLMAssistedZ3Adapter that gets imported inside the method
        mock_constraint = MagicMock()
        mock_constraint.expression = "(assert true)"
        mock_adapter_instance = AsyncMock()
        mock_adapter_instance._generate_single_constraint = AsyncMock(return_value=mock_constraint)
        mock_adapter_cls = MagicMock(return_value=mock_adapter_instance)

        # Patch at module level where it will be imported
        mock_z3_module = MagicMock()
        mock_z3_module.LLMAssistedZ3Adapter = mock_adapter_cls

        import sys

        with patch.dict(
            sys.modules, {"packages.enhanced_agent_bus.verification.z3_adapter": mock_z3_module}
        ):
            result = await generator.generate_verified_policy(spec, find_multiple=True)
            assert result.verification_status in (
                VerificationStatus.PROVEN,
                VerificationStatus.VERIFIED,
            )

    async def test_verify_smt_catches_errors(self, generator):
        # Test with deliberately malformed SMT that will cause the adapter to fail
        with patch(
            "src.core.shared.policy.unified_generator.Z3Constraint",
            side_effect=ValueError("bad constraint"),
        ):
            result = await generator._verify_smt("invalid smt")
            assert result["status"] == "error"


# ---------------------------------------------------------------------------
# Auth Provisioning Tests
# ---------------------------------------------------------------------------

from src.core.shared.auth.provisioning import (
    DomainNotAllowedError,
    JITProvisioner,
    ProvisioningDisabledError,
    ProvisioningError,
    ProvisioningResult,
    get_provisioner,
    reset_provisioner,
)


class TestProvisioningResult:
    def test_dataclass_fields(self):
        result = ProvisioningResult(
            user={"id": "1", "email": "a@b.com"},
            created=True,
            roles_updated=False,
            provider_id="prov-1",
        )
        assert result.user["id"] == "1"
        assert result.created is True
        assert result.provider_id == "prov-1"

    def test_default_provider_id(self):
        result = ProvisioningResult(user={}, created=False, roles_updated=False)
        assert result.provider_id is None


class TestProvisioningExceptions:
    def test_base_error(self):
        err = ProvisioningError("fail")
        assert err.http_status_code == 500
        assert err.error_code == "PROVISIONING_ERROR"

    def test_domain_not_allowed(self):
        err = DomainNotAllowedError("bad domain")
        assert isinstance(err, ProvisioningError)

    def test_provisioning_disabled(self):
        err = ProvisioningDisabledError("disabled")
        assert isinstance(err, ProvisioningError)


class TestJITProvisionerInit:
    def test_defaults(self):
        prov = JITProvisioner()
        assert prov.auto_provision_enabled is True
        assert prov.default_roles == []
        assert prov.allowed_domains is None

    def test_custom_config(self):
        prov = JITProvisioner(
            auto_provision_enabled=False,
            default_roles=["viewer"],
            allowed_domains=["example.com"],
        )
        assert prov.auto_provision_enabled is False
        assert prov.default_roles == ["viewer"]
        assert prov.allowed_domains == ["example.com"]


class TestJITProvisionerValidateEmailDomain:
    def test_no_restrictions(self):
        prov = JITProvisioner()
        assert prov._validate_email_domain("anyone@anything.org") is True

    def test_allowed_domain(self):
        prov = JITProvisioner(allowed_domains=["example.com"])
        assert prov._validate_email_domain("user@example.com") is True

    def test_disallowed_domain(self):
        prov = JITProvisioner(allowed_domains=["example.com"])
        assert prov._validate_email_domain("user@other.com") is False

    def test_case_insensitive(self):
        prov = JITProvisioner(allowed_domains=["Example.COM"])
        assert prov._validate_email_domain("user@example.com") is True


class TestJITProvisionerNormalizeEmail:
    def test_basic(self):
        prov = JITProvisioner()
        assert prov._normalize_email("User@Example.COM") == "user@example.com"

    def test_strips_whitespace(self):
        prov = JITProvisioner()
        assert prov._normalize_email("  user@example.com  ") == "user@example.com"


class TestJITProvisionerMergeRoles:
    @pytest.fixture()
    def prov(self):
        return JITProvisioner(default_roles=["viewer"])

    def test_idp_roles_take_precedence(self, prov):
        merged, changed = prov._merge_roles(["old"], ["admin", "editor"])
        assert merged == ["admin", "editor"]
        assert changed is True

    def test_no_idp_no_existing_uses_defaults(self, prov):
        merged, changed = prov._merge_roles([], [])
        assert merged == ["viewer"]
        assert changed is True

    def test_no_idp_existing_preserved(self, prov):
        merged, changed = prov._merge_roles(["admin"], [])
        assert merged == ["admin"]
        assert changed is False

    def test_deduplicates_and_sorts(self, prov):
        merged, _changed = prov._merge_roles([], ["b", "a", "b"])
        assert merged == ["a", "b"]

    def test_no_change_detected(self, prov):
        _merged, changed = prov._merge_roles(["a", "b"], ["a", "b"])
        assert changed is False

    def test_custom_defaults(self, prov):
        merged, _changed = prov._merge_roles([], [], default_roles=["custom"])
        assert merged == ["custom"]


class TestJITProvisionerGetOrCreateUser:
    @pytest.fixture()
    def prov(self):
        return JITProvisioner(default_roles=["viewer"], allowed_domains=["example.com"])

    async def test_domain_not_allowed_raises(self, prov):
        with pytest.raises(DomainNotAllowedError, match="not allowed"):
            await prov.get_or_create_user(email="user@badsite.com")

    async def test_in_memory_provisioning(self):
        prov = JITProvisioner(default_roles=["dev"])
        result = await prov.get_or_create_user(
            email="Test@Example.COM",
            name="Test User",
            sso_provider="oidc",
            idp_user_id="sub-123",
            provider_id="prov-1",
            roles=["admin"],
            name_id="nid",
            session_index="si",
        )
        assert result.created is True
        assert result.user["email"] == "test@example.com"
        assert result.user["sso_provider"] == "oidc"
        assert result.user["roles"] == ["admin"]
        assert result.user["sso_name_id"] == "nid"
        assert result.user["sso_session_index"] == "si"
        assert result.provider_id == "prov-1"

    async def test_in_memory_default_roles(self):
        prov = JITProvisioner(default_roles=["viewer"])
        result = await prov.get_or_create_user(email="a@b.com")
        assert result.user["roles"] == ["viewer"]
        assert result.roles_updated is True

    async def test_in_memory_no_roles(self):
        prov = JITProvisioner(default_roles=[])
        result = await prov.get_or_create_user(email="a@b.com")
        assert result.user["roles"] == []
        assert result.roles_updated is False

    async def test_normalizes_email(self):
        prov = JITProvisioner()
        result = await prov.get_or_create_user(email="  User@EXAMPLE.com  ")
        assert result.user["email"] == "user@example.com"


class TestGetResetProvisioner:
    def setup_method(self):
        reset_provisioner()

    def teardown_method(self):
        reset_provisioner()

    def test_get_creates_singleton(self):
        p1 = get_provisioner()
        p2 = get_provisioner()
        assert p1 is p2

    def test_get_with_params(self):
        p = get_provisioner(
            auto_provision_enabled=False,
            default_roles=["admin"],
            allowed_domains=["test.com"],
        )
        assert p.auto_provision_enabled is False
        assert p.default_roles == ["admin"]

    def test_reset_clears_singleton(self):
        p1 = get_provisioner()
        reset_provisioner()
        p2 = get_provisioner()
        assert p1 is not p2


# ---------------------------------------------------------------------------
# Database Utils Tests
# ---------------------------------------------------------------------------

from src.core.shared.database.utils import (
    BaseRepository,
    BulkOperations,
    Page,
    Pageable,
)


class TestPageable:
    def test_defaults(self):
        p = Pageable()
        assert p.page == 0
        assert p.size == 20
        assert p.sort == []

    def test_offset(self):
        p = Pageable(page=3, size=10)
        assert p.offset == 30

    def test_limit(self):
        p = Pageable(page=0, size=50)
        assert p.limit == 50

    def test_with_sort(self):
        p = Pageable()
        p2 = p.with_sort("name", "desc")
        assert p2.sort == [("name", "desc")]
        assert p.sort == []  # original unchanged (immutable)

    def test_next_page(self):
        p = Pageable(page=2, size=10, sort=[("id", "asc")])
        n = p.next_page()
        assert n.page == 3
        assert n.size == 10
        assert n.sort == [("id", "asc")]

    def test_previous_page(self):
        p = Pageable(page=2, size=10)
        prev = p.previous_page()
        assert prev is not None
        assert prev.page == 1

    def test_previous_page_first(self):
        p = Pageable(page=0)
        assert p.previous_page() is None


class TestPage:
    def test_total_pages(self):
        p = Page(content=[1, 2, 3], total_elements=25, page_number=0, page_size=10)
        assert p.total_pages == 3

    def test_total_pages_exact(self):
        p = Page(content=list(range(10)), total_elements=20, page_number=0, page_size=10)
        assert p.total_pages == 2

    def test_total_pages_one(self):
        p = Page(content=[1], total_elements=1, page_number=0, page_size=10)
        assert p.total_pages == 1

    def test_has_next(self):
        p = Page(content=[1], total_elements=25, page_number=0, page_size=10)
        assert p.has_next is True

    def test_has_next_last_page(self):
        p = Page(content=[1], total_elements=25, page_number=2, page_size=10)
        assert p.has_next is False

    def test_has_previous(self):
        p = Page(content=[1], total_elements=25, page_number=1, page_size=10)
        assert p.has_previous is True

    def test_has_previous_first(self):
        p = Page(content=[1], total_elements=25, page_number=0, page_size=10)
        assert p.has_previous is False

    def test_is_first(self):
        p = Page(content=[1], total_elements=25, page_number=0, page_size=10)
        assert p.is_first is True

    def test_is_first_false(self):
        p = Page(content=[1], total_elements=25, page_number=1, page_size=10)
        assert p.is_first is False

    def test_is_last(self):
        p = Page(content=[1], total_elements=25, page_number=2, page_size=10)
        assert p.is_last is True

    def test_is_last_false(self):
        p = Page(content=[1], total_elements=25, page_number=0, page_size=10)
        assert p.is_last is False

    def test_number_of_elements(self):
        p = Page(content=[1, 2, 3], total_elements=100, page_number=0, page_size=10)
        assert p.number_of_elements == 3

    def test_empty_page(self):
        p = Page(content=[], total_elements=0, page_number=0, page_size=10)
        assert p.total_pages == 0
        assert p.has_next is False
        assert p.is_first is True
        assert p.number_of_elements == 0


class TestBulkOperations:
    """Test BulkOperations static methods.

    Since these methods use real SQLAlchemy Core (insert/update/delete), we
    need to create a real in-memory table to avoid mocking deep SQLAlchemy
    internals. We patch session.execute to capture the statements.
    """

    @pytest.fixture()
    def session(self):
        return AsyncMock()

    @pytest.fixture()
    def table(self):
        """Create a real SQLAlchemy Table for testing."""
        from sqlalchemy import Column, Integer, MetaData, String
        from sqlalchemy import Table as SATable

        metadata = MetaData()
        return SATable(
            "test_table",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("name", String),
            Column("status", String),
        )

    async def test_bulk_insert_empty(self, session, table):
        result = await BulkOperations.bulk_insert(session, table, [])
        assert result is None
        session.execute.assert_not_awaited()

    async def test_bulk_insert_without_return(self, session, table):
        values = [{"name": "a"}, {"name": "b"}]
        result = await BulkOperations.bulk_insert(session, table, values)
        assert result is None
        session.execute.assert_awaited()

    async def test_bulk_insert_with_return(self, session, table):
        mappings_mock = MagicMock()
        mappings_mock.all.return_value = [{"id": 1}, {"id": 2}]
        exec_result = MagicMock()
        exec_result.mappings.return_value = mappings_mock
        session.execute.return_value = exec_result

        values = [{"name": "a"}]
        result = await BulkOperations.bulk_insert(session, table, values, return_defaults=True)
        assert result == [{"id": 1}, {"id": 2}]

    async def test_bulk_insert_batching(self, session, table):
        values = [{"name": f"item_{i}"} for i in range(5)]
        await BulkOperations.bulk_insert(session, table, values, batch_size=2)
        # 5 items / batch_size 2 = 3 batches
        assert session.execute.await_count == 3

    async def test_bulk_insert_on_conflict_empty(self, session, table):
        await BulkOperations.bulk_insert_on_conflict(session, table, [], ["id"])
        session.execute.assert_not_awaited()

    async def test_bulk_insert_on_conflict_do_nothing(self, session, table):
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        values = [{"id": 1, "name": "a"}]
        with patch("src.core.shared.database.utils.insert", pg_insert):
            await BulkOperations.bulk_insert_on_conflict(
                session, table, values, index_elements=["id"]
            )
        session.execute.assert_awaited_once()

    async def test_bulk_insert_on_conflict_do_update(self, session, table):
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        values = [{"id": 1, "name": "a"}]
        with patch("src.core.shared.database.utils.insert", pg_insert):
            await BulkOperations.bulk_insert_on_conflict(
                session, table, values, index_elements=["id"], update_columns=["name"]
            )
        session.execute.assert_awaited_once()

    async def test_bulk_update_empty(self, session, table):
        count = await BulkOperations.bulk_update(session, table, [])
        assert count == 0

    async def test_bulk_update_missing_id(self, session, table):
        values = [{"name": "a"}]  # missing id
        with pytest.raises(ACGSValidationError, match="missing 'id' field"):
            await BulkOperations.bulk_update(session, table, values)

    async def test_bulk_update_success(self, session, table):
        exec_result = MagicMock()
        exec_result.rowcount = 1
        session.execute.return_value = exec_result
        values = [{"id": 1, "name": "updated"}]
        count = await BulkOperations.bulk_update(session, table, values)
        assert count == 1

    async def test_bulk_delete_empty(self, session, table):
        count = await BulkOperations.bulk_delete(session, table, [])
        assert count == 0

    async def test_bulk_delete_with_ids(self, session, table):
        exec_result = MagicMock()
        exec_result.rowcount = 3
        session.execute.return_value = exec_result
        count = await BulkOperations.bulk_delete(session, table, [1, 2, 3])
        assert count == 3

    async def test_bulk_delete_batching(self, session, table):
        exec_result = MagicMock()
        exec_result.rowcount = 2
        session.execute.return_value = exec_result
        count = await BulkOperations.bulk_delete(session, table, list(range(5)), batch_size=2)
        # 3 batches, each returning 2
        assert count == 6


class TestBaseRepository:
    """Test BaseRepository using patched select() to avoid SQLAlchemy model requirements."""

    @pytest.fixture()
    def session(self):
        s = AsyncMock()
        # Make add and add_all regular methods (not coroutines)
        s.add = MagicMock()
        s.add_all = MagicMock()
        return s

    @pytest.fixture()
    def model(self):
        m = MagicMock()
        m.id = MagicMock()
        return m

    @pytest.fixture()
    def repo(self, session, model):
        return BaseRepository(session, model)

    async def test_find_by_id(self, repo, session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = {"id": "1"}
        session.execute.return_value = mock_result
        with patch("src.core.shared.database.utils.select") as mock_select:
            mock_stmt = MagicMock()
            mock_stmt.where.return_value = mock_stmt
            mock_select.return_value = mock_stmt
            result = await repo.find_by_id("1")
            assert result == {"id": "1"}

    async def test_save(self, repo, session):
        entity = MagicMock()
        result = await repo.save(entity)
        session.add.assert_called_once_with(entity)
        session.flush.assert_awaited_once()
        assert result is entity

    async def test_save_all(self, repo, session):
        entities = [MagicMock(), MagicMock()]
        result = await repo.save_all(entities)
        session.add_all.assert_called_once_with(entities)
        assert result is entities

    async def test_delete(self, repo, session):
        entity = MagicMock()
        await repo.delete(entity)
        session.delete.assert_awaited_once_with(entity)

    async def test_delete_by_id_found(self, repo, session):
        entity = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = entity
        session.execute.return_value = mock_result
        with patch("src.core.shared.database.utils.select") as mock_select:
            mock_stmt = MagicMock()
            mock_stmt.where.return_value = mock_stmt
            mock_select.return_value = mock_stmt
            result = await repo.delete_by_id("1")
            assert result is True

    async def test_delete_by_id_not_found(self, repo, session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result
        with patch("src.core.shared.database.utils.select") as mock_select:
            mock_stmt = MagicMock()
            mock_stmt.where.return_value = mock_stmt
            mock_select.return_value = mock_stmt
            result = await repo.delete_by_id("1")
            assert result is False

    async def test_count(self, repo, session):
        mock_result = MagicMock()
        mock_result.scalar.return_value = 42
        session.execute.return_value = mock_result
        with patch("src.core.shared.database.utils.select") as mock_select:
            mock_select.return_value = MagicMock()
            result = await repo.count()
            assert result == 42

    async def test_count_none_returns_zero(self, repo, session):
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        session.execute.return_value = mock_result
        with patch("src.core.shared.database.utils.select") as mock_select:
            mock_select.return_value = MagicMock()
            result = await repo.count()
            assert result == 0

    async def test_find_all_no_pageable(self, repo, session):
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = ["item1", "item2"]
        mock_result = MagicMock()
        mock_result.scalars.return_value = scalars_mock
        session.execute.return_value = mock_result
        with patch("src.core.shared.database.utils.select") as mock_select:
            mock_stmt = MagicMock()
            mock_stmt.where.return_value = mock_stmt
            mock_select.return_value = mock_stmt
            result = await repo.find_all()
            assert result == ["item1", "item2"]
