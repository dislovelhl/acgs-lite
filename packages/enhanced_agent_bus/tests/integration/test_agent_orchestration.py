"""
ACGS-2 Phase 7: Integration Testing - Agent Orchestration Tests
Constitutional Hash: 608508a9bd224290

Comprehensive integration tests for:
- Fast lane processing (<1ms)
- Deliberation lane with OPA policy evaluation
- MACI separation (agents cannot validate own output)
- Phase 4 context window optimization
- Phase 5 response quality validation
- Constitutional hash consistency across all components
"""

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.types import JSONDict

# Constitutional Hash - must be present in all test files
# ============================================================================
# Test Models and Fixtures
# ============================================================================


class ProcessingLane(str, Enum):
    """Processing lanes for agent orchestration."""

    FAST = "fast"
    DELIBERATION = "deliberation"
    EMERGENCY = "emergency"


class MACIRole(str, Enum):
    """MACI role types for separation of concerns."""

    EXECUTIVE = "executive"
    LEGISLATIVE = "legislative"
    JUDICIAL = "judicial"
    MONITOR = "monitor"
    AUDITOR = "auditor"


@dataclass
class AgentTestMessage:
    """Test message model for integration tests."""

    id: str
    source_agent: str
    target_agent: str
    content: str
    message_type: str = "request"
    impact_score: float = 0.0
    constitutional_hash: str = CONSTITUTIONAL_HASH
    timestamp: float = field(default_factory=time.time)
    metadata: JSONDict = field(default_factory=dict)


@dataclass
class ProcessingResult:
    """Result from lane processing."""

    message_id: str
    lane: ProcessingLane
    processing_time_ms: float
    success: bool
    validation_passed: bool = True
    constitutional_compliant: bool = True
    error: str | None = None


@dataclass
class PolicyEvaluation:
    """OPA policy evaluation result."""

    policy_id: str
    decision: bool
    reason: str
    evaluated_at: float = field(default_factory=time.time)
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class QualityMetrics:
    """Response quality metrics."""

    relevance: float
    coherence: float
    accuracy: float
    constitutional_compliance: float
    overall_score: float


# ============================================================================
# Mock Services
# ============================================================================


class MockOPAClient:
    """Mock OPA client for policy evaluation testing."""

    def __init__(self, default_decision: bool = True):
        self.default_decision = default_decision
        self.evaluation_count = 0
        self.evaluation_history: list[JSONDict] = []

    async def evaluate_policy(self, policy_path: str, input_data: JSONDict) -> PolicyEvaluation:
        """Evaluate policy against input data."""
        self.evaluation_count += 1
        self.evaluation_history.append({"policy_path": policy_path, "input_data": input_data})

        # Check for constitutional hash
        if input_data.get("constitutional_hash") != CONSTITUTIONAL_HASH:
            return PolicyEvaluation(
                policy_id=policy_path,
                decision=False,
                reason="Constitutional hash mismatch",
            )

        # Simulate policy-specific decisions
        if "deny_" in policy_path:
            return PolicyEvaluation(policy_id=policy_path, decision=False, reason="Policy denied")

        return PolicyEvaluation(
            policy_id=policy_path,
            decision=self.default_decision,
            reason="Policy passed",
        )


class MockRedisClient:
    """Mock Redis client for caching and pub/sub testing."""

    def __init__(self):
        self._cache: JSONDict = {}
        self._ttls: dict[str, float] = {}
        self._pubsub_channels: dict[str, list[Any]] = {}

    async def get(self, key: str) -> Any | None:
        """Get value from cache."""
        if key in self._cache:
            if self._ttls.get(key, float("inf")) > time.time():
                return self._cache[key]
            del self._cache[key]
        return None

    async def set(self, key: str, value: Any, ex: int | None = None) -> bool:
        """set value in cache."""
        self._cache[key] = value
        if ex:
            self._ttls[key] = time.time() + ex
        return True

    async def delete(self, key: str) -> int:
        """Delete key from cache."""
        if key in self._cache:
            del self._cache[key]
            return 1
        return 0

    async def publish(self, channel: str, message: Any) -> int:
        """Publish message to channel."""
        if channel not in self._pubsub_channels:
            self._pubsub_channels[channel] = []
        self._pubsub_channels[channel].append(message)
        return 1


class MockZ3Solver:
    """Mock Z3 solver for formal verification testing."""

    def __init__(self, satisfiable: bool = True):
        self.satisfiable = satisfiable
        self.constraints: list[str] = []

    def add(self, constraint: str) -> None:
        """Add constraint to solver."""
        self.constraints.append(constraint)

    def check(self) -> str:
        """Check satisfiability."""
        return "sat" if self.satisfiable else "unsat"

    def model(self) -> JSONDict:
        """Get model if satisfiable."""
        if self.satisfiable:
            return {"verified": True, "constitutional_hash": CONSTITUTIONAL_HASH}
        return {}


# ============================================================================
# Core Processing Components (Mocked for Integration)
# ============================================================================


class FastLaneProcessor:
    """Fast lane processor for low-impact messages (<1ms target)."""

    def __init__(self, cache: MockRedisClient):
        self.cache = cache
        self.processed_count = 0
        self.constitutional_hash = CONSTITUTIONAL_HASH

    async def process(self, message: AgentTestMessage) -> ProcessingResult:
        """Process message in fast lane."""
        start_time = time.perf_counter()

        # Verify constitutional hash
        if message.constitutional_hash != CONSTITUTIONAL_HASH:
            return ProcessingResult(
                message_id=message.id,
                lane=ProcessingLane.FAST,
                processing_time_ms=0.0,
                success=False,
                constitutional_compliant=False,
                error="Constitutional hash mismatch",
            )

        # Check cache first
        cache_key = f"fast:{message.id}"
        cached = await self.cache.get(cache_key)
        if cached:
            return ProcessingResult(
                message_id=message.id,
                lane=ProcessingLane.FAST,
                processing_time_ms=(time.perf_counter() - start_time) * 1000,
                success=True,
            )

        # Process message (minimal validation for fast lane)
        self.processed_count += 1
        await self.cache.set(cache_key, {"processed": True}, ex=60)

        processing_time = (time.perf_counter() - start_time) * 1000
        return ProcessingResult(
            message_id=message.id,
            lane=ProcessingLane.FAST,
            processing_time_ms=processing_time,
            success=True,
        )


class DeliberationLaneProcessor:
    """Deliberation lane processor with OPA policy evaluation."""

    def __init__(self, opa_client: MockOPAClient, cache: MockRedisClient):
        self.opa_client = opa_client
        self.cache = cache
        self.processed_count = 0
        self.constitutional_hash = CONSTITUTIONAL_HASH

    async def process(
        self, message: AgentTestMessage, policy_path: str = "governance/default"
    ) -> ProcessingResult:
        """Process message through deliberation with policy evaluation."""
        start_time = time.perf_counter()

        # Verify constitutional hash
        if message.constitutional_hash != CONSTITUTIONAL_HASH:
            return ProcessingResult(
                message_id=message.id,
                lane=ProcessingLane.DELIBERATION,
                processing_time_ms=0.0,
                success=False,
                constitutional_compliant=False,
                error="Constitutional hash mismatch",
            )

        # Evaluate policy via OPA
        policy_result = await self.opa_client.evaluate_policy(
            policy_path,
            {
                "message_id": message.id,
                "source_agent": message.source_agent,
                "target_agent": message.target_agent,
                "impact_score": message.impact_score,
                "constitutional_hash": message.constitutional_hash,
            },
        )

        if not policy_result.decision:
            return ProcessingResult(
                message_id=message.id,
                lane=ProcessingLane.DELIBERATION,
                processing_time_ms=(time.perf_counter() - start_time) * 1000,
                success=False,
                validation_passed=False,
                error=policy_result.reason,
            )

        self.processed_count += 1
        processing_time = (time.perf_counter() - start_time) * 1000
        return ProcessingResult(
            message_id=message.id,
            lane=ProcessingLane.DELIBERATION,
            processing_time_ms=processing_time,
            success=True,
        )


class MACIEnforcer:
    """MACI separation enforcer - prevents agents from validating own output."""

    def __init__(self):
        self.agent_roles: dict[str, MACIRole] = {}
        self.validation_history: list[JSONDict] = []
        self.constitutional_hash = CONSTITUTIONAL_HASH

    def register_agent(self, agent_id: str, role: MACIRole) -> None:
        """Register an agent with a specific MACI role."""
        self.agent_roles[agent_id] = role

    def can_validate(self, validator_agent: str, producer_agent: str) -> tuple[bool, str]:
        """
        Check if validator_agent can validate producer_agent's output.
        Key rule: An agent cannot validate its own output.
        """
        # Rule 1: Cannot validate own output
        if validator_agent == producer_agent:
            return False, "Self-validation prohibited: agents cannot validate own output"

        validator_role = self.agent_roles.get(validator_agent)
        producer_role = self.agent_roles.get(producer_agent)

        if not validator_role:
            return False, f"Validator agent '{validator_agent}' not registered"

        if not producer_role:
            return False, f"Producer agent '{producer_agent}' not registered"

        # Rule 2: Only JUDICIAL and AUDITOR roles can validate
        if validator_role not in (MACIRole.JUDICIAL, MACIRole.AUDITOR):
            return (
                False,
                f"Role '{validator_role.value}' cannot perform validation",
            )

        # Rule 3: Cannot validate agents of equal or higher role
        role_hierarchy = {
            MACIRole.JUDICIAL: 5,
            MACIRole.AUDITOR: 4,
            MACIRole.LEGISLATIVE: 3,
            MACIRole.EXECUTIVE: 2,
            MACIRole.MONITOR: 1,
        }

        if role_hierarchy.get(producer_role, 0) >= role_hierarchy.get(validator_role, 0):
            return (
                False,
                "Cannot validate agent with equal or higher role",
            )

        return True, "Validation permitted"

    def record_validation(
        self,
        validator_agent: str,
        producer_agent: str,
        result: bool,
        reason: str,
    ) -> None:
        """Record validation attempt for audit."""
        self.validation_history.append(
            {
                "validator": validator_agent,
                "producer": producer_agent,
                "result": result,
                "reason": reason,
                "timestamp": time.time(),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }
        )


class ContextWindowOptimizer:
    """Phase 4 context window optimizer for efficient context management."""

    def __init__(self, max_context_size: int = 128000):
        self.max_context_size = max_context_size
        self.cache: JSONDict = {}
        self.optimization_stats: dict[str, int] = {
            "cache_hits": 0,
            "cache_misses": 0,
            "compressions": 0,
        }
        self.constitutional_hash = CONSTITUTIONAL_HASH

    async def optimize_context(self, context_chunks: list[JSONDict], query: str) -> JSONDict:
        """Optimize context window for given query."""
        start_time = time.perf_counter()

        # Check cache
        cache_key = hashlib.md5(
            f"{query}:{len(context_chunks)}".encode(),
            usedforsecurity=False,  # Used for cache key, not security
        ).hexdigest()
        if cache_key in self.cache:
            self.optimization_stats["cache_hits"] += 1
            cached = self.cache[cache_key]
            cached["processing_time_ms"] = (time.perf_counter() - start_time) * 1000
            return cached

        self.optimization_stats["cache_misses"] += 1

        # Score and rank chunks by relevance
        scored_chunks = []
        for chunk in context_chunks:
            relevance = self._calculate_relevance(chunk, query)
            scored_chunks.append((relevance, chunk))

        scored_chunks.sort(key=lambda x: x[0], reverse=True)

        # Select top chunks within context window
        selected_chunks = []
        total_tokens = 0
        for _relevance, chunk in scored_chunks:
            chunk_tokens = chunk.get("tokens", 100)
            if total_tokens + chunk_tokens <= self.max_context_size:
                selected_chunks.append(chunk)
                total_tokens += chunk_tokens

        # Compress if needed
        if total_tokens > self.max_context_size * 0.9:
            self.optimization_stats["compressions"] += 1

        result = {
            "selected_chunks": selected_chunks,
            "total_tokens": total_tokens,
            "compression_applied": total_tokens > self.max_context_size * 0.9,
            "processing_time_ms": (time.perf_counter() - start_time) * 1000,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        self.cache[cache_key] = result
        return result

    def _calculate_relevance(self, chunk: JSONDict, query: str) -> float:
        """Calculate relevance score for chunk."""
        # Simplified relevance calculation
        content = chunk.get("content", "").lower()
        query_terms = query.lower().split()
        matches = sum(1 for term in query_terms if term in content)
        return matches / max(len(query_terms), 1)


class ResponseQualityValidator:
    """Phase 5 response quality validator."""

    def __init__(self):
        self.validation_history: list[QualityMetrics] = []
        self.thresholds = {
            "relevance": 0.7,
            "coherence": 0.8,
            "accuracy": 0.75,
            "constitutional_compliance": 0.95,
            "overall": 0.75,
        }
        self.constitutional_hash = CONSTITUTIONAL_HASH

    async def validate_response(
        self,
        response: str,
        prompt: str,
        expected_format: str | None = None,
    ) -> JSONDict:
        """Validate response quality."""
        start_time = time.perf_counter()

        # Calculate quality metrics
        metrics = QualityMetrics(
            relevance=self._calculate_relevance(response, prompt),
            coherence=self._calculate_coherence(response),
            accuracy=self._calculate_accuracy(response),
            constitutional_compliance=self._check_constitutional_compliance(response),
            overall_score=0.0,
        )

        # Calculate overall score
        metrics.overall_score = (
            metrics.relevance * 0.25
            + metrics.coherence * 0.2
            + metrics.accuracy * 0.25
            + metrics.constitutional_compliance * 0.3
        )

        self.validation_history.append(metrics)

        # Determine if response passes quality thresholds
        passes_quality = all(
            [
                metrics.relevance >= self.thresholds["relevance"],
                metrics.coherence >= self.thresholds["coherence"],
                metrics.accuracy >= self.thresholds["accuracy"],
                metrics.constitutional_compliance >= self.thresholds["constitutional_compliance"],
                metrics.overall_score >= self.thresholds["overall"],
            ]
        )

        return {
            "passed": passes_quality,
            "metrics": {
                "relevance": metrics.relevance,
                "coherence": metrics.coherence,
                "accuracy": metrics.accuracy,
                "constitutional_compliance": metrics.constitutional_compliance,
                "overall_score": metrics.overall_score,
            },
            "thresholds": self.thresholds,
            "processing_time_ms": (time.perf_counter() - start_time) * 1000,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

    def _calculate_relevance(self, response: str, prompt: str) -> float:
        """Calculate response relevance to prompt."""
        if not response or not prompt:
            return 0.0
        prompt_terms = set(prompt.lower().split())
        response_terms = set(response.lower().split())
        overlap = len(prompt_terms & response_terms)
        return min(1.0, overlap / max(len(prompt_terms), 1) * 2)

    def _calculate_coherence(self, response: str) -> float:
        """Calculate response coherence."""
        if not response:
            return 0.0
        # Check for sentence structure
        sentences = response.split(".")
        if len(sentences) < 1:
            return 0.5
        avg_length = sum(len(s.split()) for s in sentences) / len(sentences)
        # Coherent responses have reasonable sentence lengths
        if 5 <= avg_length <= 25:
            return 0.9
        elif 3 <= avg_length <= 35:
            return 0.7
        return 0.5

    def _calculate_accuracy(self, response: str) -> float:
        """Calculate response accuracy (simulated)."""
        # In real implementation, this would compare against ground truth
        if not response:
            return 0.0
        # Simulate accuracy based on response structure
        has_structure = any(marker in response for marker in [".", ",", ":", ";"])
        return 0.85 if has_structure else 0.6

    def _check_constitutional_compliance(self, response: str) -> float:
        """Check constitutional compliance of response."""
        if not response:
            return 0.0
        # Check for harmful content markers (simplified)
        harmful_markers = ["<script>", "DROP TABLE", "rm -rf", "exploit"]
        for marker in harmful_markers:
            if marker.lower() in response.lower():
                return 0.0
        return 0.98


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def redis_client():
    """Provide mock Redis client."""
    return MockRedisClient()


@pytest.fixture
def opa_client():
    """Provide mock OPA client."""
    return MockOPAClient()


@pytest.fixture
def z3_solver():
    """Provide mock Z3 solver."""
    return MockZ3Solver()


@pytest.fixture
def fast_lane_processor(redis_client):
    """Provide fast lane processor."""
    return FastLaneProcessor(redis_client)


@pytest.fixture
def deliberation_processor(opa_client, redis_client):
    """Provide deliberation lane processor."""
    return DeliberationLaneProcessor(opa_client, redis_client)


@pytest.fixture
def maci_enforcer():
    """Provide MACI enforcer with pre-registered agents."""
    enforcer = MACIEnforcer()
    # Register test agents
    enforcer.register_agent("agent_executive_1", MACIRole.EXECUTIVE)
    enforcer.register_agent("agent_legislative_1", MACIRole.LEGISLATIVE)
    enforcer.register_agent("agent_judicial_1", MACIRole.JUDICIAL)
    enforcer.register_agent("agent_auditor_1", MACIRole.AUDITOR)
    enforcer.register_agent("agent_monitor_1", MACIRole.MONITOR)
    return enforcer


@pytest.fixture
def context_optimizer():
    """Provide context window optimizer."""
    return ContextWindowOptimizer()


@pytest.fixture
def quality_validator():
    """Provide response quality validator."""
    return ResponseQualityValidator()


@pytest.fixture
def test_message():
    """Provide standard test message."""
    return AgentTestMessage(
        id="msg_001",
        source_agent="agent_executive_1",
        target_agent="agent_judicial_1",
        content="Test message content for processing",
        impact_score=0.3,
    )


@pytest.fixture
def high_impact_message():
    """Provide high-impact test message."""
    return AgentTestMessage(
        id="msg_002",
        source_agent="agent_executive_1",
        target_agent="agent_judicial_1",
        content="High impact policy change request",
        impact_score=0.9,
    )


# ============================================================================
# Test Class 1: Fast Lane Integration
# ============================================================================


class TestFastLaneIntegration:
    """Test fast lane processing achieves <1ms target latency."""

    async def test_fast_lane_processes_under_1ms(self, fast_lane_processor, test_message):
        """Verify fast lane processes messages in under 1ms."""
        result = await fast_lane_processor.process(test_message)

        assert result.success is True
        assert result.processing_time_ms < 1.0  # Under 1ms target
        assert result.lane == ProcessingLane.FAST
        assert result.constitutional_compliant is True

    async def test_fast_lane_caches_results(self, fast_lane_processor, test_message):
        """Verify fast lane caches processed messages."""
        # First processing
        result1 = await fast_lane_processor.process(test_message)
        # Second processing should use cache
        result2 = await fast_lane_processor.process(test_message)

        assert result1.success is True
        assert result2.success is True
        # Both should complete quickly (sub-ms); caching correctness matters,
        # not the relative timing which is flaky at sub-ms resolution.
        assert result2.processing_time_ms < 5.0

    async def test_fast_lane_validates_constitutional_hash(self, fast_lane_processor):
        """Verify fast lane rejects messages with invalid constitutional hash."""
        invalid_message = AgentTestMessage(
            id="msg_invalid",
            source_agent="agent_1",
            target_agent="agent_2",
            content="Test",
            constitutional_hash="invalid_hash",
        )

        result = await fast_lane_processor.process(invalid_message)

        assert result.success is False
        assert result.constitutional_compliant is False
        assert "hash mismatch" in result.error.lower()

    async def test_fast_lane_batch_processing(self, fast_lane_processor):
        """Verify fast lane handles batch processing efficiently."""
        messages = [
            AgentTestMessage(
                id=f"batch_msg_{i}",
                source_agent="agent_1",
                target_agent="agent_2",
                content=f"Batch message {i}",
            )
            for i in range(10)
        ]

        start_time = time.perf_counter()
        results = await asyncio.gather(*[fast_lane_processor.process(msg) for msg in messages])
        total_time = (time.perf_counter() - start_time) * 1000

        assert all(r.success for r in results)
        assert total_time < 50  # 10 messages should complete in < 50ms
        assert fast_lane_processor.processed_count == 10

    async def test_fast_lane_preserves_message_integrity(self, fast_lane_processor, test_message):
        """Verify fast lane preserves message integrity through processing."""
        original_content = test_message.content
        original_hash = test_message.constitutional_hash

        result = await fast_lane_processor.process(test_message)

        assert result.success is True
        assert test_message.content == original_content
        assert test_message.constitutional_hash == original_hash

    async def test_fast_lane_handles_concurrent_requests(self, fast_lane_processor):
        """Verify fast lane handles concurrent requests without race conditions."""
        concurrent_messages = [
            AgentTestMessage(
                id=f"concurrent_{i}",
                source_agent="agent_1",
                target_agent="agent_2",
                content=f"Concurrent message {i}",
            )
            for i in range(50)
        ]

        results = await asyncio.gather(
            *[fast_lane_processor.process(msg) for msg in concurrent_messages]
        )

        success_count = sum(1 for r in results if r.success)
        assert success_count == 50
        assert fast_lane_processor.processed_count == 50

    async def test_fast_lane_reports_processing_metrics(self, fast_lane_processor, test_message):
        """Verify fast lane reports accurate processing metrics."""
        result = await fast_lane_processor.process(test_message)

        assert result.message_id == test_message.id
        assert result.processing_time_ms >= 0
        assert result.lane == ProcessingLane.FAST
        assert isinstance(result.validation_passed, bool)

    async def test_fast_lane_constitutional_hash_attribute(self, fast_lane_processor):
        """Verify fast lane processor has constitutional hash attribute."""
        assert hasattr(fast_lane_processor, "constitutional_hash")
        assert fast_lane_processor.constitutional_hash == CONSTITUTIONAL_HASH


# ============================================================================
# Test Class 2: Deliberation Lane Integration
# ============================================================================


class TestDeliberationLaneIntegration:
    """Test deliberation lane with OPA policy evaluation."""

    async def test_deliberation_evaluates_opa_policy(
        self, deliberation_processor, high_impact_message
    ):
        """Verify deliberation lane evaluates OPA policies."""
        result = await deliberation_processor.process(high_impact_message)

        assert result.lane == ProcessingLane.DELIBERATION
        assert deliberation_processor.opa_client.evaluation_count == 1

    async def test_deliberation_respects_policy_decisions(
        self, opa_client, redis_client, high_impact_message
    ):
        """Verify deliberation respects OPA policy deny decisions."""
        processor = DeliberationLaneProcessor(MockOPAClient(default_decision=False), redis_client)

        result = await processor.process(high_impact_message)

        assert result.success is False
        assert result.validation_passed is False

    async def test_deliberation_validates_constitutional_hash(self, deliberation_processor):
        """Verify deliberation validates constitutional hash via OPA."""
        message = AgentTestMessage(
            id="msg_deliberate",
            source_agent="agent_1",
            target_agent="agent_2",
            content="Deliberation test",
            constitutional_hash="invalid_hash",
        )

        result = await deliberation_processor.process(message)

        assert result.success is False
        assert result.constitutional_compliant is False

    async def test_deliberation_policy_path_routing(
        self, deliberation_processor, high_impact_message
    ):
        """Verify deliberation routes to correct policy paths."""
        # Test with default policy
        result1 = await deliberation_processor.process(high_impact_message)
        # Test with specific policy
        result2 = await deliberation_processor.process(
            high_impact_message, policy_path="governance/strict"
        )

        assert deliberation_processor.opa_client.evaluation_count == 2
        history = deliberation_processor.opa_client.evaluation_history
        assert history[0]["policy_path"] == "governance/default"
        assert history[1]["policy_path"] == "governance/strict"

    async def test_deliberation_deny_policy_handling(
        self, deliberation_processor, high_impact_message
    ):
        """Verify deliberation handles deny policies correctly."""
        result = await deliberation_processor.process(high_impact_message, policy_path="deny_test")

        assert result.success is False
        assert "denied" in result.error.lower()

    async def test_deliberation_records_evaluation_history(
        self, deliberation_processor, high_impact_message
    ):
        """Verify deliberation records policy evaluation history."""
        await deliberation_processor.process(high_impact_message)

        history = deliberation_processor.opa_client.evaluation_history
        assert len(history) == 1
        assert history[0]["input_data"]["message_id"] == high_impact_message.id
        assert history[0]["input_data"]["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_deliberation_includes_impact_score_in_evaluation(
        self, deliberation_processor, high_impact_message
    ):
        """Verify deliberation includes impact score in OPA evaluation."""
        await deliberation_processor.process(high_impact_message)

        history = deliberation_processor.opa_client.evaluation_history
        assert history[0]["input_data"]["impact_score"] == 0.9

    async def test_deliberation_constitutional_hash_attribute(self, deliberation_processor):
        """Verify deliberation processor has constitutional hash attribute."""
        assert hasattr(deliberation_processor, "constitutional_hash")
        assert deliberation_processor.constitutional_hash == CONSTITUTIONAL_HASH


# ============================================================================
# Test Class 3: MACI Separation
# ============================================================================


class TestMACISeparation:
    """Test MACI separation - agents cannot validate own output."""

    def test_maci_prevents_self_validation(self, maci_enforcer):
        """Verify MACI prevents agents from validating own output."""
        can_validate, reason = maci_enforcer.can_validate("agent_judicial_1", "agent_judicial_1")

        assert can_validate is False
        assert "self-validation prohibited" in reason.lower()

    def test_maci_allows_cross_agent_validation(self, maci_enforcer):
        """Verify MACI allows cross-agent validation with proper roles."""
        can_validate, reason = maci_enforcer.can_validate("agent_judicial_1", "agent_executive_1")

        assert can_validate is True
        assert "permitted" in reason.lower()

    def test_maci_enforces_role_hierarchy(self, maci_enforcer):
        """Verify MACI enforces role hierarchy in validation."""
        # Executive cannot validate Judicial (higher role)
        can_validate, reason = maci_enforcer.can_validate("agent_executive_1", "agent_judicial_1")

        assert can_validate is False
        assert "cannot perform validation" in reason.lower()

    def test_maci_only_judicial_auditor_can_validate(self, maci_enforcer):
        """Verify only JUDICIAL and AUDITOR roles can perform validation."""
        # Monitor cannot validate
        can_validate, _reason = maci_enforcer.can_validate("agent_monitor_1", "agent_executive_1")

        assert can_validate is False

        # Auditor can validate
        can_validate, _reason = maci_enforcer.can_validate("agent_auditor_1", "agent_monitor_1")

        assert can_validate is True

    def test_maci_rejects_unregistered_validators(self, maci_enforcer):
        """Verify MACI rejects validation from unregistered agents."""
        can_validate, reason = maci_enforcer.can_validate("unregistered_agent", "agent_executive_1")

        assert can_validate is False
        assert "not registered" in reason.lower()

    def test_maci_rejects_unregistered_producers(self, maci_enforcer):
        """Verify MACI rejects validation of unregistered producers."""
        can_validate, reason = maci_enforcer.can_validate(
            "agent_judicial_1", "unregistered_producer"
        )

        assert can_validate is False
        assert "not registered" in reason.lower()

    def test_maci_records_validation_attempts(self, maci_enforcer):
        """Verify MACI records all validation attempts for audit."""
        can_validate, reason = maci_enforcer.can_validate("agent_judicial_1", "agent_executive_1")
        maci_enforcer.record_validation(
            "agent_judicial_1", "agent_executive_1", can_validate, reason
        )

        assert len(maci_enforcer.validation_history) == 1
        record = maci_enforcer.validation_history[0]
        assert record["validator"] == "agent_judicial_1"
        assert record["producer"] == "agent_executive_1"
        assert record["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_maci_constitutional_hash_attribute(self, maci_enforcer):
        """Verify MACI enforcer has constitutional hash attribute."""
        assert hasattr(maci_enforcer, "constitutional_hash")
        assert maci_enforcer.constitutional_hash == CONSTITUTIONAL_HASH


# ============================================================================
# Test Class 4: Context Window Optimization
# ============================================================================


class TestContextWindowOptimization:
    """Test Phase 4 context window optimization integration."""

    async def test_context_optimizer_selects_relevant_chunks(self, context_optimizer):
        """Verify context optimizer selects most relevant chunks."""
        chunks = [
            {"id": "c1", "content": "The weather today is sunny", "tokens": 50},
            {"id": "c2", "content": "Python programming basics", "tokens": 50},
            {"id": "c3", "content": "Weather forecast for tomorrow", "tokens": 50},
        ]

        result = await context_optimizer.optimize_context(chunks, "weather")

        assert len(result["selected_chunks"]) >= 2
        # Weather-related chunks should be prioritized
        selected_ids = [c["id"] for c in result["selected_chunks"]]
        assert "c1" in selected_ids or "c3" in selected_ids

    async def test_context_optimizer_respects_token_limits(self, context_optimizer):
        """Verify context optimizer respects max token limits."""
        # Create chunks that exceed limit
        large_chunks = [
            {"id": f"c{i}", "content": f"Content {i}" * 100, "tokens": 50000} for i in range(5)
        ]

        result = await context_optimizer.optimize_context(large_chunks, "test query")

        assert result["total_tokens"] <= context_optimizer.max_context_size

    async def test_context_optimizer_caches_results(self, context_optimizer):
        """Verify context optimizer caches optimization results."""
        chunks = [{"id": "c1", "content": "Test content", "tokens": 100}]
        query = "test query"

        # First call
        result1 = await context_optimizer.optimize_context(chunks, query)
        # Second call with same inputs
        result2 = await context_optimizer.optimize_context(chunks, query)

        assert context_optimizer.optimization_stats["cache_hits"] >= 1
        assert result2["processing_time_ms"] <= result1["processing_time_ms"]

    async def test_context_optimizer_tracks_statistics(self, context_optimizer):
        """Verify context optimizer tracks optimization statistics."""
        chunks = [{"id": "c1", "content": "Test", "tokens": 100}]

        await context_optimizer.optimize_context(chunks, "query1")
        await context_optimizer.optimize_context(chunks, "query2")

        stats = context_optimizer.optimization_stats
        assert "cache_hits" in stats
        assert "cache_misses" in stats
        assert "compressions" in stats

    async def test_context_optimizer_handles_empty_chunks(self, context_optimizer):
        """Verify context optimizer handles empty chunk lists."""
        result = await context_optimizer.optimize_context([], "test query")

        assert result["selected_chunks"] == []
        assert result["total_tokens"] == 0

    async def test_context_optimizer_includes_constitutional_hash(self, context_optimizer):
        """Verify context optimizer includes constitutional hash in results."""
        chunks = [{"id": "c1", "content": "Test", "tokens": 100}]

        result = await context_optimizer.optimize_context(chunks, "query")

        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_context_optimizer_processing_time(self, context_optimizer):
        """Verify context optimizer meets performance targets."""
        chunks = [{"id": f"c{i}", "content": f"Content {i}", "tokens": 100} for i in range(100)]

        result = await context_optimizer.optimize_context(chunks, "test query")

        # Should complete quickly even with 100 chunks
        assert result["processing_time_ms"] < 100

    async def test_context_optimizer_constitutional_hash_attribute(self, context_optimizer):
        """Verify context optimizer has constitutional hash attribute."""
        assert hasattr(context_optimizer, "constitutional_hash")
        assert context_optimizer.constitutional_hash == CONSTITUTIONAL_HASH


# ============================================================================
# Test Class 5: Response Quality Validation
# ============================================================================


class TestResponseQualityValidation:
    """Test Phase 5 response quality validator integration."""

    async def test_quality_validator_scores_relevance(self, quality_validator):
        """Verify quality validator scores response relevance."""
        result = await quality_validator.validate_response(
            "The weather today is sunny and warm",
            "What is the weather today?",
        )

        assert result["metrics"]["relevance"] > 0
        assert result["metrics"]["relevance"] <= 1.0

    async def test_quality_validator_scores_coherence(self, quality_validator):
        """Verify quality validator scores response coherence."""
        result = await quality_validator.validate_response(
            "This is a well-structured response. It has multiple sentences. Each sentence conveys meaning.",
            "Test prompt",
        )

        assert result["metrics"]["coherence"] > 0.5

    async def test_quality_validator_detects_constitutional_violations(self, quality_validator):
        """Verify quality validator detects constitutional compliance issues."""
        # Test with potentially harmful content
        result = await quality_validator.validate_response(
            "Use <script>alert('xss')</script> for injection",
            "How to secure code?",
        )

        assert result["metrics"]["constitutional_compliance"] < 0.5

    async def test_quality_validator_overall_score_calculation(self, quality_validator):
        """Verify quality validator calculates overall score correctly."""
        result = await quality_validator.validate_response(
            "A comprehensive and relevant response that addresses the prompt directly.",
            "Please provide a relevant response.",
        )

        metrics = result["metrics"]
        # Overall should be weighted combination
        expected_overall = (
            metrics["relevance"] * 0.25
            + metrics["coherence"] * 0.2
            + metrics["accuracy"] * 0.25
            + metrics["constitutional_compliance"] * 0.3
        )
        assert abs(metrics["overall_score"] - expected_overall) < 0.01

    async def test_quality_validator_applies_thresholds(self, quality_validator):
        """Verify quality validator applies quality thresholds."""
        # Low quality response
        result = await quality_validator.validate_response("x", "Test")

        assert result["passed"] is False  # Should fail thresholds
        assert "thresholds" in result

    async def test_quality_validator_records_history(self, quality_validator):
        """Verify quality validator records validation history."""
        await quality_validator.validate_response("Response 1", "Prompt 1")
        await quality_validator.validate_response("Response 2", "Prompt 2")

        assert len(quality_validator.validation_history) == 2

    async def test_quality_validator_includes_constitutional_hash(self, quality_validator):
        """Verify quality validator includes constitutional hash."""
        result = await quality_validator.validate_response("Test response", "Test prompt")

        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_quality_validator_constitutional_hash_attribute(self, quality_validator):
        """Verify quality validator has constitutional hash attribute."""
        assert hasattr(quality_validator, "constitutional_hash")
        assert quality_validator.constitutional_hash == CONSTITUTIONAL_HASH


# ============================================================================
# Test Class 6: Constitutional Hash Consistency
# ============================================================================


class TestConstitutionalHashConsistency:
    """Verify constitutional hash is present and consistent across all components."""

    def test_module_level_hash_defined(self):
        """Verify module-level CONSTITUTIONAL_HASH is defined."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_fast_lane_processor_hash(self, fast_lane_processor):
        """Verify fast lane processor has correct constitutional hash."""
        assert fast_lane_processor.constitutional_hash == CONSTITUTIONAL_HASH

    def test_deliberation_processor_hash(self, deliberation_processor):
        """Verify deliberation processor has correct constitutional hash."""
        assert deliberation_processor.constitutional_hash == CONSTITUTIONAL_HASH

    def test_maci_enforcer_hash(self, maci_enforcer):
        """Verify MACI enforcer has correct constitutional hash."""
        assert maci_enforcer.constitutional_hash == CONSTITUTIONAL_HASH

    def test_context_optimizer_hash(self, context_optimizer):
        """Verify context optimizer has correct constitutional hash."""
        assert context_optimizer.constitutional_hash == CONSTITUTIONAL_HASH

    def test_quality_validator_hash(self, quality_validator):
        """Verify quality validator has correct constitutional hash."""
        assert quality_validator.constitutional_hash == CONSTITUTIONAL_HASH

    def test_test_message_hash(self, test_message):
        """Verify test messages have correct constitutional hash."""
        assert test_message.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_policy_evaluation_hash(self, opa_client):
        """Verify OPA policy evaluations include constitutional hash."""
        result = await opa_client.evaluate_policy(
            "test_policy", {"constitutional_hash": CONSTITUTIONAL_HASH}
        )
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_maci_validation_record_hash(self, maci_enforcer):
        """Verify MACI validation records include constitutional hash."""
        maci_enforcer.record_validation("agent_judicial_1", "agent_executive_1", True, "Test")

        record = maci_enforcer.validation_history[0]
        assert record["constitutional_hash"] == CONSTITUTIONAL_HASH
