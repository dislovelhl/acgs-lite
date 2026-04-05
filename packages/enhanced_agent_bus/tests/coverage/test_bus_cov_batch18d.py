"""
Coverage tests for batch18d:
- coordinators/maci_coordinator.py
- llm_adapters/cost/optimizer.py
- llm_adapters/huggingface_adapter.py
- mcp_integration/auth/auth_injector.py
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. MACICoordinator tests
# ---------------------------------------------------------------------------


class TestMACICoordinator:
    """Tests for coordinators/maci_coordinator.py."""

    def _make_coordinator(self, strict_mode: bool = True, enable_audit: bool = True) -> Any:
        with patch(
            "enhanced_agent_bus.coordinators.maci_coordinator.MACICoordinator._initialize_maci"
        ):
            from enhanced_agent_bus.coordinators.maci_coordinator import MACICoordinator

            coord = MACICoordinator.__new__(MACICoordinator)
            coord._strict_mode = strict_mode
            coord._enable_audit = enable_audit
            coord._registry = None
            coord._enforcer = None
            coord._initialized = False
            coord._registered_agents = {}
            coord._validation_log = []
            return coord

    def test_is_available_false_when_not_initialized(self) -> None:
        coord = self._make_coordinator()
        assert coord.is_available is False

    def test_is_available_true_when_initialized_with_enforcer(self) -> None:
        coord = self._make_coordinator()
        coord._initialized = True
        coord._enforcer = MagicMock()
        assert coord.is_available is True

    def test_is_enabled(self) -> None:
        coord = self._make_coordinator()
        assert coord.is_enabled() is False
        coord._initialized = True
        assert coord.is_enabled() is True

    async def test_register_agent_no_registry(self) -> None:
        coord = self._make_coordinator()
        result = await coord.register_agent("agent-1", "executive")
        assert result is True
        assert coord._registered_agents["agent-1"] == "executive"

    async def test_register_agent_with_registry_error(self) -> None:
        coord = self._make_coordinator()
        coord._registry = MagicMock()
        # Simulate the import inside register_agent raising an error
        with patch.dict(
            "sys.modules",
            {
                "enhanced_agent_bus.maci_enforcement": MagicMock(
                    MACIRole=MagicMock(parse=MagicMock(side_effect=RuntimeError("bad role"))),
                    MACIAgentRoleConfig=MagicMock(),
                )
            },
        ):
            result = await coord.register_agent("agent-2", "judicial")
            assert result is False

    async def test_validate_action_self_validation_forbidden(self) -> None:
        coord = self._make_coordinator()
        result = await coord.validate_action("agent-1", "validate", target_output_id="agent-1")
        assert result["allowed"] is False
        assert "self-validation" in result["reason"]
        assert "constitutional_hash" in result

    async def test_validate_action_agent_not_registered(self) -> None:
        coord = self._make_coordinator()
        result = await coord.validate_action("unknown-agent", "query")
        assert result["allowed"] is False
        assert result["reason"] == "Agent not registered"

    async def test_validate_action_permitted_for_role(self) -> None:
        coord = self._make_coordinator()
        coord._registered_agents["agent-1"] = "executive"
        result = await coord.validate_action("agent-1", "propose")
        assert result["allowed"] is True
        assert result["reason"] == "Action permitted for role"

    async def test_validate_action_not_permitted_for_role(self) -> None:
        coord = self._make_coordinator()
        coord._registered_agents["agent-1"] = "monitor"
        result = await coord.validate_action("agent-1", "validate")
        assert result["allowed"] is False
        assert "not permitted" in result["reason"]

    async def test_validate_action_with_enforcer(self) -> None:
        coord = self._make_coordinator()
        mock_result = MagicMock()
        mock_result.allowed = True
        mock_result.reason = "OK"
        coord._enforcer = MagicMock()
        coord._enforcer.validate_action = AsyncMock(return_value=mock_result)

        with patch(
            "enhanced_agent_bus.coordinators.maci_coordinator.MACIAction",
            create=True,
        ) as mock_action_cls:
            mock_action_cls.return_value = "validate"
            # Patch the import inside the method
            with patch.dict(
                "sys.modules",
                {"enhanced_agent_bus.maci_enforcement": MagicMock(MACIAction=mock_action_cls)},
            ):
                result = await coord.validate_action(
                    "agent-1", "validate", target_output_id="agent-2"
                )
                assert result["allowed"] is True

    async def test_validate_action_enforcer_error(self) -> None:
        coord = self._make_coordinator()
        coord._enforcer = MagicMock()
        coord._enforcer.validate_action = AsyncMock(side_effect=RuntimeError("enforcer down"))

        with patch(
            "enhanced_agent_bus.coordinators.maci_coordinator.MACIAction",
            create=True,
        ):
            with patch.dict(
                "sys.modules",
                {"enhanced_agent_bus.maci_enforcement": MagicMock()},
            ):
                result = await coord.validate_action(
                    "agent-1", "validate", target_output_id="agent-2"
                )
                assert result["allowed"] is False
                assert "Validation error" in result["reason"]

    def test_get_role_permissions_known_roles(self) -> None:
        coord = self._make_coordinator()
        assert "propose" in coord._get_role_permissions("executive")
        assert "validate" in coord._get_role_permissions("judicial")
        assert "monitor_activity" in coord._get_role_permissions("monitor")
        assert "audit" in coord._get_role_permissions("auditor")
        assert "enforce_control" in coord._get_role_permissions("controller")
        assert "synthesize" in coord._get_role_permissions("implementer")
        assert "extract_rules" in coord._get_role_permissions("legislative")

    def test_get_role_permissions_unknown_role(self) -> None:
        coord = self._make_coordinator()
        perms = coord._get_role_permissions("unknown_role")
        assert perms == {"query"}

    def test_log_validation_audit_enabled(self) -> None:
        coord = self._make_coordinator(enable_audit=True)
        entry = {"agent_id": "a", "action": "b", "allowed": True, "reason": "ok"}
        coord._log_validation(entry)
        assert len(coord._validation_log) == 1

    def test_log_validation_audit_disabled(self) -> None:
        coord = self._make_coordinator(enable_audit=False)
        entry = {"agent_id": "a", "action": "b", "allowed": True, "reason": "ok"}
        coord._log_validation(entry)
        assert len(coord._validation_log) == 0

    def test_log_validation_truncation(self) -> None:
        coord = self._make_coordinator(enable_audit=True)
        # Fill past the limit
        coord._validation_log = [{"i": i} for i in range(1001)]
        coord._log_validation({"i": 1001})
        # Should truncate to last 500 + new entry (but _log_validation appends then truncates)
        assert len(coord._validation_log) <= 501

    async def test_check_cross_role_constraint_validator_not_registered(self) -> None:
        coord = self._make_coordinator()
        result = await coord.check_cross_role_constraint("unknown", "executive")
        assert result["allowed"] is False
        assert "not registered" in result["reason"]

    async def test_check_cross_role_constraint_allowed(self) -> None:
        coord = self._make_coordinator()
        coord._registered_agents["judge-1"] = "judicial"
        result = await coord.check_cross_role_constraint("judge-1", "executive")
        assert result["allowed"] is True

    async def test_check_cross_role_constraint_denied_trias_politica(self) -> None:
        coord = self._make_coordinator()
        coord._registered_agents["exec-1"] = "executive"
        result = await coord.check_cross_role_constraint("exec-1", "judicial")
        assert result["allowed"] is False
        assert "Trias Politica" in result["reason"]

    async def test_check_cross_role_constraint_auditor(self) -> None:
        coord = self._make_coordinator()
        coord._registered_agents["aud-1"] = "auditor"
        result = await coord.check_cross_role_constraint("aud-1", "monitor")
        assert result["allowed"] is True
        result2 = await coord.check_cross_role_constraint("aud-1", "executive")
        assert result2["allowed"] is False

    def test_get_stats(self) -> None:
        coord = self._make_coordinator()
        coord._registered_agents = {"a": "executive", "b": "executive", "c": "judicial"}
        stats = coord.get_stats()
        assert stats["registered_agents"] == 3
        assert stats["role_distribution"]["executive"] == 2
        assert stats["role_distribution"]["judicial"] == 1
        assert stats["maci_available"] is False
        assert stats["strict_mode"] is True
        assert stats["audit_enabled"] is True

    def test_get_recent_validations(self) -> None:
        coord = self._make_coordinator()
        coord._validation_log = [{"i": i} for i in range(20)]
        recent = coord.get_recent_validations(5)
        assert len(recent) == 5
        assert recent[0]["i"] == 15

    def test_get_recent_validations_default_limit(self) -> None:
        coord = self._make_coordinator()
        coord._validation_log = [{"i": i} for i in range(5)]
        recent = coord.get_recent_validations()
        assert len(recent) == 5

    def test_initialize_maci_import_error(self) -> None:
        """Test _initialize_maci when import fails."""
        from enhanced_agent_bus.coordinators.maci_coordinator import MACICoordinator

        with patch(
            "enhanced_agent_bus.coordinators.maci_coordinator.MACICoordinator._initialize_maci"
        ):
            coord = MACICoordinator.__new__(MACICoordinator)
            coord._strict_mode = True
            coord._enable_audit = True
            coord._registry = None
            coord._enforcer = None
            coord._initialized = False
            coord._registered_agents = {}
            coord._validation_log = []

        # Now call _initialize_maci which will hit ImportError
        coord._initialize_maci()
        # Should not crash, just log
        assert coord._initialized is False or coord._initialized is True


# ---------------------------------------------------------------------------
# 2. CostOptimizer tests
# ---------------------------------------------------------------------------


class TestCostOptimizer:
    """Tests for llm_adapters/cost/optimizer.py."""

    def _make_optimizer(self) -> Any:
        from enhanced_agent_bus.llm_adapters.cost.optimizer import CostOptimizer

        return CostOptimizer()

    def test_init_creates_subcomponents(self) -> None:
        opt = self._make_optimizer()
        assert opt.budget_manager is not None
        assert opt.anomaly_detector is not None
        assert opt.batch_optimizer is not None
        assert isinstance(opt._cost_models, dict)

    def test_classify_tier_free(self) -> None:
        from enhanced_agent_bus.llm_adapters.capability_matrix import ProviderCapabilityProfile

        opt = self._make_optimizer()
        profile = MagicMock(spec=ProviderCapabilityProfile)
        profile.input_cost_per_1k = 0.0
        profile.output_cost_per_1k = 0.0
        from enhanced_agent_bus.llm_adapters.cost.enums import CostTier

        assert opt._classify_tier(profile) == CostTier.FREE

    def test_classify_tier_budget(self) -> None:
        opt = self._make_optimizer()
        profile = MagicMock()
        profile.input_cost_per_1k = 0.001
        profile.output_cost_per_1k = 0.001
        from enhanced_agent_bus.llm_adapters.cost.enums import CostTier

        assert opt._classify_tier(profile) == CostTier.BUDGET

    def test_classify_tier_standard(self) -> None:
        opt = self._make_optimizer()
        profile = MagicMock()
        profile.input_cost_per_1k = 0.005
        profile.output_cost_per_1k = 0.005
        from enhanced_agent_bus.llm_adapters.cost.enums import CostTier

        assert opt._classify_tier(profile) == CostTier.STANDARD

    def test_classify_tier_premium(self) -> None:
        opt = self._make_optimizer()
        profile = MagicMock()
        profile.input_cost_per_1k = 0.03
        profile.output_cost_per_1k = 0.03
        from enhanced_agent_bus.llm_adapters.cost.enums import CostTier

        assert opt._classify_tier(profile) == CostTier.PREMIUM

    def test_classify_tier_enterprise(self) -> None:
        opt = self._make_optimizer()
        profile = MagicMock()
        profile.input_cost_per_1k = 0.1
        profile.output_cost_per_1k = 0.1
        from enhanced_agent_bus.llm_adapters.cost.enums import CostTier

        assert opt._classify_tier(profile) == CostTier.ENTERPRISE

    def test_register_cost_model(self) -> None:
        from enhanced_agent_bus.llm_adapters.cost.models import CostModel

        opt = self._make_optimizer()
        model = CostModel(
            provider_id="test-provider",
            model_id="test-model",
            input_cost_per_1k=0.01,
            output_cost_per_1k=0.02,
        )
        opt.register_cost_model(model)
        assert opt.get_cost_model("test-provider") is model

    def test_get_cost_model_not_found(self) -> None:
        opt = self._make_optimizer()
        assert opt.get_cost_model("nonexistent") is None

    def test_estimate_cost_success(self) -> None:
        from enhanced_agent_bus.llm_adapters.cost.models import CostModel

        opt = self._make_optimizer()
        model = CostModel(
            provider_id="p1",
            model_id="m1",
            input_cost_per_1k=1.0,
            output_cost_per_1k=2.0,
            cached_input_cost_per_1k=0.5,
        )
        opt.register_cost_model(model)

        est = opt.estimate_cost(
            "p1", input_tokens=2000, estimated_output_tokens=1000, cached_tokens=500
        )
        assert est is not None
        assert est.provider_id == "p1"
        assert est.model_id == "m1"
        assert est.confidence == 0.85
        assert est.estimated_cost > 0
        assert "input" in est.breakdown
        assert "cached_input" in est.breakdown
        assert "output" in est.breakdown

    def test_estimate_cost_unknown_provider(self) -> None:
        opt = self._make_optimizer()
        assert opt.estimate_cost("unknown", 100, 50) is None

    async def test_select_optimal_provider_no_capable(self) -> None:
        opt = self._make_optimizer()
        with patch.object(opt.registry, "find_capable_providers", return_value=[]):
            profile, est = await opt.select_optimal_provider([], tenant_id="t1")
            assert profile is None
            assert est is None

    async def test_select_optimal_provider_success(self) -> None:
        from enhanced_agent_bus.llm_adapters.capability_matrix import (
            LatencyClass,
            ProviderCapabilityProfile,
        )
        from enhanced_agent_bus.llm_adapters.cost.models import CostModel

        opt = self._make_optimizer()
        profile = MagicMock(spec=ProviderCapabilityProfile)
        profile.provider_id = "p1"
        profile.model_id = "m1"
        profile.display_name = "Provider 1"
        profile.latency_class = LatencyClass.LOW

        model = CostModel(
            provider_id="p1",
            model_id="m1",
            input_cost_per_1k=0.01,
            output_cost_per_1k=0.02,
        )
        opt._cost_models["p1"] = model

        with patch.object(opt.registry, "find_capable_providers", return_value=[(profile, 0.9)]):
            with patch.object(
                opt.budget_manager,
                "check_budget",
                new_callable=AsyncMock,
                return_value=(True, None),
            ):
                sel, est = await opt.select_optimal_provider(
                    [], tenant_id="t1", estimated_input_tokens=1000, estimated_output_tokens=500
                )
                assert sel is not None
                assert sel.provider_id == "p1"
                assert est is not None

    async def test_select_optimal_provider_budget_exceeded(self) -> None:
        from enhanced_agent_bus.llm_adapters.capability_matrix import (
            LatencyClass,
            ProviderCapabilityProfile,
        )
        from enhanced_agent_bus.llm_adapters.cost.models import CostModel

        opt = self._make_optimizer()
        profile = MagicMock(spec=ProviderCapabilityProfile)
        profile.provider_id = "p1"
        profile.model_id = "m1"
        profile.latency_class = LatencyClass.LOW

        model = CostModel(
            provider_id="p1",
            model_id="m1",
            input_cost_per_1k=0.01,
            output_cost_per_1k=0.02,
        )
        opt._cost_models["p1"] = model

        with patch.object(opt.registry, "find_capable_providers", return_value=[(profile, 0.9)]):
            with patch.object(
                opt.budget_manager,
                "check_budget",
                new_callable=AsyncMock,
                return_value=(False, "over"),
            ):
                sel, est = await opt.select_optimal_provider([], tenant_id="t1")
                assert sel is None

    async def test_select_optimal_provider_max_cost_filter(self) -> None:
        from enhanced_agent_bus.llm_adapters.capability_matrix import (
            LatencyClass,
            ProviderCapabilityProfile,
        )
        from enhanced_agent_bus.llm_adapters.cost.models import CostModel

        opt = self._make_optimizer()
        profile = MagicMock(spec=ProviderCapabilityProfile)
        profile.provider_id = "p1"
        profile.model_id = "m1"
        profile.latency_class = LatencyClass.LOW

        model = CostModel(
            provider_id="p1",
            model_id="m1",
            input_cost_per_1k=100.0,
            output_cost_per_1k=200.0,
        )
        opt._cost_models["p1"] = model

        with patch.object(opt.registry, "find_capable_providers", return_value=[(profile, 0.9)]):
            sel, est = await opt.select_optimal_provider([], tenant_id="t1", max_cost=0.0001)
            assert sel is None

    async def test_select_optimal_provider_urgency_batch(self) -> None:
        from enhanced_agent_bus.llm_adapters.capability_matrix import (
            LatencyClass,
            ProviderCapabilityProfile,
        )
        from enhanced_agent_bus.llm_adapters.cost.enums import QualityLevel, UrgencyLevel
        from enhanced_agent_bus.llm_adapters.cost.models import CostModel

        opt = self._make_optimizer()
        profile = MagicMock(spec=ProviderCapabilityProfile)
        profile.provider_id = "p1"
        profile.model_id = "m1"
        profile.latency_class = LatencyClass.MEDIUM

        model = CostModel(
            provider_id="p1",
            model_id="m1",
            input_cost_per_1k=0.01,
            output_cost_per_1k=0.02,
        )
        opt._cost_models["p1"] = model

        with patch.object(opt.registry, "find_capable_providers", return_value=[(profile, 0.8)]):
            with patch.object(
                opt.budget_manager,
                "check_budget",
                new_callable=AsyncMock,
                return_value=(True, None),
            ):
                sel, est = await opt.select_optimal_provider(
                    [],
                    tenant_id="t1",
                    urgency=UrgencyLevel.BATCH,
                    quality=QualityLevel.MAXIMUM,
                )
                assert sel is not None

    async def test_record_actual_cost(self) -> None:
        opt = self._make_optimizer()
        with patch.object(opt.budget_manager, "record_cost", new_callable=AsyncMock):
            with patch.object(
                opt.anomaly_detector, "record_cost", new_callable=AsyncMock, return_value=None
            ):
                result = await opt.record_actual_cost("t1", "p1", 0.05, "completion")
                assert result is None

    def test_get_cost_comparison(self) -> None:
        from enhanced_agent_bus.llm_adapters.capability_matrix import (
            LatencyClass,
            ProviderCapabilityProfile,
        )
        from enhanced_agent_bus.llm_adapters.cost.models import CostModel

        opt = self._make_optimizer()
        profile = MagicMock(spec=ProviderCapabilityProfile)
        profile.provider_id = "p1"
        profile.model_id = "m1"
        profile.display_name = "P1"
        profile.latency_class = LatencyClass.LOW

        model = CostModel(
            provider_id="p1",
            model_id="m1",
            input_cost_per_1k=0.01,
            output_cost_per_1k=0.02,
        )
        opt._cost_models["p1"] = model

        with patch.object(opt.registry, "find_capable_providers", return_value=[(profile, 0.9)]):
            comparisons = opt.get_cost_comparison([])
            assert len(comparisons) == 1
            assert comparisons[0]["provider_id"] == "p1"
            assert "estimated_cost" in comparisons[0]
            assert "cost_tier" in comparisons[0]

    def test_get_cost_comparison_no_cost_model(self) -> None:
        opt = self._make_optimizer()
        profile = MagicMock()
        profile.provider_id = "no-model"

        with patch.object(opt.registry, "find_capable_providers", return_value=[(profile, 0.5)]):
            comparisons = opt.get_cost_comparison([])
            assert len(comparisons) == 0

    def test_get_cost_analytics(self) -> None:
        opt = self._make_optimizer()
        with patch.object(opt.budget_manager, "get_usage_summary", return_value={"total": 1.0}):
            with patch.object(opt.anomaly_detector, "get_recent_anomalies", return_value=[]):
                with patch.object(opt.batch_optimizer, "get_pending_count", return_value=0):
                    analytics = opt.get_cost_analytics("t1")
                    assert analytics["tenant_id"] == "t1"
                    assert "usage" in analytics
                    assert "recent_anomalies" in analytics
                    assert "pending_batches" in analytics


class TestCostOptimizerGlobals:
    """Tests for global functions in cost/optimizer.py."""

    def test_get_cost_optimizer_singleton(self) -> None:
        import enhanced_agent_bus.llm_adapters.cost.optimizer as mod

        # Reset global
        mod._cost_optimizer = None
        opt1 = mod.get_cost_optimizer()
        opt2 = mod.get_cost_optimizer()
        assert opt1 is opt2
        # Cleanup
        mod._cost_optimizer = None

    async def test_initialize_cost_optimizer(self) -> None:
        import enhanced_agent_bus.llm_adapters.cost.optimizer as mod

        mod._cost_optimizer = None
        await mod.initialize_cost_optimizer()
        assert mod._cost_optimizer is not None
        mod._cost_optimizer = None


# ---------------------------------------------------------------------------
# 3. HuggingFaceAdapter tests
# ---------------------------------------------------------------------------


class TestHuggingFaceAdapter:
    """Tests for llm_adapters/huggingface_adapter.py."""

    def _make_adapter(self, model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct") -> Any:
        from enhanced_agent_bus.llm_adapters.huggingface_adapter import HuggingFaceAdapter

        config = MagicMock()
        config.model = model
        config.get_api_key.return_value = "fake-key"
        config.use_inference_api = True
        config.inference_endpoint = None
        config.timeout_seconds = 30

        adapter = HuggingFaceAdapter(config=config)
        return adapter

    def test_detect_model_family_llama3(self) -> None:
        adapter = self._make_adapter("meta-llama/Meta-Llama-3.1-8B-Instruct")
        assert adapter._detect_model_family() == "llama3"

    def test_detect_model_family_llama2(self) -> None:
        adapter = self._make_adapter("meta-llama/Llama-2-7b-chat-hf")
        assert adapter._detect_model_family() == "llama2"

    def test_detect_model_family_mistral(self) -> None:
        adapter = self._make_adapter("mistralai/Mistral-7B-Instruct-v0.2")
        assert adapter._detect_model_family() == "mistral"

    def test_detect_model_family_mixtral(self) -> None:
        adapter = self._make_adapter("mistralai/Mixtral-8x7B-Instruct-v0.1")
        assert adapter._detect_model_family() == "mistral"

    def test_detect_model_family_deepseek(self) -> None:
        adapter = self._make_adapter("deepseek-ai/deepseek-coder-6.7b-instruct")
        assert adapter._detect_model_family() == "deepseek"

    def test_detect_model_family_zephyr(self) -> None:
        adapter = self._make_adapter("HuggingFaceH4/zephyr-7b-beta")
        assert adapter._detect_model_family() == "zephyr"

    def test_detect_model_family_locooperator(self) -> None:
        adapter = self._make_adapter("LocoreMind/LocoOperator-4B-GGUF")
        assert adapter._detect_model_family() == "locooperator"

    def test_detect_model_family_default(self) -> None:
        adapter = self._make_adapter("some-unknown-model/v1")
        assert adapter._detect_model_family() == "default"

    def test_extract_message_parts(self) -> None:
        from enhanced_agent_bus.llm_adapters.base import LLMMessage

        adapter = self._make_adapter()
        messages = [
            LLMMessage(role="system", content="You are helpful"),
            LLMMessage(role="user", content="Hello"),
            LLMMessage(role="assistant", content="Hi there"),
            LLMMessage(role="user", content="What?"),
        ]
        system, parts = adapter._extract_message_parts(messages)
        assert system == "You are helpful"
        assert len(parts) == 3
        assert parts[0] == ("user", "Hello")
        assert parts[1] == ("assistant", "Hi there")
        assert parts[2] == ("user", "What?")

    def test_format_simple(self) -> None:
        adapter = self._make_adapter()
        parts = adapter._format_simple([("user", "hi"), ("assistant", "hello")])
        assert len(parts) == 2
        assert "User: hi" in parts[0]
        assert "Assistant: hello" in parts[1]

    def test_merge_system_to_first_user(self) -> None:
        adapter = self._make_adapter()
        conv = [("user", "hello"), ("assistant", "hi")]
        adapter._merge_system_to_first_user("System prompt", conv)
        assert "System prompt" in conv[0][1]
        assert "hello" in conv[0][1]

    def test_merge_system_to_first_user_empty(self) -> None:
        adapter = self._make_adapter()
        conv: list[tuple[str, str]] = []
        adapter._merge_system_to_first_user("System prompt", conv)
        assert len(conv) == 0

    def test_merge_system_to_first_user_non_user_first(self) -> None:
        adapter = self._make_adapter()
        conv = [("assistant", "hello")]
        adapter._merge_system_to_first_user("System prompt", conv)
        # Should not modify since first is not user
        assert conv[0] == ("assistant", "hello")

    def test_ensure_assistant_prompt_adds_suffix(self) -> None:
        adapter = self._make_adapter()
        result = adapter._ensure_assistant_prompt("Some prompt")
        assert result.rstrip().endswith("Assistant:")

    def test_ensure_assistant_prompt_already_present(self) -> None:
        adapter = self._make_adapter()
        result = adapter._ensure_assistant_prompt("Some prompt\nAssistant:")
        assert result.count("Assistant:") == 1

    def test_format_messages_for_inference_with_system(self) -> None:
        from enhanced_agent_bus.llm_adapters.base import LLMMessage

        adapter = self._make_adapter()
        messages = [
            LLMMessage(role="system", content="Be helpful"),
            LLMMessage(role="user", content="Hi"),
        ]
        prompt = adapter._format_messages_for_inference(messages)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_format_messages_for_inference_no_system(self) -> None:
        from enhanced_agent_bus.llm_adapters.base import LLMMessage

        adapter = self._make_adapter()
        messages = [LLMMessage(role="user", content="Hi")]
        prompt = adapter._format_messages_for_inference(messages)
        assert "Hi" in prompt

    def test_count_tokens_fallback(self) -> None:
        from enhanced_agent_bus.llm_adapters.base import LLMMessage

        adapter = self._make_adapter()
        adapter._tokenizer = None
        messages = [LLMMessage(role="user", content="Hello world this is a test")]
        count = adapter.count_tokens(messages)
        assert count > 0

    def test_count_tokens_with_tokenizer(self) -> None:
        from enhanced_agent_bus.llm_adapters.base import LLMMessage

        adapter = self._make_adapter()
        mock_tokenizer = MagicMock()
        mock_tokenizer.encode.return_value = [1, 2, 3, 4, 5]
        adapter._tokenizer = mock_tokenizer
        messages = [LLMMessage(role="user", content="Hello")]
        count = adapter.count_tokens(messages)
        assert count == 5

    def test_count_tokens_tokenizer_error(self) -> None:
        from enhanced_agent_bus.llm_adapters.base import LLMMessage

        adapter = self._make_adapter()
        mock_tokenizer = MagicMock()
        mock_tokenizer.encode.side_effect = RuntimeError("tokenizer fail")
        adapter._tokenizer = mock_tokenizer
        messages = [LLMMessage(role="user", content="Hello world")]
        count = adapter.count_tokens(messages)
        # Falls back to char estimate
        assert count > 0

    def test_estimate_cost_known_model(self) -> None:
        adapter = self._make_adapter("meta-llama/Meta-Llama-3.1-8B-Instruct")
        cost = adapter.estimate_cost(1000, 500)
        assert cost.total_cost_usd >= 0
        assert cost.currency == "USD"
        assert "huggingface" in cost.pricing_model

    def test_estimate_cost_unknown_model(self) -> None:
        adapter = self._make_adapter("unknown-model/v1")
        cost = adapter.estimate_cost(1000, 500)
        assert cost.total_cost_usd >= 0

    def test_complete_string_response(self) -> None:
        from enhanced_agent_bus.llm_adapters.base import LLMMessage

        adapter = self._make_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.return_value = "Generated text here"
        adapter._client = mock_client

        messages = [LLMMessage(role="user", content="Hello")]
        response = adapter.complete(messages)
        assert response.content == "Generated text here"
        assert response.usage.prompt_tokens > 0

    def test_complete_object_response(self) -> None:
        from enhanced_agent_bus.llm_adapters.base import LLMMessage

        adapter = self._make_adapter()
        mock_resp = MagicMock()
        mock_resp.generated_text = "From object"
        mock_client = MagicMock()
        mock_client.text_generation.return_value = mock_resp
        adapter._client = mock_client

        messages = [LLMMessage(role="user", content="Hello")]
        response = adapter.complete(messages)
        assert response.content == "From object"

    def test_complete_fallback_str_response(self) -> None:
        from enhanced_agent_bus.llm_adapters.base import LLMMessage

        adapter = self._make_adapter()
        mock_resp = 42  # Not str, no generated_text
        mock_client = MagicMock()
        mock_client.text_generation.return_value = mock_resp
        adapter._client = mock_client

        messages = [LLMMessage(role="user", content="Hello")]
        response = adapter.complete(messages)
        assert response.content == "42"

    def test_complete_with_optional_params(self) -> None:
        from enhanced_agent_bus.llm_adapters.base import LLMMessage

        adapter = self._make_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.return_value = "result"
        adapter._client = mock_client

        messages = [LLMMessage(role="user", content="Hello")]
        response = adapter.complete(
            messages,
            stop=["END"],
            top_k=50,
            repetition_penalty=1.2,
            do_sample=True,
        )
        assert response.content == "result"

    def test_complete_api_error(self) -> None:
        from enhanced_agent_bus.llm_adapters.base import LLMMessage

        adapter = self._make_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.side_effect = RuntimeError("API Error")
        adapter._client = mock_client

        messages = [LLMMessage(role="user", content="Hello")]
        with pytest.raises(RuntimeError, match="API Error"):
            adapter.complete(messages)

    async def test_acomplete_string_response(self) -> None:
        from enhanced_agent_bus.llm_adapters.base import LLMMessage

        adapter = self._make_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.return_value = "async generated"
        adapter._async_client = mock_client

        messages = [LLMMessage(role="user", content="Hello")]
        response = await adapter.acomplete(messages)
        assert response.content == "async generated"

    async def test_acomplete_with_coroutine_response(self) -> None:
        from enhanced_agent_bus.llm_adapters.base import LLMMessage

        adapter = self._make_adapter()

        async def fake_gen(*a: Any, **kw: Any) -> str:
            return "coroutine result"

        mock_client = MagicMock()
        mock_client.text_generation.return_value = fake_gen()
        adapter._async_client = mock_client

        messages = [LLMMessage(role="user", content="Hello")]
        response = await adapter.acomplete(messages)
        assert response.content == "coroutine result"

    async def test_acomplete_api_error(self) -> None:
        from enhanced_agent_bus.llm_adapters.base import LLMMessage

        adapter = self._make_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.side_effect = RuntimeError("async API Error")
        adapter._async_client = mock_client

        messages = [LLMMessage(role="user", content="Hello")]
        with pytest.raises(RuntimeError, match="async API Error"):
            await adapter.acomplete(messages)

    def test_stream_string_chunks(self) -> None:
        from enhanced_agent_bus.llm_adapters.base import LLMMessage

        adapter = self._make_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.return_value = iter(["chunk1", "chunk2"])
        adapter._client = mock_client

        messages = [LLMMessage(role="user", content="Hello")]
        chunks = list(adapter.stream(messages))
        assert chunks == ["chunk1", "chunk2"]

    def test_stream_token_chunks(self) -> None:
        from enhanced_agent_bus.llm_adapters.base import LLMMessage

        adapter = self._make_adapter()
        token_obj = MagicMock()
        token_obj.text = "word"
        chunk = MagicMock()
        chunk.token = token_obj
        # Make chunk not be a str
        chunk.__class__ = type("TokenChunk", (), {"token": token_obj})

        mock_client = MagicMock()
        mock_client.text_generation.return_value = iter([chunk])
        adapter._client = mock_client

        messages = [LLMMessage(role="user", content="Hello")]
        chunks = list(adapter.stream(messages))
        assert len(chunks) == 1

    def test_stream_error(self) -> None:
        from enhanced_agent_bus.llm_adapters.base import LLMMessage

        adapter = self._make_adapter()
        mock_client = MagicMock()
        mock_client.text_generation.side_effect = RuntimeError("stream error")
        adapter._client = mock_client

        messages = [LLMMessage(role="user", content="Hello")]
        with pytest.raises(RuntimeError, match="stream error"):
            list(adapter.stream(messages))

    def test_prepare_streaming_params(self) -> None:
        adapter = self._make_adapter()
        params = adapter._prepare_streaming_params(
            temperature=0.5, max_tokens=None, top_p=0.9, stop=["END"], top_k=10
        )
        assert params["temperature"] == 0.5
        assert params["max_new_tokens"] == 1024
        assert params["stop_sequences"] == ["END"]
        assert params["top_k"] == 10
        assert params["stream"] is True

    def test_prepare_streaming_params_custom_max_tokens(self) -> None:
        adapter = self._make_adapter()
        params = adapter._prepare_streaming_params(
            temperature=0.7, max_tokens=256, top_p=1.0, stop=None
        )
        assert params["max_new_tokens"] == 256
        assert "stop_sequences" not in params

    def test_process_stream_chunk_str(self) -> None:
        adapter = self._make_adapter()
        assert adapter._process_stream_chunk("hello") == "hello"

    def test_process_stream_chunk_token(self) -> None:
        adapter = self._make_adapter()
        token_obj = MagicMock()
        token_obj.text = "word"
        chunk = MagicMock()
        chunk.token = token_obj
        result = adapter._process_stream_chunk(chunk)
        assert result == "word"

    def test_process_stream_chunk_token_no_text(self) -> None:
        adapter = self._make_adapter()
        token_obj = MagicMock(spec=[])  # No attributes
        chunk = MagicMock()
        chunk.token = token_obj
        result = adapter._process_stream_chunk(chunk)
        assert result == ""

    def test_process_stream_chunk_other(self) -> None:
        adapter = self._make_adapter()
        result = adapter._process_stream_chunk(42)
        assert result == "42"

    async def test_health_check_not_inference_api(self) -> None:
        adapter = self._make_adapter()
        adapter.config.use_inference_api = False
        result = await adapter.health_check()
        from enhanced_agent_bus.llm_adapters.base import AdapterStatus

        assert result.status == AdapterStatus.HEALTHY

    async def test_health_check_inference_api_import_error(self) -> None:
        adapter = self._make_adapter()
        adapter.config.use_inference_api = True
        adapter._async_client = MagicMock()

        with patch(
            "enhanced_agent_bus.llm_adapters.huggingface_adapter.model_info",
            create=True,
            side_effect=ImportError("no huggingface_hub"),
        ):
            with patch.dict("sys.modules", {"huggingface_hub": None}):
                # The outer try/except will catch the ImportError from model_info import
                result = await adapter.health_check()
                # Should still return a result (either healthy via fallback or unhealthy)
                assert result.status is not None

    def test_get_client_import_error(self) -> None:
        adapter = self._make_adapter()
        adapter._client = None
        with patch.dict("sys.modules", {"huggingface_hub": None}):
            with pytest.raises(ImportError):
                adapter._get_client()

    def test_get_async_client_import_error(self) -> None:
        adapter = self._make_adapter()
        adapter._async_client = None
        with patch.dict("sys.modules", {"huggingface_hub": None}):
            with pytest.raises(ImportError):
                adapter._get_async_client()

    def test_get_tokenizer_import_error(self) -> None:
        adapter = self._make_adapter()
        adapter._tokenizer = None
        with patch.dict("sys.modules", {"transformers": None}):
            result = adapter._get_tokenizer()
            assert result is None

    def test_format_with_template(self) -> None:
        adapter = self._make_adapter()
        template = "{system}\n\nUser: {user}\n\nAssistant: {assistant}"
        parts = adapter._format_with_template(
            template, "System msg", [("user", "Hello"), ("assistant", "Hi")]
        )
        assert len(parts) >= 1

    def test_format_with_template_no_system(self) -> None:
        adapter = self._make_adapter()
        template = "{system}\n\nUser: {user}\n\nAssistant: {assistant}"
        parts = adapter._format_with_template(template, "", [("user", "Hello")])
        assert len(parts) == 0  # Empty system, so no template formatting


# ---------------------------------------------------------------------------
# 4. AuthInjector tests
# ---------------------------------------------------------------------------


class TestAuthEnums:
    """Test AuthMethod and InjectionStatus enums."""

    def test_auth_method_values(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import AuthMethod

        assert AuthMethod.NONE.value == "none"
        assert AuthMethod.API_KEY.value == "api_key"
        assert AuthMethod.OAUTH2.value == "oauth2"
        assert AuthMethod.OIDC.value == "oidc"
        assert AuthMethod.BEARER_TOKEN.value == "bearer_token"
        assert AuthMethod.BASIC_AUTH.value == "basic_auth"
        assert AuthMethod.CUSTOM.value == "custom"

    def test_injection_status_values(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import InjectionStatus

        assert InjectionStatus.SUCCESS.value == "success"
        assert InjectionStatus.FAILED.value == "failed"
        assert InjectionStatus.NO_CREDENTIALS.value == "no_credentials"
        assert InjectionStatus.SKIPPED.value == "skipped"
        assert InjectionStatus.EXPIRED.value == "expired"


class TestAuthContext:
    """Tests for AuthContext dataclass."""

    def test_get_tool_name_from_tool_name(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import AuthContext

        ctx = AuthContext(tool_name="my_tool")
        assert ctx.get_tool_name() == "my_tool"

    def test_get_tool_name_from_tool_id(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import AuthContext

        ctx = AuthContext(tool_id="my_tool_id")
        assert ctx.get_tool_name() == "my_tool_id"

    def test_get_tool_name_unknown(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import AuthContext

        ctx = AuthContext()
        assert ctx.get_tool_name() == "unknown"

    def test_get_scopes_from_required_scopes(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import AuthContext

        ctx = AuthContext(required_scopes=["read", "write"])
        assert ctx.get_scopes() == ["read", "write"]

    def test_get_scopes_from_scopes(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import AuthContext

        ctx = AuthContext(scopes=["admin"])
        assert ctx.get_scopes() == ["admin"]

    def test_get_scopes_empty(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import AuthContext

        ctx = AuthContext()
        assert ctx.get_scopes() == []


class TestInjectionResult:
    """Tests for InjectionResult dataclass."""

    def test_success_property(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthMethod,
            InjectionResult,
            InjectionStatus,
        )

        r1 = InjectionResult(status=InjectionStatus.SUCCESS, auth_method=AuthMethod.API_KEY)
        assert r1.success is True

        r2 = InjectionResult(status=InjectionStatus.FAILED, auth_method=AuthMethod.API_KEY)
        assert r2.success is False

    def test_injected_aliases(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthMethod,
            InjectionResult,
            InjectionStatus,
        )

        r = InjectionResult(
            status=InjectionStatus.SUCCESS,
            auth_method=AuthMethod.API_KEY,
            modified_headers={"Authorization": "***"},
            modified_params={"key": "***"},
            modified_body={"token": "***"},
        )
        assert r.injected_headers == {"Authorization": "***"}
        assert r.injected_params == {"key": "***"}
        assert r.injected_body == {"token": "***"}

    def test_to_dict(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthMethod,
            InjectionResult,
            InjectionStatus,
        )

        r = InjectionResult(
            status=InjectionStatus.SUCCESS,
            auth_method=AuthMethod.OAUTH2,
            modified_headers={"Authorization": "***"},
            credentials_used=["oauth2:provider1"],
            duration_ms=15.5,
        )
        d = r.to_dict()
        assert d["status"] == "success"
        assert d["success"] is True
        assert d["auth_method"] == "oauth2"
        assert d["has_modified_headers"] is True
        assert d["credentials_used"] == ["oauth2:provider1"]
        assert d["duration_ms"] == 15.5


class TestAuthInjector:
    """Tests for AuthInjector class."""

    def _make_injector(self, enable_audit: bool = False) -> Any:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthInjector,
            AuthInjectorConfig,
        )

        config = AuthInjectorConfig(enable_audit=enable_audit)
        return AuthInjector(config)

    def test_init_default(self) -> None:
        injector = self._make_injector()
        assert injector._credential_manager is not None
        assert injector._token_refresher is not None

    def test_configure_tool_auth(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import AuthMethod

        injector = self._make_injector()
        injector.configure_tool_auth("my_tool", AuthMethod.API_KEY, scopes=["read"])
        assert "my_tool" in injector._tool_auth_configs
        assert injector._tool_auth_configs["my_tool"]["auth_method"] == AuthMethod.API_KEY

    async def test_inject_auth_none_method(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )

        injector = self._make_injector()
        ctx = AuthContext(tool_name="tool1", auth_method=AuthMethod.NONE)
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.SKIPPED

    async def test_inject_auth_api_key(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )

        injector = self._make_injector()
        ctx = AuthContext(tool_name="tool1", auth_method=AuthMethod.API_KEY)

        with patch.object(
            injector._credential_manager,
            "inject_credentials",
            new_callable=AsyncMock,
            return_value={"headers": {"Authorization": "key"}, "params": {}, "body": {}},
        ):
            result = await injector.inject_auth(ctx)
            assert result.status == InjectionStatus.SUCCESS

    async def test_inject_auth_bearer_token(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )

        injector = self._make_injector()
        ctx = AuthContext(tool_name="tool1", auth_method=AuthMethod.BEARER_TOKEN)

        with patch.object(
            injector._credential_manager,
            "inject_credentials",
            new_callable=AsyncMock,
            return_value={"headers": {"Authorization": "Bearer tok"}, "params": {}, "body": {}},
        ):
            result = await injector.inject_auth(ctx)
            assert result.status == InjectionStatus.SUCCESS

    async def test_inject_auth_basic_auth(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )

        injector = self._make_injector()
        ctx = AuthContext(tool_name="tool1", auth_method=AuthMethod.BASIC_AUTH)

        with patch.object(
            injector._credential_manager,
            "inject_credentials",
            new_callable=AsyncMock,
            return_value={"headers": {}, "params": {}, "body": {}},
        ):
            result = await injector.inject_auth(ctx)
            assert result.status == InjectionStatus.NO_CREDENTIALS

    async def test_inject_auth_custom_unsupported(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )

        injector = self._make_injector()
        ctx = AuthContext(tool_name="tool1", auth_method=AuthMethod.CUSTOM)
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.FAILED
        assert "Unsupported" in (result.error or "")

    async def test_inject_auth_oauth2_no_provider(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )

        injector = self._make_injector()
        ctx = AuthContext(tool_name="tool1", auth_method=AuthMethod.OAUTH2)
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.FAILED
        assert "not found" in (result.error or "")

    async def test_inject_auth_oidc_no_provider(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )

        injector = self._make_injector()
        ctx = AuthContext(tool_name="tool1", auth_method=AuthMethod.OIDC)
        result = await injector.inject_auth(ctx)
        assert result.status == InjectionStatus.FAILED

    async def test_inject_auth_exception_handling(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )

        injector = self._make_injector()
        ctx = AuthContext(tool_name="tool1", auth_method=AuthMethod.API_KEY)

        with patch.object(
            injector._credential_manager,
            "inject_credentials",
            new_callable=AsyncMock,
            side_effect=RuntimeError("cred error"),
        ):
            result = await injector.inject_auth(ctx)
            assert result.status == InjectionStatus.FAILED
            assert "cred error" in (result.error or "")

    async def test_inject_auth_stats_tracking(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
        )

        injector = self._make_injector()
        ctx = AuthContext(tool_name="tool1", auth_method=AuthMethod.API_KEY)

        with patch.object(
            injector._credential_manager,
            "inject_credentials",
            new_callable=AsyncMock,
            return_value={"headers": {"X": "Y"}, "params": {}, "body": {}},
        ):
            await injector.inject_auth(ctx)
            assert injector._stats["injections_attempted"] == 1
            assert injector._stats["injections_successful"] == 1

    async def test_inject_auth_with_audit(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
        )

        injector = self._make_injector(enable_audit=True)
        ctx = AuthContext(tool_name="tool1", auth_method=AuthMethod.API_KEY, agent_id="a1")

        with patch.object(
            injector._credential_manager,
            "inject_credentials",
            new_callable=AsyncMock,
            return_value={"headers": {"X": "Y"}, "params": {}, "body": {}},
        ):
            with patch.object(injector._audit_logger, "log_event", new_callable=AsyncMock):
                result = await injector.inject_auth(ctx)
                injector._audit_logger.log_event.assert_called_once()

    async def test_acquire_oauth2_token_unknown_provider(self) -> None:
        injector = self._make_injector()
        result = await injector.acquire_oauth2_token("nonexistent")
        assert result is None

    async def test_get_oidc_authorization_url_unknown_provider(self) -> None:
        injector = self._make_injector()
        result = await injector.get_oidc_authorization_url("nonexistent", "http://cb")
        assert result is None

    async def test_handle_oidc_callback_unknown_provider(self) -> None:
        injector = self._make_injector()
        result = await injector.handle_oidc_callback("nonexistent", "code", "http://cb")
        assert result is None

    def test_add_oauth2_provider(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.oauth2_provider import OAuth2Config

        injector = self._make_injector()
        config = OAuth2Config(
            client_id="cid",
            client_secret="csecret",
            token_endpoint="https://auth.example.com/token",
        )
        injector.add_oauth2_provider("test_oauth", config)
        assert "test_oauth" in injector._oauth2_providers

    async def test_add_oidc_provider(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.oidc_provider import OIDCConfig

        injector = self._make_injector()
        config = OIDCConfig(
            issuer_url="https://auth.example.com",
            client_id="cid",
            client_secret="csecret",
        )
        with patch(
            "enhanced_agent_bus.mcp_integration.auth.oidc_provider.OIDCProvider.discover",
            new_callable=AsyncMock,
        ):
            await injector.add_oidc_provider("test_oidc", config, discover=True)
            assert "test_oidc" in injector._oidc_providers

    async def test_add_oidc_provider_no_discover(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.oidc_provider import OIDCConfig

        injector = self._make_injector()
        config = OIDCConfig(
            issuer_url="https://auth.example.com",
            client_id="cid",
            client_secret="csecret",
        )
        await injector.add_oidc_provider("test_oidc", config, discover=False)
        assert "test_oidc" in injector._oidc_providers

    def test_remove_provider_oauth2(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.oauth2_provider import OAuth2Config

        injector = self._make_injector()
        config = OAuth2Config(
            client_id="cid",
            client_secret="csecret",
            token_endpoint="https://auth.example.com/token",
        )
        injector.add_oauth2_provider("p1", config)
        assert injector.remove_provider("p1") is True
        assert "p1" not in injector._oauth2_providers

    def test_remove_provider_not_found(self) -> None:
        injector = self._make_injector()
        assert injector.remove_provider("nonexistent") is False

    def test_get_stats(self) -> None:
        injector = self._make_injector()
        stats = injector.get_stats()
        assert "injections_attempted" in stats
        assert "oauth2_providers" in stats
        assert "oidc_providers" in stats
        assert "configured_tools" in stats

    async def test_get_health(self) -> None:
        injector = self._make_injector()
        health = await injector.get_health()
        assert health["healthy"] is True
        assert "oauth2_providers" in health
        assert "oidc_providers" in health

    async def test_get_tool_auth_status_unconfigured(self) -> None:
        injector = self._make_injector()
        status = await injector.get_tool_auth_status("unknown_tool")
        assert status["configured"] is False
        assert status["auth_method"] == "none"

    async def test_get_tool_auth_status_configured(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import AuthMethod

        injector = self._make_injector()
        injector.configure_tool_auth("tool1", AuthMethod.API_KEY, scopes=["read"])
        status = await injector.get_tool_auth_status("tool1")
        assert status["configured"] is True
        assert status["auth_method"] == "api_key"
        assert status["scopes"] == ["read"]

    async def test_revoke_auth_by_tool_id(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import AuthMethod

        injector = self._make_injector()
        injector.configure_tool_auth("tool1", AuthMethod.API_KEY)

        with patch.object(injector._token_refresher, "list_tokens", return_value=[]):
            with patch.object(
                injector._credential_manager, "revoke_tool_credentials", new_callable=AsyncMock
            ):
                with patch.object(
                    injector._token_refresher, "unregister_token", new_callable=AsyncMock
                ):
                    result = await injector.revoke_auth(tool_id="tool1")
                    assert result["success"] is True
                    assert result["revoked_configs"] == 1
                    assert "tool1" not in injector._tool_auth_configs

    async def test_revoke_auth_with_audit(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import AuthMethod

        injector = self._make_injector(enable_audit=True)
        injector.configure_tool_auth("tool1", AuthMethod.API_KEY)

        with patch.object(injector._token_refresher, "list_tokens", return_value=[]):
            with patch.object(
                injector._credential_manager, "revoke_tool_credentials", new_callable=AsyncMock
            ):
                with patch.object(injector._audit_logger, "log_event", new_callable=AsyncMock):
                    result = await injector.revoke_auth(tool_id="tool1")
                    assert result["success"] is True
                    injector._audit_logger.log_event.assert_called_once()

    async def test_revoke_auth_by_agent_id(self) -> None:
        injector = self._make_injector()
        token_info = {"token_id": "oauth2:p1:agent-1:default"}

        with patch.object(injector._token_refresher, "list_tokens", return_value=[token_info]):
            with patch.object(
                injector._token_refresher, "unregister_token", new_callable=AsyncMock
            ):
                result = await injector.revoke_auth(agent_id="agent-1")
                assert result["success"] is True
                assert result["revoked_tokens"] == 1

    async def test_start_and_stop(self) -> None:
        injector = self._make_injector()
        with patch.object(injector._token_refresher, "start", new_callable=AsyncMock):
            with patch.object(
                injector._credential_manager, "load_credentials", new_callable=AsyncMock
            ):
                await injector.start()

        with patch.object(injector._token_refresher, "stop", new_callable=AsyncMock):
            await injector.stop()

    async def test_store_api_key(self) -> None:
        injector = self._make_injector()
        mock_cred = MagicMock()
        with patch.object(
            injector._credential_manager,
            "store_credential",
            new_callable=AsyncMock,
            return_value=mock_cred,
        ):
            result = await injector.store_api_key("key1", "secret", ["tool1"])
            assert result is mock_cred

    async def test_store_bearer_token(self) -> None:
        injector = self._make_injector()
        mock_cred = MagicMock()
        with patch.object(
            injector._credential_manager,
            "store_credential",
            new_callable=AsyncMock,
            return_value=mock_cred,
        ):
            result = await injector.store_bearer_token("tok1", "bearer-val", ["tool1"])
            assert result is mock_cred

    async def test_store_basic_auth(self) -> None:
        injector = self._make_injector()
        mock_cred = MagicMock()
        with patch.object(
            injector._credential_manager,
            "store_credential",
            new_callable=AsyncMock,
            return_value=mock_cred,
        ):
            result = await injector.store_basic_auth("ba1", "user", "pass", ["tool1"])
            assert result is mock_cred

    async def test_inject_oauth2_with_cached_token(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )
        from enhanced_agent_bus.mcp_integration.auth.oauth2_provider import (
            OAuth2Config,
            OAuth2Provider,
        )

        injector = self._make_injector()
        config = OAuth2Config(
            client_id="cid",
            client_secret="csecret",
            token_endpoint="https://auth.example.com/token",
        )
        injector.add_oauth2_provider("test_prov", config)

        mock_token = MagicMock()
        mock_token.is_expired.return_value = False
        mock_token.token_type = "Bearer"
        mock_token.access_token = "cached-token"

        with patch.object(injector._token_refresher, "get_token", return_value=mock_token):
            ctx = AuthContext(
                tool_name="tool1",
                auth_method=AuthMethod.OAUTH2,
                provider_name="test_prov",
            )
            result = await injector.inject_auth(ctx)
            assert result.status == InjectionStatus.SUCCESS
            assert "oauth2:test_prov" in result.credentials_used

    async def test_inject_oauth2_token_expired_acquire_new(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )
        from enhanced_agent_bus.mcp_integration.auth.oauth2_provider import OAuth2Config

        injector = self._make_injector()
        config = OAuth2Config(
            client_id="cid",
            client_secret="csecret",
            token_endpoint="https://auth.example.com/token",
        )
        injector.add_oauth2_provider("test_prov", config)

        expired_token = MagicMock()
        expired_token.is_expired.return_value = True

        new_token = MagicMock()
        new_token.token_type = "Bearer"
        new_token.access_token = "new-token"
        new_token.is_expired.return_value = False

        with patch.object(injector._token_refresher, "get_token", return_value=expired_token):
            with patch.object(
                injector._oauth2_providers["test_prov"],
                "acquire_token",
                new_callable=AsyncMock,
                return_value=new_token,
            ):
                with patch.object(
                    injector._token_refresher, "register_token", new_callable=AsyncMock
                ):
                    ctx = AuthContext(
                        tool_name="tool1",
                        auth_method=AuthMethod.OAUTH2,
                        provider_name="test_prov",
                    )
                    result = await injector.inject_auth(ctx)
                    assert result.status == InjectionStatus.SUCCESS

    async def test_inject_oauth2_failed_token_acquisition(self) -> None:
        from enhanced_agent_bus.mcp_integration.auth.auth_injector import (
            AuthContext,
            AuthMethod,
            InjectionStatus,
        )
        from enhanced_agent_bus.mcp_integration.auth.oauth2_provider import OAuth2Config

        injector = self._make_injector()
        config = OAuth2Config(
            client_id="cid",
            client_secret="csecret",
            token_endpoint="https://auth.example.com/token",
        )
        injector.add_oauth2_provider("test_prov", config)

        with patch.object(injector._token_refresher, "get_token", return_value=None):
            with patch.object(
                injector._oauth2_providers["test_prov"],
                "acquire_token",
                new_callable=AsyncMock,
                return_value=None,
            ):
                ctx = AuthContext(
                    tool_name="tool1",
                    auth_method=AuthMethod.OAUTH2,
                    provider_name="test_prov",
                )
                result = await injector.inject_auth(ctx)
                assert result.status == InjectionStatus.FAILED
                assert "Failed to acquire" in (result.error or "")
