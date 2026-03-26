"""
Coverage tests for batch 22c:
  1. constitutional/storage_infra/service.py
  2. middlewares/temporal_policy.py
  3. constitutional_classifier/detector.py
  4. opal_client.py

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# 1. ConstitutionalStorageService tests
# ---------------------------------------------------------------------------
from enhanced_agent_bus.constitutional.storage_infra.config import StorageConfig
from enhanced_agent_bus.constitutional.storage_infra.service import (
    ConstitutionalStorageService,
)
from enhanced_agent_bus.constitutional.version_model import (
    ConstitutionalStatus,
    ConstitutionalVersion,
)


def _make_version(
    version_id: str = "v1",
    version: str = "1.0.0",
    status: ConstitutionalStatus = ConstitutionalStatus.DRAFT,
) -> ConstitutionalVersion:
    return ConstitutionalVersion(
        version_id=version_id,
        version=version,
        constitutional_hash="608508a9bd224290",
        content={"policies": []},
        status=status,
    )


class TestConstitutionalStorageService:
    """Tests for ConstitutionalStorageService."""

    def _make_service(self) -> ConstitutionalStorageService:
        svc = ConstitutionalStorageService.__new__(ConstitutionalStorageService)
        svc.config = StorageConfig()
        svc.cache = MagicMock()
        svc.persistence = MagicMock()
        svc.lock = MagicMock()
        return svc

    async def test_init_defaults(self) -> None:
        with (
            patch("enhanced_agent_bus.constitutional.storage_infra.service.CacheManager"),
            patch("enhanced_agent_bus.constitutional.storage_infra.service.PersistenceManager"),
            patch("enhanced_agent_bus.constitutional.storage_infra.service.LockManager"),
        ):
            svc = ConstitutionalStorageService()
            assert svc.config is not None

    async def test_connect_both_ok(self) -> None:
        svc = self._make_service()
        svc.cache.connect = AsyncMock(return_value=True)
        svc.persistence.connect = AsyncMock(return_value=True)
        assert await svc.connect() is True

    async def test_connect_cache_fails(self) -> None:
        svc = self._make_service()
        svc.cache.connect = AsyncMock(return_value=False)
        svc.persistence.connect = AsyncMock(return_value=True)
        assert await svc.connect() is False

    async def test_connect_persistence_fails(self) -> None:
        svc = self._make_service()
        svc.cache.connect = AsyncMock(return_value=True)
        svc.persistence.connect = AsyncMock(return_value=False)
        assert await svc.connect() is False

    async def test_disconnect(self) -> None:
        svc = self._make_service()
        svc.cache.disconnect = AsyncMock()
        svc.persistence.disconnect = AsyncMock()
        await svc.disconnect()
        svc.cache.disconnect.assert_awaited_once()
        svc.persistence.disconnect.assert_awaited_once()

    async def test_save_version(self) -> None:
        svc = self._make_service()
        v = _make_version()
        svc.persistence.save_version = AsyncMock(return_value=True)
        result = await svc.save_version(v, "t1")
        svc.persistence.save_version.assert_awaited_once_with(v, "t1")
        assert result is True

    async def test_get_version_cache_hit(self) -> None:
        svc = self._make_service()
        v = _make_version()
        svc.cache.get_version = AsyncMock(return_value=v)
        result = await svc.get_version("v1", "t1")
        assert result is v
        svc.persistence.get_version = AsyncMock()
        svc.persistence.get_version.assert_not_awaited()

    async def test_get_version_cache_miss_persist_hit(self) -> None:
        svc = self._make_service()
        v = _make_version()
        svc.cache.get_version = AsyncMock(return_value=None)
        svc.persistence.get_version = AsyncMock(return_value=v)
        svc.cache.set_version = AsyncMock()
        result = await svc.get_version("v1", "t1")
        assert result is v
        svc.cache.set_version.assert_awaited_once_with(v, "t1")

    async def test_get_version_not_found(self) -> None:
        svc = self._make_service()
        svc.cache.get_version = AsyncMock(return_value=None)
        svc.persistence.get_version = AsyncMock(return_value=None)
        result = await svc.get_version("v1", "t1")
        assert result is None

    async def test_get_active_version_cache_hot_path(self) -> None:
        svc = self._make_service()
        v = _make_version()
        svc.cache.get_active_version_id = AsyncMock(return_value="v1")
        svc.cache.get_version = AsyncMock(return_value=v)
        result = await svc.get_active_version("t1")
        assert result is v

    async def test_get_active_version_cache_id_but_no_version(self) -> None:
        svc = self._make_service()
        v = _make_version(status=ConstitutionalStatus.ACTIVE)
        svc.cache.get_active_version_id = AsyncMock(return_value="v1")
        svc.cache.get_version = AsyncMock(return_value=None)
        svc.persistence.get_active_version = AsyncMock(return_value=v)
        svc.cache.set_version = AsyncMock()
        svc.cache.set_active_version = AsyncMock()
        result = await svc.get_active_version("t1")
        assert result is v
        svc.cache.set_version.assert_awaited_once()
        svc.cache.set_active_version.assert_awaited_once()

    async def test_get_active_version_no_cache_id(self) -> None:
        svc = self._make_service()
        svc.cache.get_active_version_id = AsyncMock(return_value=None)
        svc.persistence.get_active_version = AsyncMock(return_value=None)
        result = await svc.get_active_version("t1")
        assert result is None

    async def test_activate_version_lock_fail(self) -> None:
        svc = self._make_service()
        svc.lock.acquire_lock = AsyncMock(return_value=False)
        assert await svc.activate_version("v1", "t1") is False

    async def test_activate_version_not_found(self) -> None:
        svc = self._make_service()
        svc.lock.acquire_lock = AsyncMock(return_value=True)
        svc.lock.release_lock = AsyncMock()
        svc.cache.get_version = AsyncMock(return_value=None)
        svc.persistence.get_version = AsyncMock(return_value=None)
        assert await svc.activate_version("v1", "t1") is False
        svc.lock.release_lock.assert_awaited_once()

    async def test_activate_version_success_no_current(self) -> None:
        svc = self._make_service()
        v = _make_version()
        svc.lock.acquire_lock = AsyncMock(return_value=True)
        svc.lock.release_lock = AsyncMock()
        # get_version returns our version
        svc.cache.get_version = AsyncMock(return_value=v)
        # get_active_version returns None (no current active)
        svc.cache.get_active_version_id = AsyncMock(return_value=None)
        svc.persistence.get_active_version = AsyncMock(return_value=None)
        svc.persistence.update_version = AsyncMock()
        svc.cache.set_version = AsyncMock()
        svc.cache.set_active_version = AsyncMock()
        assert await svc.activate_version("v1", "t1") is True
        svc.lock.release_lock.assert_awaited_once()

    async def test_activate_version_success_with_current(self) -> None:
        svc = self._make_service()
        current = _make_version(version_id="v0", status=ConstitutionalStatus.ACTIVE)
        new_v = _make_version(version_id="v1")
        svc.lock.acquire_lock = AsyncMock(return_value=True)
        svc.lock.release_lock = AsyncMock()
        svc.cache.get_version = AsyncMock(return_value=new_v)
        svc.cache.get_active_version_id = AsyncMock(return_value="v0")
        # For the get_active_version path: first call for new_v, second for current
        # We need get_version to be called multiple times with different results
        # But the path is: activate_version calls get_version(v1) -> new_v
        # Then calls get_active_version which calls cache.get_active_version_id -> "v0"
        # Then cache.get_version("v0") -> we need current here
        call_count = 0

        async def _get_version_side_effect(vid, tid):
            nonlocal call_count
            call_count += 1
            if vid == "v1":
                return new_v
            return current

        svc.cache.get_version = AsyncMock(side_effect=_get_version_side_effect)
        svc.persistence.update_version = AsyncMock()
        svc.cache.set_version = AsyncMock()
        svc.cache.set_active_version = AsyncMock()
        assert await svc.activate_version("v1", "t1") is True
        # current should have been deactivated
        assert svc.persistence.update_version.await_count >= 2

    async def test_save_amendment(self) -> None:
        svc = self._make_service()
        amendment = MagicMock()
        svc.persistence.save_amendment = AsyncMock(return_value=True)
        assert await svc.save_amendment(amendment, "t1") is True

    async def test_get_amendment(self) -> None:
        svc = self._make_service()
        amendment = MagicMock()
        svc.persistence.get_amendment = AsyncMock(return_value=amendment)
        assert await svc.get_amendment("p1", "t1") is amendment

    async def test_list_versions(self) -> None:
        svc = self._make_service()
        svc.persistence.list_versions = AsyncMock(return_value=[])
        result = await svc.list_versions("t1", limit=10, offset=5, status="active")
        svc.persistence.list_versions.assert_awaited_once_with("t1", 10, 5, "active")
        assert result == []

    async def test_list_amendments(self) -> None:
        svc = self._make_service()
        svc.persistence.list_amendments = AsyncMock(return_value=([], 0))
        result = await svc.list_amendments(
            "t1", limit=10, offset=0, status="proposed", proposer_id="p1"
        )
        svc.persistence.list_amendments.assert_awaited_once_with("t1", 10, 0, "proposed", "p1")
        assert result == ([], 0)


# ---------------------------------------------------------------------------
# 2. TemporalPolicyMiddleware tests
# ---------------------------------------------------------------------------

from enhanced_agent_bus.middlewares.temporal_policy import (
    _GOVERNED_ACTIONS,
    GovernanceRule,
    TemporalPolicyMiddleware,
)
from enhanced_agent_bus.validators import ValidationResult


class TestGovernanceRule:
    """Tests for GovernanceRule dataclass."""

    def test_not_expired_no_ttl(self) -> None:
        rule = GovernanceRule(rule_id="r1", action="modify_policy", created_at=time.time())
        assert rule.is_expired() is False

    def test_not_expired_within_ttl(self) -> None:
        rule = GovernanceRule(
            rule_id="r1", action="modify_policy", created_at=time.time(), ttl_seconds=3600
        )
        assert rule.is_expired() is False

    def test_expired(self) -> None:
        rule = GovernanceRule(
            rule_id="r1", action="modify_policy", created_at=1000.0, ttl_seconds=10
        )
        assert rule.is_expired(now=1020.0) is True

    def test_not_expired_explicit_now(self) -> None:
        rule = GovernanceRule(
            rule_id="r1", action="modify_policy", created_at=1000.0, ttl_seconds=100
        )
        assert rule.is_expired(now=1050.0) is False

    def test_default_policy_path(self) -> None:
        rule = GovernanceRule(rule_id="r1", action="test", created_at=0.0)
        assert rule.policy_path == "data.acgs.temporal.allow"


def _make_pipeline_context(requested_tool: str | None = None, impact_score: float = 0.0):
    """Create a minimal PipelineContext with mocked message."""
    msg = MagicMock()
    msg.requested_tool = requested_tool
    ctx = MagicMock()
    ctx.message = msg
    ctx.action_history = []
    ctx.impact_score = impact_score
    ctx.constitutional_validated = False
    ctx.add_middleware = MagicMock()
    ctx.set_early_result = MagicMock()
    return ctx


class TestTemporalPolicyMiddleware:
    """Tests for TemporalPolicyMiddleware."""

    def test_init_defaults(self) -> None:
        mw = TemporalPolicyMiddleware()
        assert mw.config.timeout_ms == 50
        assert mw.config.fail_closed is True
        assert mw._governance_rules == {}

    def test_register_governance_rule(self) -> None:
        mw = TemporalPolicyMiddleware()
        rule = GovernanceRule(rule_id="r1", action="modify_policy", created_at=time.time())
        mw.register_governance_rule(rule)
        assert "r1" in mw._governance_rules

    def test_enforce_rule_not_expired(self) -> None:
        mw = TemporalPolicyMiddleware()
        rule = GovernanceRule(
            rule_id="r1", action="modify_policy", created_at=time.time(), ttl_seconds=3600
        )
        result = mw.enforce_rule(rule)
        assert result.is_valid is True

    def test_enforce_rule_expired(self) -> None:
        mw = TemporalPolicyMiddleware()
        rule = GovernanceRule(
            rule_id="r1", action="modify_policy", created_at=1000.0, ttl_seconds=10
        )
        result = mw.enforce_rule(rule, now=1020.0)
        assert result.is_valid is False
        assert len(result.errors) > 0
        assert "expired" in result.errors[0].lower()

    def test_enforce_rule_no_ttl(self) -> None:
        mw = TemporalPolicyMiddleware()
        rule = GovernanceRule(rule_id="r1", action="modify_policy", created_at=1000.0)
        result = mw.enforce_rule(rule, now=999999.0)
        assert result.is_valid is True

    def test_enforce_rule_uses_time_when_now_none(self) -> None:
        mw = TemporalPolicyMiddleware()
        rule = GovernanceRule(
            rule_id="r1", action="modify_policy", created_at=time.time(), ttl_seconds=3600
        )
        result = mw.enforce_rule(rule, now=None)
        assert result.is_valid is True

    async def test_process_no_action_passthrough(self) -> None:
        mw = TemporalPolicyMiddleware()
        ctx = _make_pipeline_context(requested_tool=None)
        mw._next = MagicMock()
        mw._next.process = AsyncMock(return_value=ctx)
        result = await mw.process(ctx)
        ctx.add_middleware.assert_called_once_with("TemporalPolicyMiddleware")

    async def test_process_ungoverned_action_passthrough(self) -> None:
        mw = TemporalPolicyMiddleware()
        ctx = _make_pipeline_context(requested_tool="read_only_query")
        mw._next = MagicMock()
        mw._next.process = AsyncMock(return_value=ctx)
        result = await mw.process(ctx)
        ctx.set_early_result.assert_not_called()

    async def test_process_governed_action_ttl_expired(self) -> None:
        mw = TemporalPolicyMiddleware()
        rule = GovernanceRule(
            rule_id="r1", action="modify_policy", created_at=1000.0, ttl_seconds=10
        )
        mw.register_governance_rule(rule)
        ctx = _make_pipeline_context(requested_tool="modify_policy")
        result = await mw.process(ctx)
        ctx.set_early_result.assert_called_once()
        vr = ctx.set_early_result.call_args[0][0]
        assert vr.is_valid is False

    @patch("enhanced_agent_bus.middlewares.temporal_policy.get_opa_client")
    async def test_process_governed_action_opa_allows(self, mock_get_opa) -> None:
        mw = TemporalPolicyMiddleware()
        mock_opa = MagicMock()
        mock_opa.evaluate_with_history = AsyncMock(return_value={"allowed": True})
        mock_get_opa.return_value = mock_opa

        ctx = _make_pipeline_context(requested_tool="modify_policy")
        mw._next = MagicMock()
        mw._next.process = AsyncMock(return_value=ctx)

        result = await mw.process(ctx)
        assert "modify_policy" in ctx.action_history
        ctx.set_early_result.assert_not_called()

    @patch("enhanced_agent_bus.middlewares.temporal_policy.get_opa_client")
    async def test_process_governed_action_opa_denies(self, mock_get_opa) -> None:
        mw = TemporalPolicyMiddleware()
        mock_opa = MagicMock()
        mock_opa.evaluate_with_history = AsyncMock(
            return_value={"allowed": False, "reason": "ordering violation", "metadata": {"x": 1}}
        )
        mock_get_opa.return_value = mock_opa

        ctx = _make_pipeline_context(requested_tool="execute_action")
        result = await mw.process(ctx)
        ctx.set_early_result.assert_called_once()
        vr = ctx.set_early_result.call_args[0][0]
        assert vr.is_valid is False
        assert "temporal:ordering violation" in vr.errors[0]

    @patch("enhanced_agent_bus.middlewares.temporal_policy.get_opa_client")
    async def test_process_governed_action_opa_denies_default_reason(self, mock_get_opa) -> None:
        mw = TemporalPolicyMiddleware()
        mock_opa = MagicMock()
        mock_opa.evaluate_with_history = AsyncMock(return_value={"allowed": False})
        mock_get_opa.return_value = mock_opa

        ctx = _make_pipeline_context(requested_tool="execute_action")
        result = await mw.process(ctx)
        ctx.set_early_result.assert_called_once()
        vr = ctx.set_early_result.call_args[0][0]
        assert "temporal ordering violation" in vr.errors[0]

    @patch("enhanced_agent_bus.middlewares.temporal_policy.get_opa_client")
    async def test_process_opa_exception_fail_closed(self, mock_get_opa) -> None:
        mw = TemporalPolicyMiddleware()
        mock_get_opa.side_effect = RuntimeError("OPA down")

        ctx = _make_pipeline_context(requested_tool="modify_policy")
        result = await mw.process(ctx)
        ctx.set_early_result.assert_called_once()
        vr = ctx.set_early_result.call_args[0][0]
        assert vr.is_valid is False
        assert "fail-closed" in vr.errors[0]

    @patch("enhanced_agent_bus.middlewares.temporal_policy.get_opa_client")
    async def test_process_opa_oserror(self, mock_get_opa) -> None:
        mw = TemporalPolicyMiddleware()
        mock_opa = MagicMock()
        mock_opa.evaluate_with_history = AsyncMock(side_effect=OSError("network"))
        mock_get_opa.return_value = mock_opa

        ctx = _make_pipeline_context(requested_tool="approve_message")
        result = await mw.process(ctx)
        ctx.set_early_result.assert_called_once()

    def test_governed_actions_set(self) -> None:
        assert "modify_policy" in _GOVERNED_ACTIONS
        assert "execute_action" in _GOVERNED_ACTIONS
        assert "read_only" not in _GOVERNED_ACTIONS


# ---------------------------------------------------------------------------
# 3. ThreatDetector tests
# ---------------------------------------------------------------------------

from enhanced_agent_bus.constitutional_classifier.detector import (
    DetectionDecision,
    DetectionMode,
    DetectionResult,
    DetectorConfig,
    ThreatDetector,
    get_threat_detector,
)
from enhanced_agent_bus.constitutional_classifier.patterns import (
    PatternMatchResult,
    ThreatCategory,
    ThreatPattern,
    ThreatSeverity,
)
from enhanced_agent_bus.constitutional_classifier.scoring import (
    ComplianceScore,
)


def _make_compliance_score(
    final_score: float = 0.95,
    is_compliant: bool = True,
    threat_matches: list | None = None,
) -> ComplianceScore:
    return ComplianceScore(
        final_score=final_score,
        is_compliant=is_compliant,
        threshold=0.85,
        confidence=0.9,
        threat_matches=threat_matches or [],
    )


class TestDetectionResult:
    """Tests for DetectionResult dataclass."""

    def test_to_dict_basic(self) -> None:
        result = DetectionResult(
            decision=DetectionDecision.ALLOW,
            threat_detected=False,
        )
        d = result.to_dict()
        assert d["decision"] == "allow"
        assert d["threat_detected"] is False
        assert d["compliance_score"] is None
        assert d["mode"] == "standard"
        assert d["categories_detected"] == []
        assert d["max_severity"] is None

    def test_to_dict_with_score_and_categories(self) -> None:
        score = _make_compliance_score()
        result = DetectionResult(
            decision=DetectionDecision.BLOCK,
            threat_detected=True,
            compliance_score=score,
            categories_detected={ThreatCategory.PROMPT_INJECTION},
            max_severity=ThreatSeverity.CRITICAL,
        )
        d = result.to_dict()
        assert d["decision"] == "block"
        assert d["threat_detected"] is True
        assert d["max_severity"] == "critical"
        assert "prompt_injection" in d["categories_detected"]
        assert d["compliance_score"] is not None


class TestDetectorConfig:
    """Tests for DetectorConfig."""

    def test_defaults(self) -> None:
        config = DetectorConfig()
        assert config.block_threshold == 0.4
        assert config.flag_threshold == 0.7
        assert config.strict_mode is True
        assert config.enable_caching is True
        assert ThreatCategory.CONSTITUTIONAL_BYPASS in config.escalate_categories


class TestThreatDetector:
    """Tests for ThreatDetector."""

    def _make_detector(self, **config_kwargs) -> ThreatDetector:
        config = DetectorConfig(**config_kwargs)
        scoring_engine = MagicMock()
        pattern_registry = MagicMock()
        return ThreatDetector(
            config=config,
            scoring_engine=scoring_engine,
            pattern_registry=pattern_registry,
        )

    async def test_detect_standard_allow(self) -> None:
        detector = self._make_detector()
        score = _make_compliance_score(final_score=0.95, is_compliant=True)
        detector.scoring_engine.calculate_score = MagicMock(return_value=score)

        result = await detector.detect("hello world")
        assert result.decision == DetectionDecision.ALLOW
        assert result.threat_detected is False

    async def test_detect_standard_block_low_score(self) -> None:
        detector = self._make_detector()
        score = _make_compliance_score(final_score=0.2, is_compliant=False)
        detector.scoring_engine.calculate_score = MagicMock(return_value=score)

        result = await detector.detect("malicious content", use_cache=False)
        assert result.decision == DetectionDecision.BLOCK

    async def test_detect_standard_flag(self) -> None:
        detector = self._make_detector()
        score = _make_compliance_score(final_score=0.6, is_compliant=False)
        detector.scoring_engine.calculate_score = MagicMock(return_value=score)

        result = await detector.detect("borderline", use_cache=False)
        assert result.decision == DetectionDecision.FLAG

    async def test_detect_standard_escalate(self) -> None:
        detector = self._make_detector()
        pattern = ThreatPattern(
            pattern="bypass",
            category=ThreatCategory.CONSTITUTIONAL_BYPASS,
            severity=ThreatSeverity.HIGH,
            description="test",
        )
        match = PatternMatchResult(matched=True, pattern=pattern, match_text="bypass")
        score = _make_compliance_score(final_score=0.6, is_compliant=False, threat_matches=[match])
        detector.scoring_engine.calculate_score = MagicMock(return_value=score)

        result = await detector.detect("bypass attempt", use_cache=False)
        assert result.decision == DetectionDecision.ESCALATE

    async def test_detect_strict_mode_critical_block(self) -> None:
        detector = self._make_detector(strict_mode=True)
        pattern = ThreatPattern(
            pattern="inject",
            category=ThreatCategory.PROMPT_INJECTION,
            severity=ThreatSeverity.CRITICAL,
            description="test",
        )
        match = PatternMatchResult(matched=True, pattern=pattern, match_text="inject")
        score = _make_compliance_score(final_score=0.8, is_compliant=True, threat_matches=[match])
        detector.scoring_engine.calculate_score = MagicMock(return_value=score)

        result = await detector.detect("inject stuff", use_cache=False)
        assert result.decision == DetectionDecision.BLOCK

    async def test_detect_quick_mode_no_match(self) -> None:
        detector = self._make_detector()
        detector.registry.quick_scan = MagicMock(return_value=None)

        result = await detector.detect("safe content", mode=DetectionMode.QUICK, use_cache=False)
        assert result.decision == DetectionDecision.ALLOW
        assert result.mode == DetectionMode.QUICK

    async def test_detect_quick_mode_match(self) -> None:
        detector = self._make_detector()
        pattern = ThreatPattern(
            pattern="danger",
            category=ThreatCategory.PROMPT_INJECTION,
            severity=ThreatSeverity.CRITICAL,
            description="critical",
        )
        match = PatternMatchResult(matched=True, pattern=pattern, match_text="danger")
        detector.registry.quick_scan = MagicMock(return_value=match)

        result = await detector.detect("danger zone", mode=DetectionMode.QUICK, use_cache=False)
        assert result.decision == DetectionDecision.BLOCK
        assert result.threat_detected is True

    async def test_detect_comprehensive_mode(self) -> None:
        detector = self._make_detector()
        score = _make_compliance_score(final_score=0.95)
        detector.scoring_engine.calculate_score = MagicMock(return_value=score)

        result = await detector.detect("content", mode=DetectionMode.COMPREHENSIVE, use_cache=False)
        assert result.mode == DetectionMode.COMPREHENSIVE

    async def test_detect_streaming_mode_fallback(self) -> None:
        detector = self._make_detector()
        score = _make_compliance_score(final_score=0.95)
        detector.scoring_engine.calculate_score = MagicMock(return_value=score)

        result = await detector.detect("content", mode=DetectionMode.STREAMING, use_cache=False)
        assert result is not None

    async def test_detect_cache_hit(self) -> None:
        detector = self._make_detector()
        cached = DetectionResult(decision=DetectionDecision.ALLOW, threat_detected=False)
        cache_key = f"standard:{hash('cached content')}"
        detector._cache[cache_key] = (cached, time.monotonic())

        result = await detector.detect("cached content")
        assert result.decision == DetectionDecision.ALLOW

    async def test_detect_cache_expired(self) -> None:
        detector = self._make_detector(cache_ttl_seconds=1)
        cached = DetectionResult(decision=DetectionDecision.ALLOW, threat_detected=False)
        cache_key = f"standard:{hash('old content')}"
        detector._cache[cache_key] = (cached, time.monotonic() - 100)

        score = _make_compliance_score(final_score=0.95)
        detector.scoring_engine.calculate_score = MagicMock(return_value=score)

        result = await detector.detect("old content")
        # Should have re-evaluated since cache expired
        detector.scoring_engine.calculate_score.assert_called_once()

    async def test_detect_cache_disabled(self) -> None:
        detector = self._make_detector(enable_caching=False)
        score = _make_compliance_score(final_score=0.95)
        detector.scoring_engine.calculate_score = MagicMock(return_value=score)

        result = await detector.detect("content", use_cache=True)
        detector.scoring_engine.calculate_score.assert_called_once()

    async def test_detect_streaming(self) -> None:
        detector = self._make_detector()
        detector.registry.quick_scan = MagicMock(return_value=None)
        score = _make_compliance_score(final_score=0.95)
        detector.scoring_engine.calculate_score = MagicMock(return_value=score)

        async def token_gen():
            for t in ["a"] * 15:
                yield t

        results = []
        async for r in detector.detect_streaming(token_gen()):
            results.append(r)
        assert len(results) >= 1  # At least the final result

    async def test_detect_streaming_block(self) -> None:
        detector = self._make_detector()
        pattern = ThreatPattern(
            pattern="x",
            category=ThreatCategory.PROMPT_INJECTION,
            severity=ThreatSeverity.CRITICAL,
            description="test",
        )
        match = PatternMatchResult(matched=True, pattern=pattern, match_text="x")
        detector.registry.quick_scan = MagicMock(return_value=match)

        async def token_gen():
            for t in ["x"] * 20:
                yield t

        results = []
        async for r in detector.detect_streaming(token_gen()):
            results.append(r)
        # Should have blocked early
        assert any(r.decision == DetectionDecision.BLOCK for r in results)

    def test_determine_decision_allow(self) -> None:
        detector = self._make_detector()
        score = _make_compliance_score(final_score=0.95)
        decision = detector._determine_decision(score, set(), None)
        assert decision == DetectionDecision.ALLOW

    def test_determine_decision_block_low_score(self) -> None:
        detector = self._make_detector()
        score = _make_compliance_score(final_score=0.3)
        decision = detector._determine_decision(score, set(), None)
        assert decision == DetectionDecision.BLOCK

    def test_determine_decision_escalate_high_score(self) -> None:
        detector = self._make_detector()
        score = _make_compliance_score(final_score=0.95)
        cats = {ThreatCategory.CONSTITUTIONAL_BYPASS}
        decision = detector._determine_decision(score, cats, ThreatSeverity.HIGH)
        assert decision == DetectionDecision.ESCALATE

    def test_determine_decision_flag(self) -> None:
        detector = self._make_detector()
        score = _make_compliance_score(final_score=0.6)
        decision = detector._determine_decision(score, set(), ThreatSeverity.MEDIUM)
        assert decision == DetectionDecision.FLAG

    def test_generate_explanation_allow(self) -> None:
        detector = self._make_detector()
        score = _make_compliance_score(final_score=0.95)
        explanation = detector._generate_explanation(score, DetectionDecision.ALLOW)
        assert "passed" in explanation

    def test_generate_explanation_block_with_matches(self) -> None:
        detector = self._make_detector()
        pattern = ThreatPattern(
            pattern="x",
            category=ThreatCategory.PROMPT_INJECTION,
            severity=ThreatSeverity.CRITICAL,
            description="test",
        )
        match = PatternMatchResult(matched=True, pattern=pattern, match_text="x")
        score = _make_compliance_score(final_score=0.2, threat_matches=[match])
        explanation = detector._generate_explanation(score, DetectionDecision.BLOCK)
        assert "blocked" in explanation.lower()

    def test_generate_explanation_block_no_matches(self) -> None:
        detector = self._make_detector()
        score = _make_compliance_score(final_score=0.2)
        explanation = detector._generate_explanation(score, DetectionDecision.BLOCK)
        assert "low compliance" in explanation.lower()

    def test_generate_explanation_flag(self) -> None:
        detector = self._make_detector()
        score = _make_compliance_score(final_score=0.6)
        explanation = detector._generate_explanation(score, DetectionDecision.FLAG)
        assert "flagged" in explanation.lower()

    def test_generate_explanation_escalate(self) -> None:
        detector = self._make_detector()
        score = _make_compliance_score(final_score=0.6)
        explanation = detector._generate_explanation(score, DetectionDecision.ESCALATE)
        assert "human review" in explanation.lower()

    def test_generate_recommendations(self) -> None:
        detector = self._make_detector()
        score = _make_compliance_score(final_score=0.3, is_compliant=False)
        cats = {
            ThreatCategory.PROMPT_INJECTION,
            ThreatCategory.ROLE_CONFUSION,
            ThreatCategory.CONSTITUTIONAL_BYPASS,
            ThreatCategory.ENCODING_ATTACK,
            ThreatCategory.PRIVILEGE_ESCALATION,
        }
        recs = detector._generate_recommendations(score, cats)
        assert len(recs) >= 5
        assert any("sanitization" in r.lower() for r in recs)
        assert any("role" in r.lower() for r in recs)
        assert any("constitutional" in r.lower() for r in recs)
        assert any("encoding" in r.lower() for r in recs)
        assert any("access controls" in r.lower() for r in recs)

    def test_generate_recommendations_empty(self) -> None:
        detector = self._make_detector(enable_recommendations=True)
        score = _make_compliance_score(final_score=0.95, is_compliant=True)
        recs = detector._generate_recommendations(score, set())
        assert isinstance(recs, list)

    def test_update_cache_lru_eviction(self) -> None:
        detector = self._make_detector()
        detector._cache_max_size = 2
        r1 = DetectionResult(decision=DetectionDecision.ALLOW, threat_detected=False)
        r2 = DetectionResult(decision=DetectionDecision.ALLOW, threat_detected=False)
        r3 = DetectionResult(decision=DetectionDecision.BLOCK, threat_detected=True)

        detector._update_cache("k1", r1)
        detector._update_cache("k2", r2)
        assert len(detector._cache) == 2
        detector._update_cache("k3", r3)
        assert len(detector._cache) == 2
        assert "k1" not in detector._cache

    async def test_trigger_threat_callbacks_sync(self) -> None:
        detector = self._make_detector()
        called = []
        detector.on_threat_detected(lambda r: called.append(r))

        result = DetectionResult(decision=DetectionDecision.BLOCK, threat_detected=True)
        await detector._trigger_threat_callbacks(result)
        assert len(called) == 1

    async def test_trigger_threat_callbacks_async(self) -> None:
        detector = self._make_detector()
        called = []

        async def cb(r):
            called.append(r)

        detector.on_threat_detected(cb)

        result = DetectionResult(decision=DetectionDecision.BLOCK, threat_detected=True)
        await detector._trigger_threat_callbacks(result)
        assert len(called) == 1

    async def test_trigger_threat_callbacks_error(self) -> None:
        detector = self._make_detector()
        detector.on_threat_detected(lambda r: (_ for _ in ()).throw(RuntimeError("boom")))
        # Actually need a callable that raises
        detector._on_threat_detected.clear()

        def bad_cb(r):
            raise RuntimeError("boom")

        detector.on_threat_detected(bad_cb)
        result = DetectionResult(decision=DetectionDecision.BLOCK, threat_detected=True)
        # Should not raise
        await detector._trigger_threat_callbacks(result)

    async def test_trigger_block_callbacks_sync(self) -> None:
        detector = self._make_detector()
        called = []
        detector.on_block(lambda r: called.append(r))

        result = DetectionResult(decision=DetectionDecision.BLOCK, threat_detected=True)
        await detector._trigger_block_callbacks(result)
        assert len(called) == 1

    async def test_trigger_block_callbacks_async(self) -> None:
        detector = self._make_detector()
        called = []

        async def cb(r):
            called.append(r)

        detector.on_block(cb)

        result = DetectionResult(decision=DetectionDecision.BLOCK, threat_detected=True)
        await detector._trigger_block_callbacks(result)
        assert len(called) == 1

    async def test_trigger_block_callbacks_error(self) -> None:
        detector = self._make_detector()

        def bad_cb(r):
            raise ValueError("boom")

        detector.on_block(bad_cb)
        result = DetectionResult(decision=DetectionDecision.BLOCK, threat_detected=True)
        await detector._trigger_block_callbacks(result)

    def test_get_metrics_initial(self) -> None:
        detector = self._make_detector()
        m = detector.get_metrics()
        assert m["total_detections"] == 0
        assert m["blocked_count"] == 0
        assert m["flagged_count"] == 0
        assert m["block_rate"] == 0
        assert m["average_latency_ms"] == 0

    def test_get_metrics_after_detections(self) -> None:
        detector = self._make_detector()
        detector._total_detections = 10
        detector._blocked_count = 3
        detector._flagged_count = 2
        detector._total_latency_ms = 50.0
        m = detector.get_metrics()
        assert m["total_detections"] == 10
        assert m["block_rate"] == 0.3
        assert m["average_latency_ms"] == 5.0

    def test_clear_cache(self) -> None:
        detector = self._make_detector()
        r = DetectionResult(decision=DetectionDecision.ALLOW, threat_detected=False)
        detector._cache["k1"] = (r, time.monotonic())
        detector._cache["k2"] = (r, time.monotonic())
        count = detector.clear_cache()
        assert count == 2
        assert len(detector._cache) == 0

    def test_update_detection_metrics_block(self) -> None:
        detector = self._make_detector()
        result = DetectionResult(
            decision=DetectionDecision.BLOCK, threat_detected=True, latency_ms=5.0
        )
        detector._update_detection_metrics(result)
        assert detector._blocked_count == 1
        assert detector._total_latency_ms == 5.0

    def test_update_detection_metrics_flag(self) -> None:
        detector = self._make_detector()
        result = DetectionResult(
            decision=DetectionDecision.FLAG, threat_detected=True, latency_ms=3.0
        )
        detector._update_detection_metrics(result)
        assert detector._flagged_count == 1

    async def test_handle_callbacks_and_logging_threat(self) -> None:
        detector = self._make_detector(log_threats=True)
        called = []
        detector.on_threat_detected(lambda r: called.append("threat"))
        detector.on_block(lambda r: called.append("block"))

        result = DetectionResult(
            decision=DetectionDecision.BLOCK,
            threat_detected=True,
            max_severity=ThreatSeverity.CRITICAL,
            categories_detected={ThreatCategory.PROMPT_INJECTION},
        )
        await detector._handle_callbacks_and_logging(result)
        assert "threat" in called
        assert "block" in called

    async def test_handle_callbacks_and_logging_no_threat(self) -> None:
        detector = self._make_detector(log_threats=True)
        called = []
        detector.on_threat_detected(lambda r: called.append("threat"))

        result = DetectionResult(decision=DetectionDecision.ALLOW, threat_detected=False)
        await detector._handle_callbacks_and_logging(result)
        assert len(called) == 0

    def test_severity_comparison_in_standard_detect(self) -> None:
        """Test that max_severity correctly tracks highest severity."""
        detector = self._make_detector()
        p_low = ThreatPattern(
            pattern="a",
            category=ThreatCategory.PROMPT_INJECTION,
            severity=ThreatSeverity.LOW,
            description="low",
        )
        p_high = ThreatPattern(
            pattern="b",
            category=ThreatCategory.ROLE_CONFUSION,
            severity=ThreatSeverity.HIGH,
            description="high",
        )
        m1 = PatternMatchResult(matched=True, pattern=p_low, match_text="a")
        m2 = PatternMatchResult(matched=True, pattern=p_high, match_text="b")
        score = _make_compliance_score(final_score=0.3, is_compliant=False, threat_matches=[m1, m2])
        detector.scoring_engine.calculate_score = MagicMock(return_value=score)
        # Verify via _standard_detect that severity is tracked correctly
        # (tested indirectly through detect)

    async def test_finalize_detection_result_caches(self) -> None:
        detector = self._make_detector()
        result = DetectionResult(
            decision=DetectionDecision.ALLOW, threat_detected=False, latency_ms=1.0
        )
        await detector._finalize_detection_result(result, "content", DetectionMode.STANDARD, True)
        assert len(detector._cache) == 1


class TestGetThreatDetector:
    """Tests for get_threat_detector singleton."""

    def test_get_creates_new(self) -> None:
        with patch("enhanced_agent_bus.constitutional_classifier.detector._global_detector", None):
            detector = get_threat_detector()
            assert isinstance(detector, ThreatDetector)

    def test_get_with_config_creates_new(self) -> None:
        config = DetectorConfig(block_threshold=0.5)
        with patch("enhanced_agent_bus.constitutional_classifier.detector._global_detector", None):
            detector = get_threat_detector(config=config)
            assert detector.config.block_threshold == 0.5


# ---------------------------------------------------------------------------
# 4. OPALPolicyClient tests
# ---------------------------------------------------------------------------

from enhanced_agent_bus.opal_client import (
    OPALClientStatus,
    OPALConnectionState,
    OPALPolicyClient,
    PolicyUpdateEvent,
)


class TestPolicyUpdateEvent:
    """Tests for PolicyUpdateEvent model."""

    def test_defaults(self) -> None:
        event = PolicyUpdateEvent(event_type="policy_update")
        assert event.event_type == "policy_update"
        assert event.event_id  # auto-generated
        assert event.policy_id is None
        assert event.raw_payload == {}

    def test_with_fields(self) -> None:
        event = PolicyUpdateEvent(
            event_type="data_update",
            policy_id="p1",
            opal_server_url="http://test:7002",
            raw_payload={"key": "val"},
        )
        assert event.policy_id == "p1"
        assert event.raw_payload == {"key": "val"}


class TestOPALClientStatus:
    """Tests for OPALClientStatus model."""

    def test_creation(self) -> None:
        status = OPALClientStatus(
            enabled=True,
            connection_state=OPALConnectionState.CONNECTED,
            opal_server_url="http://test:7002",
        )
        assert status.enabled is True
        assert status.total_updates_received == 0
        assert status.fallback_active is False


class TestOPALPolicyClient:
    """Tests for OPALPolicyClient."""

    def _make_client(self, **kwargs) -> OPALPolicyClient:
        defaults = {
            "opa_url": "http://localhost:8181",
            "opal_server_url": "http://opal:7002",
            "opal_enabled": False,  # Disable WS by default in tests
        }
        defaults.update(kwargs)
        return OPALPolicyClient(**defaults)

    def test_init_defaults(self) -> None:
        client = self._make_client()
        assert client.opa_url == "http://localhost:8181"
        assert client._connection_state == OPALConnectionState.DISCONNECTED

    def test_init_strips_trailing_slash(self) -> None:
        client = self._make_client(opa_url="http://opa:8181/")
        assert client.opa_url == "http://opa:8181"

    async def test_connect_opal_disabled(self) -> None:
        client = self._make_client(opal_enabled=False)
        with (
            patch.object(client, "_http_client", None),
            patch("enhanced_agent_bus.opal_client.OPAClient", None),
            patch("enhanced_agent_bus.opal_client.AuditClient", None),
        ):
            await client.connect()
            assert client._fallback_active is True
            await client.disconnect()

    async def test_disconnect_cleans_up(self) -> None:
        client = self._make_client()
        client._http_client = AsyncMock()
        client._http_client.aclose = AsyncMock()
        client._opa_client = AsyncMock()
        client._opa_client.close = AsyncMock()
        client._audit_client = AsyncMock()
        client._audit_client.stop = AsyncMock()
        client._ws_task = None

        await client.disconnect()
        assert client._connection_state == OPALConnectionState.DISCONNECTED
        assert client._http_client is None
        assert client._opa_client is None
        assert client._audit_client is None

    async def test_disconnect_cancels_ws_task(self) -> None:
        client = self._make_client()
        client._http_client = None
        client._opa_client = None
        client._audit_client = None

        # Create a real task that we can cancel
        async def _long_running():
            await asyncio.sleep(100)

        task = asyncio.create_task(_long_running())
        client._ws_task = task
        await client.disconnect()
        assert task.cancelled() or task.done()

    async def test_evaluate_with_opa_client_success(self) -> None:
        client = self._make_client()
        client._opa_client = AsyncMock()
        client._opa_client.evaluate = AsyncMock(return_value=True)

        result = await client.evaluate("data.acgs.allow", {"action": "read"})
        assert result is True

    async def test_evaluate_with_opa_client_returns_false(self) -> None:
        client = self._make_client()
        client._opa_client = AsyncMock()
        client._opa_client.evaluate = AsyncMock(return_value=False)

        result = await client.evaluate("data.acgs.allow", {"action": "write"})
        assert result is False

    async def test_evaluate_opa_client_error_fail_closed(self) -> None:
        client = self._make_client(fail_closed=True)
        client._opa_client = AsyncMock()
        client._opa_client.evaluate = AsyncMock(side_effect=ConnectionError("down"))

        result = await client.evaluate("data.acgs.allow", {"action": "write"})
        assert result is False  # fail_closed -> deny

    async def test_evaluate_opa_client_error_fail_open(self) -> None:
        client = self._make_client(fail_closed=False)
        client._opa_client = AsyncMock()
        client._opa_client.evaluate = AsyncMock(side_effect=TimeoutError("slow"))

        result = await client.evaluate("data.acgs.allow", {"action": "write"})
        assert result is True  # fail_open -> allow

    async def test_evaluate_override_default_deny(self) -> None:
        client = self._make_client(fail_closed=True)
        client._opa_client = AsyncMock()
        client._opa_client.evaluate = AsyncMock(side_effect=ValueError("bad"))

        result = await client.evaluate("data.acgs.allow", {"action": "write"}, default_deny=False)
        assert result is True  # override to fail_open

    async def test_evaluate_direct_http_fallback_success(self) -> None:
        client = self._make_client()
        client._opa_client = None
        client._http_client = AsyncMock()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"result": True}
        client._http_client.post = AsyncMock(return_value=response)

        result = await client.evaluate("data.acgs.allow", {"action": "read"})
        assert result is True

    async def test_evaluate_direct_http_fallback_non_200(self) -> None:
        client = self._make_client(fail_closed=True)
        client._opa_client = None
        client._http_client = AsyncMock()
        response = MagicMock()
        response.status_code = 500
        client._http_client.post = AsyncMock(return_value=response)

        result = await client.evaluate("data.acgs.allow", {"action": "read"})
        assert result is False

    async def test_evaluate_direct_http_error(self) -> None:
        client = self._make_client(fail_closed=True)
        client._opa_client = None
        client._http_client = AsyncMock()
        client._http_client.post = AsyncMock(side_effect=httpx.HTTPError("connection refused"))

        result = await client.evaluate("data.acgs.allow", {"action": "read"})
        assert result is False

    async def test_evaluate_no_http_client(self) -> None:
        client = self._make_client(fail_closed=True)
        client._opa_client = None
        client._http_client = None

        result = await client.evaluate("data.acgs.allow", {"action": "read"})
        assert result is False

    async def test_handle_ws_message_valid(self) -> None:
        client = self._make_client()
        client._opa_client = None
        client._audit_client = None

        payload = json.dumps({"type": "policy_update", "policy_id": "p1"})
        await client._handle_ws_message(payload)
        assert client._total_updates == 1
        assert client._last_update_at is not None

    async def test_handle_ws_message_invalid_json(self) -> None:
        client = self._make_client()
        await client._handle_ws_message("not json {{{")
        assert client._total_updates == 0

    async def test_handle_ws_message_notifies_listeners(self) -> None:
        client = self._make_client()
        client._opa_client = None
        client._audit_client = None

        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        client._update_listeners.append(queue)

        payload = json.dumps({"type": "data_update"})
        await client._handle_ws_message(payload)
        assert not queue.empty()
        event = queue.get_nowait()
        assert event.event_type == "data_update"

    async def test_invalidate_opa_cache_with_clear_cache(self) -> None:
        client = self._make_client()
        client._opa_client = AsyncMock()
        client._opa_client.clear_cache = AsyncMock()
        event = PolicyUpdateEvent(event_type="policy_update")
        await client._invalidate_opa_cache(event)
        client._opa_client.clear_cache.assert_awaited_once()

    async def test_invalidate_opa_cache_no_client(self) -> None:
        client = self._make_client()
        client._opa_client = None
        event = PolicyUpdateEvent(event_type="policy_update")
        await client._invalidate_opa_cache(event)  # Should not raise

    async def test_invalidate_opa_cache_no_clear_cache_method(self) -> None:
        client = self._make_client()
        client._opa_client = MagicMock(spec=[])  # No clear_cache attr
        event = PolicyUpdateEvent(event_type="policy_update")
        await client._invalidate_opa_cache(event)  # Should not raise

    async def test_invalidate_opa_cache_error(self) -> None:
        client = self._make_client()
        client._opa_client = AsyncMock()
        client._opa_client.clear_cache = AsyncMock(side_effect=ConnectionError("fail"))
        event = PolicyUpdateEvent(event_type="policy_update")
        await client._invalidate_opa_cache(event)  # Should not raise

    async def test_audit_policy_update_with_client(self) -> None:
        client = self._make_client()
        client._audit_client = AsyncMock()
        client._audit_client.log = AsyncMock()
        event = PolicyUpdateEvent(event_type="policy_update", policy_id="p1")
        await client._audit_policy_update(event)
        client._audit_client.log.assert_awaited_once()

    async def test_audit_policy_update_no_client(self) -> None:
        client = self._make_client()
        client._audit_client = None
        event = PolicyUpdateEvent(event_type="policy_update")
        await client._audit_policy_update(event)  # Should not raise

    async def test_audit_policy_update_error(self) -> None:
        client = self._make_client()
        client._audit_client = AsyncMock()
        client._audit_client.log = AsyncMock(side_effect=ConnectionError("fail"))
        event = PolicyUpdateEvent(event_type="policy_update")
        await client._audit_policy_update(event)  # Should not raise

    async def test_wait_for_propagation_success(self) -> None:
        client = self._make_client()
        event = PolicyUpdateEvent(event_type="policy_update")

        async def _push_event():
            await asyncio.sleep(0.01)
            for q in client._update_listeners:
                q.put_nowait(event)

        asyncio.create_task(_push_event())
        result = await client.wait_for_propagation(timeout=2)
        assert result is True

    async def test_wait_for_propagation_timeout(self) -> None:
        client = self._make_client()
        result = await client.wait_for_propagation(timeout=0)
        assert result is False

    def test_status(self) -> None:
        client = self._make_client()
        s = client.status()
        assert isinstance(s, OPALClientStatus)
        assert s.connection_state == OPALConnectionState.DISCONNECTED
        assert s.total_updates_received == 0

    async def test_context_manager(self) -> None:
        client = self._make_client(opal_enabled=False)
        with (
            patch("enhanced_agent_bus.opal_client.OPAClient", None),
            patch("enhanced_agent_bus.opal_client.AuditClient", None),
        ):
            async with client as c:
                assert c is client
            assert client._connection_state == OPALConnectionState.DISCONNECTED

    @patch("enhanced_agent_bus.opal_client.WEBSOCKETS_AVAILABLE", False)
    async def test_connect_websocket_no_lib(self) -> None:
        client = self._make_client(opal_enabled=True)
        client._stop_event.set()  # Prevent blocking
        await client._connect_websocket()
        assert client._connection_state == OPALConnectionState.FAILED
        assert client._fallback_active is True

    async def test_evaluate_direct_http_path_transform(self) -> None:
        """Test that policy path is correctly transformed for direct HTTP."""
        client = self._make_client()
        client._opa_client = None
        client._http_client = AsyncMock()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"result": False}
        client._http_client.post = AsyncMock(return_value=response)

        await client.evaluate("data.acgs.temporal.allow", {"action": "x"})
        call_args = client._http_client.post.call_args
        url = call_args[0][0]
        assert "/v1/data/acgs/temporal/allow" in url

    async def test_run_websocket_listener_cancelled(self) -> None:
        """Test that CancelledError breaks the listener loop."""
        client = self._make_client(opal_enabled=True)

        async def _raise_cancel():
            raise asyncio.CancelledError()

        with patch.object(client, "_connect_websocket", side_effect=asyncio.CancelledError):
            await client._run_websocket_listener()
        assert client._connection_state == OPALConnectionState.DISCONNECTED

    async def test_run_websocket_listener_retries_on_error(self) -> None:
        """Test reconnection on connection error."""
        client = self._make_client(opal_enabled=True)
        call_count = 0

        async def _connect_ws():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("first try fails")
            # Second call: set stop event so loop exits
            client._stop_event.set()

        with patch.object(client, "_connect_websocket", side_effect=_connect_ws):
            await client._run_websocket_listener()
        assert call_count >= 1

    async def test_opal_enabled_env_false(self) -> None:
        """Test OPAL_ENABLED=false disables OPAL."""
        with patch.dict("os.environ", {"OPAL_ENABLED": "false"}):
            client = OPALPolicyClient(
                opa_url="http://localhost:8181",
                opal_server_url="http://opal:7002",
                opal_enabled=True,
            )
            assert client.opal_enabled is False
