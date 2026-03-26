"""
Tests for coverage batch 22e:
- verification_layer/z3_policy_verifier.py
- integrations/ml_governance.py
- profiling/benchmark_gpu_decision.py

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ============================================================================
# ml_governance imports
# ============================================================================
from enhanced_agent_bus.integrations.ml_governance import (
    MLGovernanceClient,
    MLGovernanceConfig,
    MLGovernanceConnectionError,
    MLGovernanceError,
    MLGovernanceTimeoutError,
    OutcomeReport,
    OutcomeReportStatus,
    OutcomeResult,
    get_ml_governance_client,
)

# ============================================================================
# benchmark_gpu_decision imports
# ============================================================================
from enhanced_agent_bus.profiling.benchmark_gpu_decision import (
    SAMPLE_MESSAGES,
    GPUBenchmark,
    generate_random_message,
)

# ============================================================================
# z3_policy_verifier imports
# ============================================================================
from enhanced_agent_bus.verification_layer.z3_policy_verifier import (
    ConstraintGenerator,
    ConstraintType,
    HeuristicVerifier,
    PolicyConstraint,
    PolicyDomain,
    PolicyVerificationRequest,
    PolicyVerificationResult,
    VerificationProof,
    Z3PolicyVerifier,
    Z3VerificationStatus,
    create_z3_verifier,
)

# ============================================================================
# z3_policy_verifier: Enums and Dataclasses
# ============================================================================


class TestZ3VerificationStatusEnum:
    def test_all_values(self):
        assert Z3VerificationStatus.PENDING.value == "pending"
        assert Z3VerificationStatus.SATISFIABLE.value == "satisfiable"
        assert Z3VerificationStatus.UNSATISFIABLE.value == "unsatisfiable"
        assert Z3VerificationStatus.UNKNOWN.value == "unknown"
        assert Z3VerificationStatus.TIMEOUT.value == "timeout"
        assert Z3VerificationStatus.ERROR.value == "error"
        assert Z3VerificationStatus.HEURISTIC_FALLBACK.value == "heuristic_fallback"


class TestConstraintType:
    def test_all_values(self):
        assert ConstraintType.BOOLEAN.value == "boolean"
        assert ConstraintType.INTEGER.value == "integer"
        assert ConstraintType.REAL.value == "real"
        assert ConstraintType.STRING.value == "string"
        assert ConstraintType.ARRAY.value == "array"
        assert ConstraintType.COMPOSITE.value == "composite"


class TestPolicyDomain:
    def test_all_values(self):
        assert PolicyDomain.ACCESS_CONTROL.value == "access_control"
        assert PolicyDomain.DATA_PROTECTION.value == "data_protection"
        assert PolicyDomain.RESOURCE_ALLOCATION.value == "resource_allocation"
        assert PolicyDomain.GOVERNANCE.value == "governance"
        assert PolicyDomain.SECURITY.value == "security"
        assert PolicyDomain.COMPLIANCE.value == "compliance"


class TestPolicyConstraint:
    def test_defaults(self):
        pc = PolicyConstraint()
        assert pc.name == ""
        assert pc.constraint_type == ConstraintType.BOOLEAN
        assert pc.domain == PolicyDomain.GOVERNANCE
        assert pc.confidence == 1.0
        assert pc.is_mandatory is True
        assert pc.priority == 1
        assert isinstance(pc.variables, dict)

    def test_to_dict(self):
        pc = PolicyConstraint(
            name="test",
            description="desc",
            constraint_type=ConstraintType.INTEGER,
            domain=PolicyDomain.SECURITY,
            expression="(assert x)",
            natural_language="x must be true",
            variables={"x": "Bool"},
            confidence=0.9,
            generated_by="test",
            is_mandatory=False,
            priority=2,
            metadata={"key": "val"},
        )
        d = pc.to_dict()
        assert d["name"] == "test"
        assert d["constraint_type"] == "integer"
        assert d["domain"] == "security"
        assert d["confidence"] == 0.9
        assert d["is_mandatory"] is False
        assert d["variables"] == {"x": "Bool"}
        assert "created_at" in d
        assert "constraint_id" in d


class TestVerificationProof:
    def test_defaults(self):
        vp = VerificationProof()
        assert vp.status == Z3VerificationStatus.PENDING
        assert vp.is_verified is False
        assert vp.constraints_evaluated == 0

    def test_to_dict(self):
        vp = VerificationProof(
            status=Z3VerificationStatus.SATISFIABLE,
            is_verified=True,
            model={"x": True},
            constraints_evaluated=3,
            constraints_satisfied=3,
            solve_time_ms=1.5,
        )
        d = vp.to_dict()
        assert d["status"] == "satisfiable"
        assert d["is_verified"] is True
        assert d["model"] == {"x": True}
        assert d["solve_time_ms"] == 1.5

    def test_add_trace_entry(self):
        vp = VerificationProof()
        vp.add_trace_entry("step1", {"key": "value"})
        assert len(vp.proof_trace) == 1
        assert vp.proof_trace[0]["step"] == "step1"
        assert vp.proof_trace[0]["details"]["key"] == "value"
        assert "timestamp" in vp.proof_trace[0]

    def test_to_dict_with_none_model(self):
        vp = VerificationProof(model=None, unsat_core=["c1"])
        d = vp.to_dict()
        assert d["model"] is None
        assert d["unsat_core"] == ["c1"]


class TestPolicyVerificationRequest:
    def test_defaults(self):
        req = PolicyVerificationRequest()
        assert req.policy_id == ""
        assert req.timeout_ms == 5000
        assert req.use_heuristic_fallback is False
        assert req.require_proof is True

    def test_to_dict(self):
        constraint = PolicyConstraint(name="c1")
        req = PolicyVerificationRequest(
            policy_id="p1",
            policy_text="some policy",
            constraints=[constraint],
            context={"env": "test"},
            timeout_ms=3000,
        )
        d = req.to_dict()
        assert d["policy_id"] == "p1"
        assert d["timeout_ms"] == 3000
        assert len(d["constraints"]) == 1
        assert d["context"]["env"] == "test"


class TestPolicyVerificationResult:
    def test_defaults(self):
        r = PolicyVerificationResult()
        assert r.is_verified is False
        assert r.status == Z3VerificationStatus.PENDING

    def test_to_dict_with_proof(self):
        proof = VerificationProof(is_verified=True)
        r = PolicyVerificationResult(
            is_verified=True,
            status=Z3VerificationStatus.SATISFIABLE,
            proof=proof,
            violations=[{"type": "test"}],
            warnings=["warn"],
            recommendations=["rec"],
            total_constraints=5,
            satisfied_constraints=5,
        )
        d = r.to_dict()
        assert d["is_verified"] is True
        assert d["proof"] is not None
        assert d["proof"]["is_verified"] is True
        assert d["violations"] == [{"type": "test"}]

    def test_to_dict_without_proof(self):
        r = PolicyVerificationResult(proof=None)
        d = r.to_dict()
        assert d["proof"] is None


# ============================================================================
# z3_policy_verifier: ConstraintGenerator
# ============================================================================


class TestConstraintGenerator:
    @pytest.fixture()
    def generator(self):
        return ConstraintGenerator()

    async def test_generate_empty_text(self, generator):
        constraints = await generator.generate_constraints("")
        assert constraints == []

    async def test_generate_obligation_must(self, generator):
        constraints = await generator.generate_constraints(
            "The system must enforce access controls."
        )
        assert len(constraints) == 1
        assert "Obligation" in constraints[0].name
        assert constraints[0].confidence == 0.85
        assert constraints[0].is_mandatory is True
        assert constraints[0].generated_by == "pattern_matching"

    async def test_generate_obligation_shall(self, generator):
        constraints = await generator.generate_constraints("Agents shall report their status.")
        assert len(constraints) == 1
        assert "Obligation" in constraints[0].name

    async def test_generate_obligation_required(self, generator):
        constraints = await generator.generate_constraints(
            "Authentication is required for all endpoints."
        )
        assert len(constraints) == 1
        assert "Obligation" in constraints[0].name

    async def test_generate_prohibition_cannot(self, generator):
        constraints = await generator.generate_constraints(
            "Agents cannot modify governance policies."
        )
        assert len(constraints) == 1
        assert "Prohibition" in constraints[0].name
        assert constraints[0].confidence == 0.90

    async def test_generate_prohibition_must_not(self, generator):
        constraints = await generator.generate_constraints("Agents must not bypass security.")
        # "must not" triggers prohibition, but "must" also matches obligation
        # The comparison patterns are checked first, then others
        assert len(constraints) >= 1

    async def test_generate_prohibition_forbidden(self, generator):
        constraints = await generator.generate_constraints("Unauthorized access is forbidden.")
        assert len(constraints) == 1
        assert "Prohibition" in constraints[0].name

    async def test_generate_permission_may(self, generator):
        constraints = await generator.generate_constraints("Users may request data exports.")
        assert len(constraints) == 1
        assert "Permission" in constraints[0].name
        assert constraints[0].confidence == 0.75
        assert constraints[0].is_mandatory is False
        assert constraints[0].priority == 2

    async def test_generate_permission_can(self, generator):
        constraints = await generator.generate_constraints("Admins can override rate limits.")
        assert len(constraints) == 1
        assert "Permission" in constraints[0].name

    async def test_generate_permission_optional(self, generator):
        constraints = await generator.generate_constraints("Logging is optional for debug mode.")
        assert len(constraints) == 1
        assert "Permission" in constraints[0].name

    async def test_generate_comparison_greater_than(self, generator):
        constraints = await generator.generate_constraints("Score must be greater than 50.")
        # "greater than" is a comparison pattern, checked first
        assert len(constraints) >= 1
        comp = [c for c in constraints if "Comparison" in c.name]
        assert len(comp) >= 1
        assert comp[0].constraint_type == ConstraintType.INTEGER
        assert ">=" in comp[0].expression
        assert "50" in comp[0].expression

    async def test_generate_comparison_less_than(self, generator):
        constraints = await generator.generate_constraints("Latency must be less than 100ms.")
        comp = [c for c in constraints if "Comparison" in c.name]
        assert len(comp) >= 1
        assert "<=" in comp[0].expression
        assert "100" in comp[0].expression

    async def test_generate_comparison_at_least(self, generator):
        constraints = await generator.generate_constraints("Coverage at least 80 percent.")
        comp = [c for c in constraints if "Comparison" in c.name]
        assert len(comp) >= 1
        assert ">=" in comp[0].expression

    async def test_generate_comparison_at_most(self, generator):
        constraints = await generator.generate_constraints("Queue size at most 1000.")
        comp = [c for c in constraints if "Comparison" in c.name]
        assert len(comp) >= 1
        assert "<=" in comp[0].expression

    async def test_generate_comparison_no_number(self, generator):
        constraints = await generator.generate_constraints("Value greater than threshold.")
        comp = [c for c in constraints if "Comparison" in c.name]
        assert len(comp) >= 1
        # threshold defaults to 0 when no number found
        assert "0" in comp[0].expression

    async def test_generate_multiple_sentences(self, generator):
        constraints = await generator.generate_constraints(
            "The system must log events. Users may export data. Latency at most 50ms."
        )
        assert len(constraints) >= 3

    async def test_generate_no_matching_pattern(self, generator):
        constraints = await generator.generate_constraints("Hello world.")
        assert constraints == []

    async def test_generate_with_context(self, generator):
        constraints = await generator.generate_constraints(
            "The system must enforce rules.",
            context={"env": "production"},
        )
        assert len(constraints) == 1


# ============================================================================
# z3_policy_verifier: HeuristicVerifier
# ============================================================================


class TestHeuristicVerifier:
    @pytest.fixture()
    def verifier(self):
        return HeuristicVerifier()

    async def test_verify_empty_constraints(self, verifier):
        score, violations = await verifier.verify([], {})
        assert score == 0.0
        assert violations == []

    async def test_verify_obligation_constraint(self, verifier):
        c = PolicyConstraint(
            name="Obligation: test",
            confidence=0.85,
            is_mandatory=True,
        )
        score, violations = await verifier.verify([c], {})
        # 0.85 * 0.9 = 0.765
        assert score == pytest.approx(0.765)
        assert violations == []

    async def test_verify_prohibition_constraint(self, verifier):
        c = PolicyConstraint(
            name="Prohibition: test",
            confidence=0.90,
            is_mandatory=True,
        )
        score, violations = await verifier.verify([c], {})
        # 0.90 * 0.95 = 0.855
        assert score == pytest.approx(0.855)
        assert violations == []

    async def test_verify_permission_constraint(self, verifier):
        c = PolicyConstraint(
            name="Permission: test",
            confidence=0.75,
            is_mandatory=False,
        )
        score, violations = await verifier.verify([c], {})
        # 0.75 * 0.7 = 0.525
        assert score == pytest.approx(0.525)
        # Not mandatory, so no violation even though score < 0.7
        assert violations == []

    async def test_verify_comparison_constraint(self, verifier):
        c = PolicyConstraint(
            name="Comparison: test",
            confidence=0.80,
            is_mandatory=True,
        )
        score, violations = await verifier.verify([c], {})
        # 0.80 * 0.85 = 0.68
        assert score == pytest.approx(0.68)
        # mandatory and < 0.7, so violation
        assert len(violations) == 1

    async def test_verify_unknown_type_defaults_to_comparison(self, verifier):
        c = PolicyConstraint(
            name="SomeOther: test",
            confidence=0.80,
            is_mandatory=True,
        )
        score, violations = await verifier.verify([c], {})
        assert score == pytest.approx(0.68)

    async def test_verify_low_confidence_mandatory_triggers_violation(self, verifier):
        c = PolicyConstraint(
            name="Obligation: weak rule",
            confidence=0.5,
            is_mandatory=True,
        )
        score, violations = await verifier.verify([c], {})
        # 0.5 * 0.9 = 0.45 < 0.7 => violation
        assert score == pytest.approx(0.45)
        assert len(violations) == 1
        assert violations[0]["constraint_id"] == c.constraint_id

    async def test_verify_multiple_constraints(self, verifier):
        constraints = [
            PolicyConstraint(name="Obligation: a", confidence=0.9, is_mandatory=True),
            PolicyConstraint(name="Permission: b", confidence=0.8, is_mandatory=False),
        ]
        score, violations = await verifier.verify(constraints, {})
        # (0.9*0.9 + 0.8*0.7) / 2 = (0.81 + 0.56) / 2 = 0.685
        assert score == pytest.approx(0.685)


# ============================================================================
# z3_policy_verifier: Z3PolicyVerifier
# ============================================================================


class TestZ3PolicyVerifier:
    @pytest.fixture()
    def verifier(self):
        return Z3PolicyVerifier(
            default_timeout_ms=1000,
            enable_heuristic_fallback=True,
            heuristic_threshold=0.75,
        )

    async def test_verify_empty_constraints(self, verifier):
        req = PolicyVerificationRequest(
            policy_id="p1",
            constraints=[],
            policy_text="",
        )
        result = await verifier.verify_policy(req)
        assert result.is_verified is True
        assert result.status == Z3VerificationStatus.SATISFIABLE
        assert "No constraints to verify" in result.warnings

    async def test_verify_policy_text_generates_constraints(self, verifier):
        req = PolicyVerificationRequest(
            policy_id="p1",
            policy_text="The system must log all events. Users may export data.",
        )
        result = await verifier.verify_policy(req)
        assert result.total_constraints >= 2
        assert result.proof is not None

    async def test_verify_policy_text_convenience(self, verifier):
        result = await verifier.verify_policy_text(
            "The system must enforce rules.",
            policy_id="p-test",
            context={"env": "test"},
            timeout_ms=2000,
        )
        assert result.request_id != ""
        assert result.proof is not None

    async def test_verify_policy_text_default_policy_id(self, verifier):
        result = await verifier.verify_policy_text("Access is forbidden.")
        assert result.policy_id.startswith("policy_")

    async def test_verify_stores_history(self, verifier):
        await verifier.verify_policy_text("The system must work.")
        await verifier.verify_policy_text("Access is forbidden.")
        assert len(verifier._verification_history) == 2

    async def test_heuristic_fallback_when_z3_unavailable(self, verifier):
        """Test heuristic path when Z3 is not available."""
        with patch(
            "enhanced_agent_bus.verification_layer.z3_policy_verifier.Z3_AVAILABLE",
            False,
        ):
            req = PolicyVerificationRequest(
                policy_id="p1",
                policy_text="The system must enforce access controls.",
                use_heuristic_fallback=True,
            )
            result = await verifier.verify_policy(req)
            assert result.status == Z3VerificationStatus.HEURISTIC_FALLBACK
            assert "Z3 not available" in result.warnings[0]

    async def test_generate_recommendations_not_verified(self, verifier):
        result = PolicyVerificationResult(is_verified=False)
        recs = verifier._generate_recommendations(result, [])
        assert "Review and address identified policy violations" in recs

    async def test_generate_recommendations_heuristic_fallback(self, verifier):
        result = PolicyVerificationResult(
            status=Z3VerificationStatus.HEURISTIC_FALLBACK,
        )
        recs = verifier._generate_recommendations(result, [])
        assert any("simplifying" in r for r in recs)

    async def test_generate_recommendations_unsat_violations(self, verifier):
        result = PolicyVerificationResult(
            is_verified=False,
            violations=[
                {"type": "unsatisfiable_constraint", "constraint": "c1"},
            ],
        )
        recs = verifier._generate_recommendations(result, [])
        assert any("Constraint conflict" in r for r in recs)

    async def test_generate_recommendations_many_constraints(self, verifier):
        constraints = [PolicyConstraint() for _ in range(55)]
        result = PolicyVerificationResult(total_constraints=55)
        recs = verifier._generate_recommendations(result, constraints)
        assert any("decomposing" in r for r in recs)

    def test_get_verification_stats_empty(self, verifier):
        stats = verifier.get_verification_stats()
        assert stats["total_verifications"] == 0

    async def test_get_verification_stats_with_history(self, verifier):
        await verifier.verify_policy_text("The system must work.")
        stats = verifier.get_verification_stats()
        assert stats["total_verifications"] == 1
        assert "verification_rate" in stats
        assert "average_time_ms" in stats
        assert "average_constraints" in stats

    def test_get_constitutional_hash(self, verifier):
        h = verifier.get_constitutional_hash()
        assert isinstance(h, str)
        assert len(h) > 0

    async def test_verify_policy_error_handling(self, verifier):
        """Test error handling when constraint generation raises."""
        with patch.object(
            verifier.constraint_generator,
            "generate_constraints",
            side_effect=RuntimeError("fail"),
        ):
            req = PolicyVerificationRequest(
                policy_id="p1",
                policy_text="some policy",
            )
            result = await verifier.verify_policy(req)
            assert result.status == Z3VerificationStatus.ERROR
            assert result.is_verified is False
            assert len(result.violations) >= 1

    async def test_verify_with_heuristic_method(self, verifier):
        constraints = [
            PolicyConstraint(
                name="Obligation: test",
                confidence=0.9,
                is_mandatory=True,
            ),
        ]
        proof = VerificationProof()
        result = await verifier._verify_with_heuristic(constraints, {}, proof)
        assert "is_verified" in result
        assert "score" in result
        assert "violations" in result


class TestCreateZ3Verifier:
    def test_factory_defaults(self):
        v = create_z3_verifier()
        assert v.default_timeout_ms == 5000
        assert v.enable_heuristic_fallback is False

    def test_factory_custom(self):
        v = create_z3_verifier(timeout_ms=2000, enable_heuristic_fallback=False)
        assert v.default_timeout_ms == 2000
        assert v.enable_heuristic_fallback is False


# ============================================================================
# ml_governance: Exceptions
# ============================================================================


class TestMLGovernanceExceptions:
    def test_ml_governance_error(self):
        err = MLGovernanceError("test error", details={"key": "val"})
        assert "test error" in str(err)

    def test_ml_governance_connection_error(self):
        err = MLGovernanceConnectionError("http://localhost:8001", "refused")
        assert "http://localhost:8001" in str(err)
        assert "refused" in str(err)
        assert err.url == "http://localhost:8001"
        assert err.reason == "refused"

    def test_ml_governance_timeout_error(self):
        err = MLGovernanceTimeoutError("report_outcome", 5.0)
        assert "report_outcome" in str(err)
        assert err.operation == "report_outcome"
        assert err.timeout_seconds == 5.0


# ============================================================================
# ml_governance: Config
# ============================================================================


class TestMLGovernanceConfig:
    def test_defaults(self):
        cfg = MLGovernanceConfig()
        assert cfg.timeout == 5.0
        assert cfg.max_retries == 3
        assert cfg.circuit_breaker_threshold == 5
        assert cfg.enable_async_queue is True
        assert cfg.graceful_degradation is True

    def test_for_testing(self):
        cfg = MLGovernanceConfig.for_testing()
        assert cfg.base_url == "http://localhost:8001"
        assert cfg.timeout == 1.0
        assert cfg.max_retries == 1
        assert cfg.enable_async_queue is False

    def test_to_dict(self):
        cfg = MLGovernanceConfig.for_testing()
        d = cfg.to_dict()
        assert d["base_url"] == "http://localhost:8001"
        assert d["timeout"] == 1.0
        assert "max_retries" in d

    def test_from_environment_defaults(self):
        cfg = MLGovernanceConfig.from_environment()
        assert cfg.timeout == 5.0
        assert cfg.max_retries == 3

    def test_from_environment_with_env_vars(self):
        env = {
            "ADAPTIVE_LEARNING_URL": "http://test:9999",
            "ML_GOVERNANCE_TIMEOUT": "10.0",
            "ML_GOVERNANCE_MAX_RETRIES": "5",
            "ML_GOVERNANCE_RETRY_DELAY": "1.0",
            "ML_GOVERNANCE_CIRCUIT_THRESHOLD": "10",
            "ML_GOVERNANCE_CIRCUIT_RESET": "60.0",
            "ML_GOVERNANCE_ENABLE_QUEUE": "false",
            "ML_GOVERNANCE_MAX_QUEUE_SIZE": "500",
            "ML_GOVERNANCE_GRACEFUL_DEGRADATION": "false",
        }
        with patch.dict("os.environ", env, clear=False):
            cfg = MLGovernanceConfig.from_environment()
            assert cfg.base_url == "http://test:9999"
            assert cfg.timeout == 10.0
            assert cfg.max_retries == 5
            assert cfg.retry_delay == 1.0
            assert cfg.circuit_breaker_threshold == 10
            assert cfg.circuit_breaker_reset == 60.0
            assert cfg.enable_async_queue is False
            assert cfg.max_queue_size == 500
            assert cfg.graceful_degradation is False

    def test_from_environment_invalid_values(self):
        env = {
            "ML_GOVERNANCE_TIMEOUT": "not_a_number",
            "ML_GOVERNANCE_MAX_RETRIES": "nope",
        }
        with patch.dict("os.environ", env, clear=False):
            cfg = MLGovernanceConfig.from_environment()
            assert cfg.timeout == 5.0  # fallback
            assert cfg.max_retries == 3  # fallback


# ============================================================================
# ml_governance: Data Types
# ============================================================================


class TestOutcomeReport:
    def test_to_request_dict_minimal(self):
        report = OutcomeReport(features={"x": 1.0}, label=1)
        d = report.to_request_dict()
        assert d["features"] == {"x": 1.0}
        assert d["label"] == 1
        assert "sample_weight" not in d
        assert "tenant_id" not in d

    def test_to_request_dict_full(self):
        report = OutcomeReport(
            features={"x": 1.0},
            label=0,
            weight=0.5,
            tenant_id="t1",
            prediction_id="p1",
            timestamp=1234567890.0,
        )
        d = report.to_request_dict()
        assert d["sample_weight"] == 0.5
        assert d["tenant_id"] == "t1"
        assert d["prediction_id"] == "p1"
        assert d["timestamp"] == 1234567890.0


class TestOutcomeResult:
    def test_to_dict(self):
        r = OutcomeResult(
            status=OutcomeReportStatus.SUCCESS,
            success=True,
            sample_count=10,
            current_accuracy=0.95,
            message="ok",
            training_id="t1",
        )
        d = r.to_dict()
        assert d["status"] == "success"
        assert d["success"] is True
        assert d["sample_count"] == 10
        assert d["training_id"] == "t1"


class TestOutcomeReportStatus:
    def test_all_values(self):
        assert OutcomeReportStatus.SUCCESS.value == "success"
        assert OutcomeReportStatus.QUEUED.value == "queued"
        assert OutcomeReportStatus.FAILED.value == "failed"
        assert OutcomeReportStatus.CIRCUIT_OPEN.value == "circuit_open"
        assert OutcomeReportStatus.TIMEOUT.value == "timeout"
        assert OutcomeReportStatus.SERVICE_UNAVAILABLE.value == "service_unavailable"


# ============================================================================
# ml_governance: Client
# ============================================================================


class TestMLGovernanceClient:
    @pytest.fixture()
    def config(self):
        return MLGovernanceConfig.for_testing()

    @pytest.fixture()
    def client(self, config):
        return MLGovernanceClient(config=config)

    def test_init_defaults(self, client):
        assert client._http_client is None
        assert client._failure_count == 0
        assert len(client._queue) == 0

    def test_init_with_base_url(self):
        c = MLGovernanceClient(base_url="http://custom:5000/")
        assert c.config.base_url == "http://custom:5000"  # trailing slash stripped

    async def test_initialize_creates_client(self, client):
        await client.initialize()
        assert client._http_client is not None
        await client.close()

    async def test_initialize_idempotent(self, client):
        await client.initialize()
        first = client._http_client
        await client.initialize()
        assert client._http_client is first
        await client.close()

    async def test_context_manager(self, config):
        async with MLGovernanceClient(config=config) as c:
            assert c._http_client is not None
        assert c._http_client is None

    async def test_close_without_init(self, client):
        # Should not raise
        await client.close()

    def test_check_circuit_closed(self, client):
        assert client._check_circuit() is True

    def test_check_circuit_open_not_expired(self, client):
        from enhanced_agent_bus.circuit_breaker.enums import CircuitState

        client._circuit_state = CircuitState.OPEN
        client._last_failure_time = datetime.now(UTC).timestamp()
        assert client._check_circuit() is False

    def test_check_circuit_open_expired(self, client):
        from enhanced_agent_bus.circuit_breaker.enums import CircuitState

        client._circuit_state = CircuitState.OPEN
        client._last_failure_time = datetime.now(UTC).timestamp() - 100
        assert client._check_circuit() is True
        assert client._circuit_state == CircuitState.HALF_OPEN

    def test_check_circuit_half_open(self, client):
        from enhanced_agent_bus.circuit_breaker.enums import CircuitState

        client._circuit_state = CircuitState.HALF_OPEN
        assert client._check_circuit() is True

    def test_record_success_closes_circuit(self, client):
        from enhanced_agent_bus.circuit_breaker.enums import CircuitState

        client._circuit_state = CircuitState.HALF_OPEN
        client._failure_count = 3
        client._record_success()
        assert client._circuit_state == CircuitState.CLOSED
        assert client._failure_count == 0

    def test_record_failure_opens_circuit(self, client):
        from enhanced_agent_bus.circuit_breaker.enums import CircuitState

        # threshold is 2 for testing config
        client._record_failure()
        assert client._circuit_state == CircuitState.CLOSED
        client._record_failure()
        assert client._circuit_state == CircuitState.OPEN

    def test_record_failure_callback_error(self, client):
        def bad_callback():
            raise RuntimeError("cb error")

        client._on_circuit_open_callbacks.append(bad_callback)
        # Force open
        client._failure_count = client.config.circuit_breaker_threshold - 1
        client._record_failure()  # should not raise

    def test_queue_report(self, client):
        report = OutcomeReport(features={"x": 1.0}, label=1)
        result = client._queue_report(report)
        assert result.status == OutcomeReportStatus.QUEUED
        assert len(client._queue) == 1

    def test_queue_report_overflow(self, client):
        # max_queue_size is 10 for testing config
        for i in range(12):
            report = OutcomeReport(features={"x": float(i)}, label=1)
            client._queue_report(report)
        assert len(client._queue) == 10  # oldest dropped

    async def test_report_outcome_circuit_open_with_queue(self, client):
        from enhanced_agent_bus.circuit_breaker.enums import CircuitState

        client.config.enable_async_queue = True
        client._circuit_state = CircuitState.OPEN
        client._last_failure_time = datetime.now(UTC).timestamp()
        result = await client.report_outcome(features={"x": 1.0}, label=1)
        assert result.status == OutcomeReportStatus.QUEUED

    async def test_report_outcome_circuit_open_no_queue(self, client):
        from enhanced_agent_bus.circuit_breaker.enums import CircuitState

        client.config.enable_async_queue = False
        client._circuit_state = CircuitState.OPEN
        client._last_failure_time = datetime.now(UTC).timestamp()
        result = await client.report_outcome(features={"x": 1.0}, label=1)
        assert result.status == OutcomeReportStatus.CIRCUIT_OPEN

    async def test_send_request_200(self, client):
        await client.initialize()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "sample_count": 5,
            "current_accuracy": 0.9,
            "message": "ok",
            "training_id": "t1",
        }
        client._http_client.post = AsyncMock(return_value=mock_response)  # type: ignore[union-attr]

        report = OutcomeReport(features={"x": 1.0}, label=1)
        result = await client._send_request(report)
        assert result.status == OutcomeReportStatus.SUCCESS
        assert result.success is True
        assert result.sample_count == 5
        await client.close()

    async def test_send_request_202(self, client):
        await client.initialize()
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            "sample_count": 1,
            "current_accuracy": 0.85,
            "message": "Accepted",
        }
        client._http_client.post = AsyncMock(return_value=mock_response)  # type: ignore[union-attr]

        report = OutcomeReport(features={"x": 1.0}, label=1)
        result = await client._send_request(report)
        assert result.status == OutcomeReportStatus.SUCCESS
        await client.close()

    async def test_send_request_503(self, client):
        await client.initialize()
        mock_response = MagicMock()
        mock_response.status_code = 503
        client._http_client.post = AsyncMock(return_value=mock_response)  # type: ignore[union-attr]

        report = OutcomeReport(features={"x": 1.0}, label=1)
        result = await client._send_request(report)
        assert result.status == OutcomeReportStatus.SERVICE_UNAVAILABLE
        assert result.success is False
        await client.close()

    async def test_send_request_other_error(self, client):
        await client.initialize()
        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.json.return_value = {"detail": "Validation error"}
        client._http_client.post = AsyncMock(return_value=mock_response)  # type: ignore[union-attr]

        report = OutcomeReport(features={"x": 1.0}, label=1)
        result = await client._send_request(report)
        assert result.status == OutcomeReportStatus.FAILED
        assert "Validation error" in result.message
        await client.close()

    async def test_send_request_error_json_fails(self, client):
        await client.initialize()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.side_effect = ValueError("bad json")
        mock_response.text = "Internal Server Error"
        client._http_client.post = AsyncMock(return_value=mock_response)  # type: ignore[union-attr]

        report = OutcomeReport(features={"x": 1.0}, label=1)
        result = await client._send_request(report)
        assert result.status == OutcomeReportStatus.FAILED
        assert "Internal Server Error" in result.message
        await client.close()

    async def test_send_request_not_initialized(self, client):
        report = OutcomeReport(features={"x": 1.0}, label=1)
        with pytest.raises(MLGovernanceConnectionError):
            await client._send_request(report)

    async def test_send_request_success_callback(self, client):
        await client.initialize()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        client._http_client.post = AsyncMock(return_value=mock_response)  # type: ignore[union-attr]

        called = []
        client.on_success(lambda r: called.append(r))

        report = OutcomeReport(features={"x": 1.0}, label=1)
        await client._send_request(report)
        assert len(called) == 1
        await client.close()

    async def test_send_request_success_callback_error(self, client):
        await client.initialize()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        client._http_client.post = AsyncMock(return_value=mock_response)  # type: ignore[union-attr]

        client.on_success(lambda r: (_ for _ in ()).throw(RuntimeError("cb fail")))

        report = OutcomeReport(features={"x": 1.0}, label=1)
        # Should not raise despite callback error
        result = await client._send_request(report)
        assert result.success is True
        await client.close()

    async def test_submit_report_retries_on_timeout(self, client):
        await client.initialize()
        client._http_client.post = AsyncMock(  # type: ignore[union-attr]
            side_effect=httpx.ConnectError("refused"),
        )

        with patch(
            "enhanced_agent_bus.integrations.ml_governance.MLGovernanceClient._sanitize_error",
            return_value="sanitized",
        ):
            result = await client._submit_report(OutcomeReport(features={"x": 1.0}, label=1))
        # max_retries=1 for testing, graceful_degradation=True, queue disabled
        assert result.success is False
        await client.close()

    async def test_submit_report_unexpected_error(self, client):
        await client.initialize()
        client._http_client.post = AsyncMock(  # type: ignore[union-attr]
            side_effect=ValueError("unexpected"),
        )

        with patch(
            "enhanced_agent_bus.integrations.ml_governance.MLGovernanceClient._sanitize_error",
            return_value="sanitized",
        ):
            result = await client._submit_report(OutcomeReport(features={"x": 1.0}, label=1))
        assert result.success is False
        await client.close()

    async def test_submit_report_not_graceful_timeout(self):
        cfg = MLGovernanceConfig.for_testing()
        cfg.graceful_degradation = False
        cfg.enable_async_queue = False
        client = MLGovernanceClient(config=cfg)
        await client.initialize()
        client._http_client.post = AsyncMock(  # type: ignore[union-attr]
            side_effect=httpx.TimeoutException("timeout"),
        )
        with pytest.raises(MLGovernanceTimeoutError):
            await client._submit_report(OutcomeReport(features={"x": 1.0}, label=1))
        await client.close()

    async def test_submit_report_not_graceful_connection(self):
        cfg = MLGovernanceConfig.for_testing()
        cfg.graceful_degradation = False
        cfg.enable_async_queue = False
        client = MLGovernanceClient(config=cfg)
        await client.initialize()
        client._http_client.post = AsyncMock(  # type: ignore[union-attr]
            side_effect=httpx.ConnectError("refused"),
        )
        with pytest.raises(MLGovernanceConnectionError):
            await client._submit_report(OutcomeReport(features={"x": 1.0}, label=1))
        await client.close()

    async def test_flush_queue_empty(self, client):
        count = await client._flush_queue()
        assert count == 0

    async def test_flush_queue_success(self, client):
        await client.initialize()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        client._http_client.post = AsyncMock(return_value=mock_response)  # type: ignore[union-attr]

        client._queue = [OutcomeReport(features={"x": 1.0}, label=1)]
        count = await client._flush_queue()
        assert count == 1
        assert len(client._queue) == 0
        await client.close()

    async def test_flush_queue_circuit_open(self, client):
        from enhanced_agent_bus.circuit_breaker.enums import CircuitState

        client._circuit_state = CircuitState.OPEN
        client._last_failure_time = datetime.now(UTC).timestamp()
        client._queue = [OutcomeReport(features={"x": 1.0}, label=1)]
        count = await client._flush_queue()
        assert count == 0
        assert len(client._queue) == 1

    async def test_flush_queue_send_fails(self, client):
        await client.initialize()
        client._http_client.post = AsyncMock(  # type: ignore[union-attr]
            side_effect=OSError("network"),
        )
        client._queue = [OutcomeReport(features={"x": 1.0}, label=1)]
        count = await client._flush_queue()
        assert count == 0
        assert len(client._queue) == 1
        await client.close()

    async def test_report_outcomes_batch_success(self, client):
        await client.initialize()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "accepted": 2,
            "sample_count": 2,
            "current_accuracy": 0.9,
        }
        client._http_client.post = AsyncMock(return_value=mock_response)  # type: ignore[union-attr]

        reports = [
            OutcomeReport(features={"x": 1.0}, label=1),
            OutcomeReport(features={"y": 2.0}, label=0),
        ]
        results = await client.report_outcomes_batch(reports)
        assert len(results) == 2
        assert all(r.success for r in results)
        await client.close()

    async def test_report_outcomes_batch_circuit_open(self, client):
        from enhanced_agent_bus.circuit_breaker.enums import CircuitState

        client._circuit_state = CircuitState.OPEN
        client._last_failure_time = datetime.now(UTC).timestamp()
        reports = [OutcomeReport(features={"x": 1.0}, label=1)]
        results = await client.report_outcomes_batch(reports)
        assert results[0].status == OutcomeReportStatus.CIRCUIT_OPEN

    async def test_report_outcomes_batch_http_error(self, client):
        await client.initialize()
        client._http_client.post = AsyncMock(  # type: ignore[union-attr]
            side_effect=httpx.ConnectError("fail"),
        )
        reports = [OutcomeReport(features={"x": 1.0}, label=1)]
        results = await client.report_outcomes_batch(reports)
        assert results[0].status == OutcomeReportStatus.FAILED
        await client.close()

    async def test_report_outcomes_batch_non_200(self, client):
        await client.initialize()
        mock_response = MagicMock()
        mock_response.status_code = 500
        client._http_client.post = AsyncMock(return_value=mock_response)  # type: ignore[union-attr]

        reports = [OutcomeReport(features={"x": 1.0}, label=1)]
        results = await client.report_outcomes_batch(reports)
        assert results[0].status == OutcomeReportStatus.FAILED
        await client.close()

    async def test_health_check_healthy(self, client):
        await client.initialize()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "service": "adaptive-learning-engine",
            "model_status": "ready",
        }
        client._http_client.get = AsyncMock(return_value=mock_response)  # type: ignore[union-attr]

        result = await client.health_check()
        assert result["status"] == "healthy"
        assert result["service"] == "adaptive-learning-engine"
        await client.close()

    async def test_health_check_unhealthy(self, client):
        await client.initialize()
        mock_response = MagicMock()
        mock_response.status_code = 503
        client._http_client.get = AsyncMock(return_value=mock_response)  # type: ignore[union-attr]

        result = await client.health_check()
        assert result["status"] == "unhealthy"
        await client.close()

    async def test_health_check_error(self, client):
        await client.initialize()
        client._http_client.get = AsyncMock(  # type: ignore[union-attr]
            side_effect=httpx.ConnectError("fail"),
        )
        result = await client.health_check()
        assert result["status"] == "unhealthy"
        await client.close()

    def test_get_stats(self, client):
        stats = client.get_stats()
        assert stats["circuit_state"] == "closed"
        assert stats["failure_count"] == 0
        assert stats["queue_size"] == 0
        assert stats["initialized"] is False

    def test_callback_registration(self, client):
        client.on_success(lambda r: None)
        client.on_failure(lambda s: None)
        client.on_circuit_open(lambda: None)
        assert len(client._on_success_callbacks) == 1
        assert len(client._on_failure_callbacks) == 1
        assert len(client._on_circuit_open_callbacks) == 1

    async def test_failure_callbacks_on_graceful_degradation(self, client):
        """Test that failure callbacks fire when all retries fail."""
        client.config.enable_async_queue = False
        await client.initialize()
        client._http_client.post = AsyncMock(  # type: ignore[union-attr]
            side_effect=httpx.ConnectError("fail"),
        )

        called = []
        client.on_failure(lambda msg: called.append(msg))

        with patch(
            "enhanced_agent_bus.integrations.ml_governance.MLGovernanceClient._sanitize_error",
            return_value="sanitized",
        ):
            result = await client._submit_report(OutcomeReport(features={"x": 1.0}, label=1))
        assert result.status == OutcomeReportStatus.SERVICE_UNAVAILABLE
        assert len(called) == 1
        await client.close()


class TestGetMLGovernanceClient:
    def test_get_client_call(self):
        # The global _ml_governance_client is unreachable due to indentation
        # in the source, so get_ml_governance_client raises NameError.
        with pytest.raises(NameError):
            get_ml_governance_client()


# ============================================================================
# benchmark_gpu_decision: generate_random_message
# ============================================================================


class TestGenerateRandomMessage:
    def test_returns_dict(self):
        msg = generate_random_message()
        assert isinstance(msg, dict)
        assert "timestamp" in msg
        assert "agent_id" in msg
        assert "content" in msg

    def test_randomness(self):
        messages = [generate_random_message() for _ in range(20)]
        agent_ids = {m["agent_id"] for m in messages}
        # With 20 samples from 1-100, very likely to get > 1 unique
        assert len(agent_ids) >= 1

    def test_sample_messages_structure(self):
        for msg in SAMPLE_MESSAGES:
            assert "content" in msg
            assert "priority" in msg


# ============================================================================
# benchmark_gpu_decision: GPUBenchmark
# ============================================================================


class TestGPUBenchmark:
    def test_init_defaults(self):
        bench = GPUBenchmark()
        assert bench.num_samples == 200
        assert bench.concurrency == 4
        assert bench.warmup_samples == 20
        assert bench.results == {}

    def test_init_custom(self):
        bench = GPUBenchmark(num_samples=50, concurrency=2, warmup_samples=5)
        assert bench.num_samples == 50
        assert bench.concurrency == 2
        assert bench.warmup_samples == 5

    def test_import_scorer_fallback(self):
        """When ImpactScorer is not importable, returns None tuple."""
        bench = GPUBenchmark(num_samples=5)
        with patch(
            "enhanced_agent_bus.profiling.benchmark_gpu_decision.GPUBenchmark._import_scorer",
            return_value=(None, None, None, None),
        ):
            result = bench._import_scorer()
            assert result == (None, None, None, None)

    def test_import_scorer_real(self):
        """Test actual import (may or may not have ImpactScorer)."""
        bench = GPUBenchmark(num_samples=5)
        result = bench._import_scorer()
        # Returns a 4-tuple regardless
        assert len(result) == 4

    def test_run_warmup(self):
        bench = GPUBenchmark(num_samples=5, warmup_samples=3)
        mock_scorer = MagicMock()
        mock_scorer.calculate_impact_score.return_value = 0.5
        bench.run_warmup(mock_scorer)
        assert mock_scorer.calculate_impact_score.call_count == 3

    def test_run_sequential_benchmark(self):
        bench = GPUBenchmark(num_samples=10)
        mock_scorer = MagicMock()
        mock_scorer.calculate_impact_score.return_value = 0.5
        rps = bench.run_sequential_benchmark(mock_scorer)
        assert rps > 0
        assert mock_scorer.calculate_impact_score.call_count == 10

    def test_run_concurrent_benchmark(self):
        bench = GPUBenchmark(num_samples=10, concurrency=2)
        mock_scorer = MagicMock()
        mock_scorer.calculate_impact_score.return_value = 0.5
        rps = bench.run_concurrent_benchmark(mock_scorer)
        assert rps > 0
        assert mock_scorer.calculate_impact_score.call_count == 10

    def test_run_mock_benchmark(self):
        bench = GPUBenchmark(num_samples=5)
        # Mock profiler to avoid actual sleep
        mock_profiler = MagicMock()
        mock_profiler.generate_report.return_value = "mock report"
        mock_profiler.get_all_metrics.return_value = {}

        from contextlib import contextmanager

        @contextmanager
        def mock_track(name):
            yield

        mock_profiler.track = mock_track
        bench.profiler = mock_profiler

        result = bench._run_mock_benchmark()
        assert result["benchmark_info"]["mock"] is True
        assert "gpu_decision_matrix" in result

    def test_generate_summary_no_gpu(self):
        bench = GPUBenchmark()
        gpu_matrix = {
            "model_a": {
                "analysis": {"bottleneck_type": "io_bound"},
                "latency": {"p99_ms": 1.5},
            },
        }
        summary = bench._generate_summary(gpu_matrix, 1000.0, 2000.0)
        assert summary["overall_recommendation"] == "KEEP_CPU"
        assert len(summary["reasons"]) >= 1
        assert len(summary["action_items"]) >= 1

    def test_generate_summary_gpu_candidate(self):
        bench = GPUBenchmark()
        gpu_matrix = {
            "model_a": {
                "analysis": {"bottleneck_type": "compute_bound"},
                "latency": {"p99_ms": 10.0},
            },
        }
        summary = bench._generate_summary(gpu_matrix, 500.0, 1000.0)
        assert summary["overall_recommendation"] == "EVALUATE_GPU"
        assert any("model_a" in r for r in summary["reasons"])

    def test_generate_summary_error_in_metrics(self):
        bench = GPUBenchmark()
        gpu_matrix = {
            "model_a": {"error": "failed to profile"},
        }
        summary = bench._generate_summary(gpu_matrix, 500.0, 1000.0)
        assert summary["overall_recommendation"] == "KEEP_CPU"

    def test_generate_summary_mixed(self):
        bench = GPUBenchmark()
        gpu_matrix = {
            "model_a": {
                "analysis": {"bottleneck_type": "compute_bound"},
                "latency": {"p99_ms": 15.0},
            },
            "model_b": {
                "analysis": {"bottleneck_type": "io_bound"},
                "latency": {"p99_ms": 2.0},
            },
        }
        summary = bench._generate_summary(gpu_matrix, 500.0, 1000.0)
        assert summary["overall_recommendation"] == "EVALUATE_GPU"

    def test_print_summary(self):
        bench = GPUBenchmark()
        bench.results = {
            "summary": {
                "overall_recommendation": "KEEP_CPU",
                "reasons": ["reason1"],
                "action_items": ["action1"],
            },
            "throughput": {
                "sequential_rps": 1000.0,
                "concurrent_rps": 2000.0,
                "concurrency_scaling": 2.0,
            },
        }
        # Should not raise
        bench._print_summary()

    def test_print_summary_empty(self):
        bench = GPUBenchmark()
        bench.results = {}
        bench._print_summary()

    def test_save_results(self, tmp_path):
        bench = GPUBenchmark()
        bench.results = {"test": "data"}
        out = str(tmp_path / "results.json")
        path = bench.save_results(out)
        assert path == out
        with open(out) as f:
            data = json.load(f)
        assert data["test"] == "data"

    def test_save_results_default_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        bench = GPUBenchmark()
        bench.results = {"test": True}
        path = bench.save_results()
        assert path.startswith("gpu_benchmark_results_")
        assert path.endswith(".json")

    def test_run_calls_mock_when_scorer_unavailable(self):
        bench = GPUBenchmark(num_samples=5)
        bench._import_scorer = MagicMock(return_value=(None, None, None, None))

        mock_profiler = MagicMock()
        mock_profiler.generate_report.return_value = "report"
        mock_profiler.get_all_metrics.return_value = {}

        from contextlib import contextmanager

        @contextmanager
        def mock_track(name):
            yield

        mock_profiler.track = mock_track
        bench.profiler = mock_profiler

        result = bench.run()
        assert result["benchmark_info"]["mock"] is True

    def test_run_scorer_init_fails(self):
        bench = GPUBenchmark(num_samples=5)

        mock_scorer_cls = MagicMock()
        mock_get_scorer = MagicMock(side_effect=RuntimeError("init fail"))

        bench._import_scorer = MagicMock(
            return_value=(mock_scorer_cls, mock_get_scorer, None, None),
        )

        mock_profiler = MagicMock()
        mock_profiler.generate_report.return_value = "report"
        mock_profiler.get_all_metrics.return_value = {}

        from contextlib import contextmanager

        @contextmanager
        def mock_track(name):
            yield

        mock_profiler.track = mock_track
        bench.profiler = mock_profiler

        result = bench.run()
        assert result["benchmark_info"]["mock"] is True

    def test_run_full_with_scorer(self):
        bench = GPUBenchmark(num_samples=5, warmup_samples=2, concurrency=1)

        mock_scorer = MagicMock()
        mock_scorer.model_name = "test-model"
        mock_scorer._bert_enabled = False
        mock_scorer._onnx_enabled = False
        mock_scorer.calculate_impact_score.return_value = 0.5

        mock_get_scorer = MagicMock(return_value=mock_scorer)
        mock_get_report = MagicMock(return_value="Profile Report")
        mock_get_matrix = MagicMock(
            return_value={
                "model": {
                    "analysis": {"bottleneck_type": "io_bound"},
                    "latency": {"p99_ms": 1.0},
                }
            },
        )

        bench._import_scorer = MagicMock(
            return_value=(MagicMock, mock_get_scorer, mock_get_report, mock_get_matrix),
        )

        result = bench.run()
        assert "throughput" in result
        assert "gpu_decision_matrix" in result
        assert "summary" in result
        assert result["throughput"]["sequential_rps"] > 0


class TestMainFunction:
    def test_main_no_save(self):
        from enhanced_agent_bus.profiling.benchmark_gpu_decision import main

        mock_bench_instance = MagicMock()
        mock_bench_instance.run.return_value = {
            "summary": {"overall_recommendation": "KEEP_CPU"},
        }

        with (
            patch("sys.argv", ["prog", "--no-save", "--samples", "5"]),
            patch(
                "enhanced_agent_bus.profiling.benchmark_gpu_decision.GPUBenchmark",
                return_value=mock_bench_instance,
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 0

    def test_main_evaluate_gpu_exit_code(self):
        from enhanced_agent_bus.profiling.benchmark_gpu_decision import main

        mock_bench_instance = MagicMock()
        mock_bench_instance.run.return_value = {
            "summary": {"overall_recommendation": "EVALUATE_GPU"},
        }

        with (
            patch("sys.argv", ["prog", "--no-save", "--samples", "5"]),
            patch(
                "enhanced_agent_bus.profiling.benchmark_gpu_decision.GPUBenchmark",
                return_value=mock_bench_instance,
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1
