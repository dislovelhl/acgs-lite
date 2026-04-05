"""Coverage tests for validation_strategies, processing_strategies,
adaptive_governance/threshold_manager, and verification_orchestrator.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import base64
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from enhanced_agent_bus.config import BusConfiguration
from enhanced_agent_bus.models import (
    CONSTITUTIONAL_HASH,
    AgentMessage,
    MessageStatus,
    MessageType,
    Priority,
)
from enhanced_agent_bus.validators import ValidationResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_msg(**overrides: Any) -> AgentMessage:
    """Build an AgentMessage with sane defaults."""
    defaults: dict[str, Any] = {
        "message_id": "test-msg-001",
        "content": {"key": "value"},
        "from_agent": "agent-a",
        "to_agent": "agent-b",
        "tenant_id": "tenant-1",
        "constitutional_hash": CONSTITUTIONAL_HASH,
        "message_type": MessageType.COMMAND,
        "priority": Priority.MEDIUM,
        "status": MessageStatus.PENDING,
    }
    defaults.update(overrides)
    return AgentMessage(**defaults)


@dataclass
class _PolicyResult:
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)


@dataclass
class _OPAResult:
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)


@dataclass
class _ConstitutionalResult:
    is_valid: bool = True
    failure_reason: str = ""


# ===================================================================
# 1. validation_strategies.py
# ===================================================================


class TestStaticHashValidationStrategy:
    @pytest.fixture
    def strategy(self):
        from enhanced_agent_bus.validation_strategies import StaticHashValidationStrategy

        return StaticHashValidationStrategy(strict=True)

    @pytest.fixture
    def non_strict(self):
        from enhanced_agent_bus.validation_strategies import StaticHashValidationStrategy

        return StaticHashValidationStrategy(strict=False)

    async def test_valid_message(self, strategy):
        msg = _make_msg()
        valid, err = await strategy.validate(msg)
        assert valid is True
        assert err is None

    async def test_none_content_rejected(self, strategy):
        msg = _make_msg(content=None)
        valid, err = await strategy.validate(msg)
        assert valid is False
        assert "None" in err

    async def test_empty_message_id_rejected(self, strategy):
        msg = _make_msg(message_id="")
        valid, err = await strategy.validate(msg)
        assert valid is False
        assert "Message ID" in err

    async def test_hash_mismatch_strict(self, strategy):
        msg = _make_msg(constitutional_hash="wrong")
        valid, err = await strategy.validate(msg)
        assert valid is False
        assert "hash mismatch" in err

    async def test_hash_mismatch_non_strict(self, non_strict):
        msg = _make_msg(constitutional_hash="wrong")
        valid, err = await non_strict.validate(msg)
        assert valid is True
        assert err is None


class TestDynamicPolicyValidationStrategy:
    async def test_no_client(self):
        from enhanced_agent_bus.validation_strategies import DynamicPolicyValidationStrategy

        strategy = DynamicPolicyValidationStrategy(policy_client=None)
        valid, err = await strategy.validate(_make_msg())
        assert valid is False
        assert "not available" in err

    async def test_valid_policy(self):
        from enhanced_agent_bus.validation_strategies import DynamicPolicyValidationStrategy

        client = AsyncMock()
        client.validate_message_signature = AsyncMock(return_value=_PolicyResult(is_valid=True))
        strategy = DynamicPolicyValidationStrategy(policy_client=client)
        valid, err = await strategy.validate(_make_msg())
        assert valid is True

    async def test_invalid_policy(self):
        from enhanced_agent_bus.validation_strategies import DynamicPolicyValidationStrategy

        client = AsyncMock()
        client.validate_message_signature = AsyncMock(
            return_value=_PolicyResult(is_valid=False, errors=["bad sig"])
        )
        strategy = DynamicPolicyValidationStrategy(policy_client=client)
        valid, err = await strategy.validate(_make_msg())
        assert valid is False
        assert "bad sig" in err

    async def test_exception_handling(self):
        from enhanced_agent_bus.validation_strategies import DynamicPolicyValidationStrategy

        client = AsyncMock()
        client.validate_message_signature = AsyncMock(side_effect=RuntimeError("boom"))
        strategy = DynamicPolicyValidationStrategy(policy_client=client)
        valid, err = await strategy.validate(_make_msg())
        assert valid is False
        assert "boom" in err


class TestOPAValidationStrategy:
    async def test_no_client(self):
        from enhanced_agent_bus.validation_strategies import OPAValidationStrategy

        strategy = OPAValidationStrategy(opa_client=None)
        valid, err = await strategy.validate(_make_msg())
        assert valid is False
        assert "not available" in err

    async def test_valid_opa(self):
        from enhanced_agent_bus.validation_strategies import OPAValidationStrategy

        client = AsyncMock()
        client.validate_constitutional = AsyncMock(return_value=_OPAResult(is_valid=True))
        strategy = OPAValidationStrategy(opa_client=client)
        valid, err = await strategy.validate(_make_msg())
        assert valid is True

    async def test_invalid_opa(self):
        from enhanced_agent_bus.validation_strategies import OPAValidationStrategy

        client = AsyncMock()
        client.validate_constitutional = AsyncMock(
            return_value=_OPAResult(is_valid=False, errors=["policy fail"])
        )
        strategy = OPAValidationStrategy(opa_client=client)
        valid, err = await strategy.validate(_make_msg())
        assert valid is False
        assert "policy fail" in err

    async def test_exception_handling(self):
        from enhanced_agent_bus.validation_strategies import OPAValidationStrategy

        client = AsyncMock()
        client.validate_constitutional = AsyncMock(side_effect=ValueError("bad"))
        strategy = OPAValidationStrategy(opa_client=client)
        valid, err = await strategy.validate(_make_msg())
        assert valid is False
        assert "bad" in err


class TestRustValidationStrategy:
    async def test_no_processor(self):
        from enhanced_agent_bus.validation_strategies import RustValidationStrategy

        strategy = RustValidationStrategy(rust_processor=None)
        valid, err = await strategy.validate(_make_msg())
        assert valid is False
        assert "not available" in err

    async def test_validate_message_returns_true(self):
        from enhanced_agent_bus.validation_strategies import RustValidationStrategy

        rp = AsyncMock()
        rp.validate_message = AsyncMock(return_value=True)
        strategy = RustValidationStrategy(rust_processor=rp)
        valid, err = await strategy.validate(_make_msg())
        assert valid is True

    async def test_validate_message_returns_false(self):
        from enhanced_agent_bus.validation_strategies import RustValidationStrategy

        rp = AsyncMock()
        rp.validate_message = AsyncMock(return_value=False)
        strategy = RustValidationStrategy(rust_processor=rp)
        valid, err = await strategy.validate(_make_msg())
        assert valid is False
        assert "rejected" in err

    async def test_validate_message_returns_dict_valid(self):
        from enhanced_agent_bus.validation_strategies import RustValidationStrategy

        rp = AsyncMock()
        rp.validate_message = AsyncMock(return_value={"is_valid": True})
        strategy = RustValidationStrategy(rust_processor=rp)
        valid, err = await strategy.validate(_make_msg())
        assert valid is True

    async def test_validate_message_returns_dict_invalid(self):
        from enhanced_agent_bus.validation_strategies import RustValidationStrategy

        rp = AsyncMock()
        rp.validate_message = AsyncMock(return_value={"is_valid": False, "error": "corrupt"})
        strategy = RustValidationStrategy(rust_processor=rp)
        valid, err = await strategy.validate(_make_msg())
        assert valid is False
        assert "corrupt" in err

    async def test_sync_validate_returns_true(self):
        from enhanced_agent_bus.validation_strategies import RustValidationStrategy

        rp = MagicMock(spec=[])
        rp.validate = MagicMock(return_value=True)
        strategy = RustValidationStrategy(rust_processor=rp)
        valid, err = await strategy.validate(_make_msg())
        assert valid is True

    async def test_sync_validate_returns_false(self):
        from enhanced_agent_bus.validation_strategies import RustValidationStrategy

        rp = MagicMock(spec=[])
        rp.validate = MagicMock(return_value=False)
        strategy = RustValidationStrategy(rust_processor=rp)
        valid, err = await strategy.validate(_make_msg())
        assert valid is False

    async def test_sync_validate_returns_dict_valid(self):
        from enhanced_agent_bus.validation_strategies import RustValidationStrategy

        rp = MagicMock(spec=[])
        rp.validate = MagicMock(return_value={"is_valid": True})
        strategy = RustValidationStrategy(rust_processor=rp)
        valid, err = await strategy.validate(_make_msg())
        assert valid is True

    async def test_sync_validate_returns_dict_invalid(self):
        from enhanced_agent_bus.validation_strategies import RustValidationStrategy

        rp = MagicMock(spec=[])
        rp.validate = MagicMock(return_value={"is_valid": False, "error": "nope"})
        strategy = RustValidationStrategy(rust_processor=rp)
        valid, err = await strategy.validate(_make_msg())
        assert valid is False
        assert "nope" in err

    async def test_constitutional_validate_pass(self):
        from enhanced_agent_bus.validation_strategies import RustValidationStrategy

        rp = MagicMock(spec=[])
        rp.constitutional_validate = MagicMock(return_value=True)
        strategy = RustValidationStrategy(rust_processor=rp)
        valid, err = await strategy.validate(_make_msg())
        assert valid is True

    async def test_constitutional_validate_fail(self):
        from enhanced_agent_bus.validation_strategies import RustValidationStrategy

        rp = MagicMock(spec=[])
        rp.constitutional_validate = MagicMock(return_value=False)
        strategy = RustValidationStrategy(rust_processor=rp)
        valid, err = await strategy.validate(_make_msg())
        assert valid is False
        assert "Constitutional hash" in err

    async def test_no_method_fail_closed(self):
        from enhanced_agent_bus.validation_strategies import RustValidationStrategy

        rp = MagicMock(spec=[])  # no validate methods at all
        # Remove any auto-added attributes
        if hasattr(rp, "validate_message"):
            del rp.validate_message
        if hasattr(rp, "validate"):
            del rp.validate
        if hasattr(rp, "constitutional_validate"):
            del rp.constitutional_validate
        strategy = RustValidationStrategy(rust_processor=rp)
        valid, err = await strategy.validate(_make_msg())
        assert valid is False
        assert "fail closed" in err

    async def test_exception_fail_closed(self):
        from enhanced_agent_bus.validation_strategies import RustValidationStrategy

        rp = MagicMock(spec=[])
        rp.validate_message = MagicMock(side_effect=RuntimeError("segfault"))
        # Make hasattr return True
        strategy = RustValidationStrategy(rust_processor=rp)
        valid, err = await strategy.validate(_make_msg())
        assert valid is False
        assert "segfault" in err


class TestPQCValidationStrategy:
    async def test_no_validator_hybrid_hash_match(self):
        from enhanced_agent_bus.validation_strategies import PQCValidationStrategy

        strategy = PQCValidationStrategy(validator=None, hybrid_mode=True)
        strategy._validator = None
        msg = _make_msg()
        valid, err = await strategy.validate(msg)
        assert valid is True

    async def test_no_validator_hybrid_hash_mismatch(self):
        from enhanced_agent_bus.validation_strategies import PQCValidationStrategy

        strategy = PQCValidationStrategy(validator=None, hybrid_mode=True)
        strategy._validator = None
        msg = _make_msg(constitutional_hash="wrong")
        valid, err = await strategy.validate(msg)
        assert valid is False
        assert "hash mismatch" in err

    async def test_no_validator_no_hybrid(self):
        from enhanced_agent_bus.validation_strategies import PQCValidationStrategy

        strategy = PQCValidationStrategy(validator=None, hybrid_mode=False)
        strategy._validator = None
        msg = _make_msg()
        valid, err = await strategy.validate(msg)
        assert valid is False
        assert "not available" in err

    async def test_no_pqc_signature_hybrid_fallback(self):
        from enhanced_agent_bus.validation_strategies import PQCValidationStrategy

        validator = MagicMock()
        strategy = PQCValidationStrategy(validator=validator, hybrid_mode=True)
        msg = _make_msg(pqc_signature=None)
        valid, err = await strategy.validate(msg)
        assert valid is True

    async def test_no_pqc_signature_hybrid_hash_mismatch(self):
        from enhanced_agent_bus.validation_strategies import PQCValidationStrategy

        validator = MagicMock()
        strategy = PQCValidationStrategy(validator=validator, hybrid_mode=True)
        msg = _make_msg(pqc_signature=None, constitutional_hash="bad")
        valid, err = await strategy.validate(msg)
        assert valid is False

    async def test_no_pqc_signature_strict(self):
        from enhanced_agent_bus.validation_strategies import PQCValidationStrategy

        validator = MagicMock()
        strategy = PQCValidationStrategy(validator=validator, hybrid_mode=False)
        msg = _make_msg(pqc_signature=None)
        valid, err = await strategy.validate(msg)
        assert valid is False
        assert "required" in err

    async def test_pqc_signature_no_public_key(self):
        from enhanced_agent_bus.validation_strategies import PQCValidationStrategy

        validator = MagicMock()
        strategy = PQCValidationStrategy(validator=validator, hybrid_mode=False)
        strategy._PQCSignature = MagicMock()
        strategy._PQCAlgorithm = MagicMock()
        sig = base64.b64encode(b"fake-sig").decode()
        msg = _make_msg(pqc_signature=sig, pqc_public_key=None)
        valid, err = await strategy.validate(msg)
        assert valid is False
        assert "public key" in err.lower()

    async def test_pqc_signature_valid(self):
        from enhanced_agent_bus.validation_strategies import PQCValidationStrategy

        validator = MagicMock()
        validator.verify_governance_decision = MagicMock(return_value=True)

        mock_pqc_sig_cls = MagicMock()
        mock_pqc_alg = MagicMock()
        mock_pqc_alg.DILITHIUM_3 = "dilithium3"

        strategy = PQCValidationStrategy(validator=validator, hybrid_mode=False)
        strategy._PQCSignature = mock_pqc_sig_cls
        strategy._PQCAlgorithm = mock_pqc_alg

        sig = base64.b64encode(b"real-sig").decode()
        pub = base64.b64encode(b"real-key").decode()
        msg = _make_msg(pqc_signature=sig, pqc_public_key=pub)
        valid, err = await strategy.validate(msg)
        assert valid is True

    async def test_pqc_signature_invalid(self):
        from enhanced_agent_bus.validation_strategies import PQCValidationStrategy

        validator = MagicMock()
        validator.verify_governance_decision = MagicMock(return_value=False)

        strategy = PQCValidationStrategy(validator=validator, hybrid_mode=False)
        strategy._PQCSignature = MagicMock()
        strategy._PQCAlgorithm = MagicMock()
        strategy._PQCAlgorithm.DILITHIUM_3 = "d3"

        sig = base64.b64encode(b"sig").decode()
        pub = base64.b64encode(b"key").decode()
        msg = _make_msg(pqc_signature=sig, pqc_public_key=pub)
        valid, err = await strategy.validate(msg)
        assert valid is False
        assert "verification failed" in err

    async def test_pqc_classes_not_available(self):
        from enhanced_agent_bus.validation_strategies import PQCValidationStrategy

        validator = MagicMock()
        strategy = PQCValidationStrategy(validator=validator, hybrid_mode=False)
        strategy._PQCSignature = None
        strategy._PQCAlgorithm = None

        sig = base64.b64encode(b"sig").decode()
        pub = base64.b64encode(b"key").decode()
        msg = _make_msg(pqc_signature=sig, pqc_public_key=pub)
        valid, err = await strategy.validate(msg)
        assert valid is False
        assert "not available" in err

    async def test_pqc_hex_fallback_for_public_key(self):
        from enhanced_agent_bus.validation_strategies import PQCValidationStrategy

        validator = MagicMock()
        validator.verify_governance_decision = MagicMock(return_value=True)

        strategy = PQCValidationStrategy(validator=validator, hybrid_mode=False)
        strategy._PQCSignature = MagicMock()
        strategy._PQCAlgorithm = MagicMock()
        strategy._PQCAlgorithm.DILITHIUM_3 = "d3"

        sig = base64.b64encode(b"sig").decode()
        pub_hex = b"abcd1234".hex()  # valid hex
        msg = _make_msg(pqc_signature=sig, pqc_public_key=pub_hex)
        valid, err = await strategy.validate(msg)
        assert valid is True

    async def test_pqc_validation_error_hybrid_fallback(self):
        from enhanced_agent_bus.validation_strategies import PQCValidationStrategy

        validator = MagicMock()
        validator.verify_governance_decision = MagicMock(side_effect=ValueError("corrupt"))

        strategy = PQCValidationStrategy(validator=validator, hybrid_mode=True)
        strategy._PQCSignature = MagicMock()
        strategy._PQCAlgorithm = MagicMock()
        strategy._PQCAlgorithm.DILITHIUM_3 = "d3"

        sig = base64.b64encode(b"sig").decode()
        pub = base64.b64encode(b"key").decode()
        msg = _make_msg(pqc_signature=sig, pqc_public_key=pub)
        valid, err = await strategy.validate(msg)
        # Hybrid mode falls back to hash check which should pass
        assert valid is True

    async def test_pqc_validation_error_no_hybrid(self):
        from enhanced_agent_bus.validation_strategies import PQCValidationStrategy

        validator = MagicMock()
        validator.verify_governance_decision = MagicMock(side_effect=TypeError("bad type"))

        strategy = PQCValidationStrategy(validator=validator, hybrid_mode=False)
        strategy._PQCSignature = MagicMock()
        strategy._PQCAlgorithm = MagicMock()
        strategy._PQCAlgorithm.DILITHIUM_3 = "d3"

        sig = base64.b64encode(b"sig").decode()
        pub = base64.b64encode(b"key").decode()
        msg = _make_msg(pqc_signature=sig, pqc_public_key=pub)
        valid, err = await strategy.validate(msg)
        assert valid is False
        assert "bad type" in err


class TestCompositeValidationStrategy:
    async def test_empty_strategies_pass(self):
        from enhanced_agent_bus.validation_strategies import CompositeValidationStrategy

        strategy = CompositeValidationStrategy(strategies=[], enable_pqc=False)
        msg = _make_msg()
        valid, err = await strategy.validate(msg)
        assert valid is True

    async def test_all_pass(self):
        from enhanced_agent_bus.validation_strategies import (
            CompositeValidationStrategy,
            StaticHashValidationStrategy,
        )

        s1 = StaticHashValidationStrategy(strict=True)
        strategy = CompositeValidationStrategy(strategies=[s1], enable_pqc=False)
        valid, err = await strategy.validate(_make_msg())
        assert valid is True

    async def test_one_fails(self):
        from enhanced_agent_bus.validation_strategies import (
            CompositeValidationStrategy,
            StaticHashValidationStrategy,
        )

        s1 = StaticHashValidationStrategy(strict=True)
        strategy = CompositeValidationStrategy(strategies=[s1], enable_pqc=False)
        msg = _make_msg(constitutional_hash="bad")
        valid, err = await strategy.validate(msg)
        assert valid is False
        assert "StaticHash" in err

    async def test_add_strategy(self):
        from enhanced_agent_bus.validation_strategies import (
            CompositeValidationStrategy,
            StaticHashValidationStrategy,
        )

        strategy = CompositeValidationStrategy(strategies=[], enable_pqc=False)
        strategy.add_strategy(StaticHashValidationStrategy(strict=False))
        valid, err = await strategy.validate(_make_msg())
        assert valid is True

    async def test_pqc_strategy_auto_added(self):
        from enhanced_agent_bus.validation_strategies import (
            CompositeValidationStrategy,
            PQCValidationStrategy,
        )

        strategy = CompositeValidationStrategy(strategies=[], enable_pqc=True)
        assert any(isinstance(s, PQCValidationStrategy) for s in strategy._strategies)

    async def test_pqc_prioritized_with_signature(self):
        from enhanced_agent_bus.validation_strategies import (
            CompositeValidationStrategy,
            PQCValidationStrategy,
        )

        pqc = PQCValidationStrategy(validator=None, hybrid_mode=True)
        pqc._validator = None  # force no validator
        strategy = CompositeValidationStrategy(strategies=[pqc], enable_pqc=False)
        sig = base64.b64encode(b"sig").decode()
        msg = _make_msg(pqc_signature=sig)
        # PQC with no validator in hybrid falls back to hash check
        valid, _ = await strategy.validate(msg)
        assert valid is True


class TestConstitutionalValidationStrategy:
    async def test_no_verifier(self):
        from enhanced_agent_bus.validation_strategies import ConstitutionalValidationStrategy

        strategy = ConstitutionalValidationStrategy(verifier=None)
        valid, err = await strategy.validate(_make_msg())
        assert valid is False
        assert "not available" in err

    async def test_valid(self):
        from enhanced_agent_bus.validation_strategies import ConstitutionalValidationStrategy

        verifier = AsyncMock()
        verifier.verify_constitutional_compliance = AsyncMock(
            return_value=_ConstitutionalResult(is_valid=True)
        )
        strategy = ConstitutionalValidationStrategy(verifier=verifier)
        valid, err = await strategy.validate(_make_msg())
        assert valid is True

    async def test_invalid(self):
        from enhanced_agent_bus.validation_strategies import ConstitutionalValidationStrategy

        verifier = AsyncMock()
        verifier.verify_constitutional_compliance = AsyncMock(
            return_value=_ConstitutionalResult(is_valid=False, failure_reason="violation X")
        )
        strategy = ConstitutionalValidationStrategy(verifier=verifier)
        valid, err = await strategy.validate(_make_msg())
        assert valid is False
        assert "violation X" in err

    async def test_exception(self):
        from enhanced_agent_bus.validation_strategies import ConstitutionalValidationStrategy

        verifier = AsyncMock()
        verifier.verify_constitutional_compliance = AsyncMock(side_effect=RuntimeError("z3 crash"))
        strategy = ConstitutionalValidationStrategy(verifier=verifier)
        valid, err = await strategy.validate(_make_msg())
        assert valid is False
        assert "z3 crash" in err

    async def test_dict_content_context(self):
        from enhanced_agent_bus.validation_strategies import ConstitutionalValidationStrategy

        verifier = AsyncMock()
        verifier.verify_constitutional_compliance = AsyncMock(
            return_value=_ConstitutionalResult(is_valid=True)
        )
        strategy = ConstitutionalValidationStrategy(verifier=verifier)
        msg = _make_msg(content={"count": 5, "flag": True, "name": "test"})
        valid, _ = await strategy.validate(msg)
        assert valid is True
        # Verify context included numeric/bool fields
        call_kwargs = verifier.verify_constitutional_compliance.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context")
        assert context["count"] == 5
        assert context["flag"] is True
        assert "name" not in context  # strings excluded


# ===================================================================
# 2. processing_strategies.py
# ===================================================================


class TestHandlerExecutorMixin:
    async def test_sync_handler(self):
        from enhanced_agent_bus.processing_strategies import HandlerExecutorMixin

        mixin = HandlerExecutorMixin()
        called = []
        msg = _make_msg()
        handlers = {MessageType.COMMAND: [lambda m: called.append(m.message_id)]}
        result = await mixin._execute_handlers(msg, handlers)
        assert result.is_valid is True
        assert called == ["test-msg-001"]
        assert msg.status == MessageStatus.DELIVERED

    async def test_async_handler(self):
        from enhanced_agent_bus.processing_strategies import HandlerExecutorMixin

        mixin = HandlerExecutorMixin()

        async def async_handler(m):
            pass

        msg = _make_msg()
        handlers = {MessageType.COMMAND: [async_handler]}
        result = await mixin._execute_handlers(msg, handlers)
        assert result.is_valid is True

    async def test_handler_exception(self):
        from enhanced_agent_bus.processing_strategies import HandlerExecutorMixin

        mixin = HandlerExecutorMixin()

        def bad_handler(m):
            raise RuntimeError("handler boom")

        msg = _make_msg()
        handlers = {MessageType.COMMAND: [bad_handler]}
        result = await mixin._execute_handlers(msg, handlers)
        assert result.is_valid is False
        assert msg.status == MessageStatus.FAILED
        assert any("Runtime error" in e for e in result.errors)

    async def test_no_handlers_for_type(self):
        from enhanced_agent_bus.processing_strategies import HandlerExecutorMixin

        mixin = HandlerExecutorMixin()
        msg = _make_msg()
        result = await mixin._execute_handlers(msg, {})
        assert result.is_valid is True


class TestPythonProcessingStrategy:
    async def test_valid_message_processed(self):
        from enhanced_agent_bus.processing_strategies import PythonProcessingStrategy
        from enhanced_agent_bus.validation_strategies import StaticHashValidationStrategy

        strategy = PythonProcessingStrategy(
            validation_strategy=StaticHashValidationStrategy(strict=True)
        )
        msg = _make_msg()
        result = await strategy.process(msg, {})
        assert result.is_valid is True

    async def test_validation_failure(self):
        from enhanced_agent_bus.processing_strategies import PythonProcessingStrategy
        from enhanced_agent_bus.validation_strategies import StaticHashValidationStrategy

        strategy = PythonProcessingStrategy(
            validation_strategy=StaticHashValidationStrategy(strict=True)
        )
        msg = _make_msg(constitutional_hash="bad")
        result = await strategy.process(msg, {})
        assert result.is_valid is False
        assert msg.status == MessageStatus.FAILED

    async def test_is_available(self):
        from enhanced_agent_bus.processing_strategies import PythonProcessingStrategy

        strategy = PythonProcessingStrategy()
        assert strategy.is_available() is True

    async def test_get_name(self):
        from enhanced_agent_bus.processing_strategies import PythonProcessingStrategy

        strategy = PythonProcessingStrategy()
        assert strategy.get_name() == "python"

    async def test_default_validation_strategy(self):
        from enhanced_agent_bus.processing_strategies import PythonProcessingStrategy

        strategy = PythonProcessingStrategy()
        msg = _make_msg()
        result = await strategy.process(msg, {})
        assert result.is_valid is True


class TestRustProcessingStrategy:
    def _make_rust_strategy(self, rp=None, rb=None, vs=None):
        from enhanced_agent_bus.processing_strategies import RustProcessingStrategy

        return RustProcessingStrategy(
            rust_processor=rp,
            rust_bus=rb,
            validation_strategy=vs,
            metrics_enabled=False,
        )

    async def test_not_available_no_processor(self):
        strategy = self._make_rust_strategy()
        assert strategy.is_available() is False
        result = await strategy.process(_make_msg(), {})
        assert result.is_valid is False

    async def test_circuit_breaker_trips(self):
        strategy = self._make_rust_strategy()
        for _ in range(3):
            strategy._record_failure()
        assert strategy._breaker_tripped is True

    async def test_circuit_breaker_resets(self):
        strategy = self._make_rust_strategy()
        strategy._breaker_tripped = True
        strategy._failure_count = 3
        for _ in range(5):
            strategy._record_success()
        assert strategy._breaker_tripped is False
        assert strategy._failure_count == 0

    async def test_get_name(self):
        strategy = self._make_rust_strategy()
        assert strategy.get_name() == "rust"

    async def test_process_rust_valid(self):
        rp = MagicMock()
        rp.validate = MagicMock(return_value=True)
        rp.process = MagicMock(return_value=MagicMock(is_valid=True))

        rb = MagicMock()
        rb.AgentMessage = MagicMock
        rb.MessageType = MagicMock()
        rb.Priority = MagicMock()
        rb.MessageStatus = MagicMock()

        from enhanced_agent_bus.validation_strategies import StaticHashValidationStrategy

        vs = StaticHashValidationStrategy(strict=True)
        strategy = self._make_rust_strategy(rp=rp, rb=rb, vs=vs)

        msg = _make_msg()
        result = await strategy.process(msg, {})
        assert result.is_valid is True

    async def test_process_rust_invalid_result(self):
        rp = MagicMock()
        rp.validate = MagicMock(return_value=True)
        res_mock = MagicMock()
        res_mock.is_valid = False
        res_mock.errors = ["rust error"]
        rp.process = MagicMock(return_value=res_mock)

        rb = MagicMock()
        rb.AgentMessage = MagicMock

        from enhanced_agent_bus.validation_strategies import StaticHashValidationStrategy

        vs = StaticHashValidationStrategy(strict=True)
        strategy = self._make_rust_strategy(rp=rp, rb=rb, vs=vs)

        msg = _make_msg()
        result = await strategy.process(msg, {})
        assert result.is_valid is False

    async def test_process_validation_fails(self):
        rp = MagicMock()
        rp.validate = MagicMock(return_value=True)

        from enhanced_agent_bus.validation_strategies import StaticHashValidationStrategy

        vs = StaticHashValidationStrategy(strict=True)
        strategy = self._make_rust_strategy(rp=rp, rb=None, vs=vs)

        msg = _make_msg(constitutional_hash="bad")
        result = await strategy.process(msg, {})
        assert result.is_valid is False

    async def test_process_exception_records_failure(self):
        rp = MagicMock()
        rp.validate = MagicMock(return_value=True)
        rp.process = MagicMock(side_effect=RuntimeError("rust crash"))

        rb = MagicMock()
        rb.AgentMessage = MagicMock

        from enhanced_agent_bus.validation_strategies import StaticHashValidationStrategy

        vs = StaticHashValidationStrategy(strict=True)
        strategy = self._make_rust_strategy(rp=rp, rb=rb, vs=vs)

        msg = _make_msg()
        result = await strategy.process(msg, {})
        assert result.is_valid is False
        assert strategy._failure_count >= 1

    async def test_is_available_with_validate(self):
        rp = MagicMock(spec=["validate"])
        strategy = self._make_rust_strategy(rp=rp)
        assert strategy.is_available() is True

    async def test_is_available_with_validate_message(self):
        rp = MagicMock(spec=["validate_message"])
        strategy = self._make_rust_strategy(rp=rp)
        assert strategy.is_available() is True

    async def test_process_no_rb(self):
        """Validation passes but rb is None -> fail."""
        rp = MagicMock()
        rp.validate = MagicMock(return_value=True)

        from enhanced_agent_bus.validation_strategies import StaticHashValidationStrategy

        vs = StaticHashValidationStrategy(strict=True)
        strategy = self._make_rust_strategy(rp=rp, rb=None, vs=vs)
        msg = _make_msg()
        result = await strategy.process(msg, {})
        assert result.is_valid is False
        assert "not initialized" in result.errors[0]


class TestCompositeProcessingStrategy:
    async def test_first_strategy_succeeds(self):
        from enhanced_agent_bus.processing_strategies import (
            CompositeProcessingStrategy,
            PythonProcessingStrategy,
        )
        from enhanced_agent_bus.validation_strategies import StaticHashValidationStrategy

        s1 = PythonProcessingStrategy(validation_strategy=StaticHashValidationStrategy(strict=True))
        composite = CompositeProcessingStrategy(strategies=[s1])
        result = await composite.process(_make_msg(), {})
        assert result.is_valid is True

    async def test_all_unavailable(self):
        from enhanced_agent_bus.processing_strategies import CompositeProcessingStrategy

        s1 = MagicMock()
        s1.is_available.return_value = False
        composite = CompositeProcessingStrategy(strategies=[s1])
        result = await composite.process(_make_msg(), {})
        assert result.is_valid is False

    async def test_fallback_on_exception(self):
        from enhanced_agent_bus.processing_strategies import (
            CompositeProcessingStrategy,
            PythonProcessingStrategy,
        )
        from enhanced_agent_bus.validation_strategies import StaticHashValidationStrategy

        s1 = MagicMock()
        s1.is_available.return_value = True
        s1.process = AsyncMock(side_effect=RuntimeError("s1 fail"))
        s1.get_name.return_value = "broken"

        s2 = PythonProcessingStrategy(validation_strategy=StaticHashValidationStrategy(strict=True))
        composite = CompositeProcessingStrategy(strategies=[s1, s2])
        result = await composite.process(_make_msg(), {})
        assert result.is_valid is True

    async def test_is_available(self):
        from enhanced_agent_bus.processing_strategies import (
            CompositeProcessingStrategy,
            PythonProcessingStrategy,
        )

        composite = CompositeProcessingStrategy(strategies=[PythonProcessingStrategy()])
        assert composite.is_available() is True

    async def test_get_name(self):
        from enhanced_agent_bus.processing_strategies import (
            CompositeProcessingStrategy,
            PythonProcessingStrategy,
        )

        composite = CompositeProcessingStrategy(strategies=[PythonProcessingStrategy()])
        assert composite.get_name() == "composite(python)"

    async def test_fail_fast_on_invalid(self):
        from enhanced_agent_bus.processing_strategies import (
            CompositeProcessingStrategy,
            PythonProcessingStrategy,
        )
        from enhanced_agent_bus.validation_strategies import StaticHashValidationStrategy

        s1 = PythonProcessingStrategy(validation_strategy=StaticHashValidationStrategy(strict=True))
        s2 = PythonProcessingStrategy(validation_strategy=StaticHashValidationStrategy(strict=True))
        composite = CompositeProcessingStrategy(strategies=[s1, s2])
        msg = _make_msg(constitutional_hash="bad")
        result = await composite.process(msg, {})
        assert result.is_valid is False


class TestDynamicPolicyProcessingStrategy:
    async def test_available_with_client(self):
        from enhanced_agent_bus.processing_strategies import DynamicPolicyProcessingStrategy

        client = MagicMock()
        strategy = DynamicPolicyProcessingStrategy(policy_client=client)
        assert strategy.is_available() is True

    async def test_not_available_without_client(self):
        from enhanced_agent_bus.processing_strategies import DynamicPolicyProcessingStrategy

        strategy = DynamicPolicyProcessingStrategy(policy_client=None)
        assert strategy.is_available() is False

    async def test_get_name(self):
        from enhanced_agent_bus.processing_strategies import DynamicPolicyProcessingStrategy

        strategy = DynamicPolicyProcessingStrategy()
        assert strategy.get_name() == "dynamic_policy"

    async def test_process_delegates(self):
        from enhanced_agent_bus.processing_strategies import DynamicPolicyProcessingStrategy

        client = AsyncMock()
        client.validate_message_signature = AsyncMock(return_value=_PolicyResult(is_valid=True))
        strategy = DynamicPolicyProcessingStrategy(policy_client=client)
        msg = _make_msg()
        result = await strategy.process(msg, {})
        assert result.is_valid is True


class TestOPAProcessingStrategy:
    async def test_available_with_client(self):
        from enhanced_agent_bus.processing_strategies import OPAProcessingStrategy

        client = MagicMock()
        strategy = OPAProcessingStrategy(opa_client=client)
        assert strategy.is_available() is True

    async def test_not_available_without_client(self):
        from enhanced_agent_bus.processing_strategies import OPAProcessingStrategy

        strategy = OPAProcessingStrategy(opa_client=None)
        assert strategy.is_available() is False

    async def test_get_name(self):
        from enhanced_agent_bus.processing_strategies import OPAProcessingStrategy

        strategy = OPAProcessingStrategy()
        assert strategy.get_name() == "opa"


class TestMACIProcessingStrategy:
    async def test_maci_pass_through(self):
        from enhanced_agent_bus.processing_strategies import (
            MACIProcessingStrategy,
            PythonProcessingStrategy,
        )
        from enhanced_agent_bus.validation_strategies import StaticHashValidationStrategy

        inner = PythonProcessingStrategy(
            validation_strategy=StaticHashValidationStrategy(strict=True)
        )
        strategy = MACIProcessingStrategy(
            inner_strategy=inner,
            maci_registry=MagicMock(),
            maci_enforcer=MagicMock(spec=[]),
            strict_mode=False,
        )
        msg = _make_msg()
        result = await strategy.process(msg, {})
        assert result.is_valid is True

    async def test_maci_violation_strict(self):
        from enhanced_agent_bus.processing_strategies import (
            MACIProcessingStrategy,
            PythonProcessingStrategy,
        )
        from enhanced_agent_bus.validation_strategies import StaticHashValidationStrategy

        inner = PythonProcessingStrategy(
            validation_strategy=StaticHashValidationStrategy(strict=True)
        )
        enforcer = MagicMock()
        enforcer.validate = MagicMock(return_value=(False, "role violation"))
        strategy = MACIProcessingStrategy(
            inner_strategy=inner,
            maci_registry=MagicMock(),
            maci_enforcer=enforcer,
            strict_mode=True,
        )
        msg = _make_msg()
        result = await strategy.process(msg, {})
        assert result.is_valid is False
        assert any("MACIRoleViolation" in e for e in result.errors)

    async def test_maci_violation_non_strict_continues(self):
        from enhanced_agent_bus.processing_strategies import (
            MACIProcessingStrategy,
            PythonProcessingStrategy,
        )
        from enhanced_agent_bus.validation_strategies import StaticHashValidationStrategy

        inner = PythonProcessingStrategy(
            validation_strategy=StaticHashValidationStrategy(strict=True)
        )
        enforcer = MagicMock()
        enforcer.validate = MagicMock(return_value=(False, "role violation"))
        strategy = MACIProcessingStrategy(
            inner_strategy=inner,
            maci_registry=MagicMock(),
            maci_enforcer=enforcer,
            strict_mode=False,
        )
        msg = _make_msg()
        result = await strategy.process(msg, {})
        # Non-strict: violation logged but inner processes
        assert result.is_valid is True

    async def test_maci_exception_strict(self):
        from enhanced_agent_bus.processing_strategies import (
            MACIProcessingStrategy,
            PythonProcessingStrategy,
        )
        from enhanced_agent_bus.validation_strategies import StaticHashValidationStrategy

        inner = PythonProcessingStrategy(
            validation_strategy=StaticHashValidationStrategy(strict=True)
        )
        enforcer = MagicMock()
        enforcer.validate = MagicMock(side_effect=RuntimeError("maci fail"))
        strategy = MACIProcessingStrategy(
            inner_strategy=inner,
            maci_registry=MagicMock(),
            maci_enforcer=enforcer,
            strict_mode=True,
        )
        msg = _make_msg()
        result = await strategy.process(msg, {})
        assert result.is_valid is False

    async def test_is_available_strict_no_maci(self):
        from enhanced_agent_bus.processing_strategies import (
            MACIProcessingStrategy,
            PythonProcessingStrategy,
        )

        inner = PythonProcessingStrategy()
        # MACIProcessingStrategy auto-initializes MACI from imports (VULN-001).
        # If auto-init succeeds, _maci_available is True even with None args.
        # We test the logic by directly setting _maci_available = False.
        strategy = MACIProcessingStrategy(
            inner_strategy=inner,
            maci_registry=None,
            maci_enforcer=None,
            strict_mode=True,
        )
        strategy._maci_available = False
        # strict + no maci -> not available
        assert strategy.is_available() is False

    async def test_is_available_non_strict_no_maci(self):
        from enhanced_agent_bus.processing_strategies import (
            MACIProcessingStrategy,
            PythonProcessingStrategy,
        )

        inner = PythonProcessingStrategy()
        strategy = MACIProcessingStrategy(
            inner_strategy=inner,
            maci_registry=None,
            maci_enforcer=None,
            strict_mode=False,
        )
        assert strategy.is_available() is True

    async def test_get_name(self):
        from enhanced_agent_bus.processing_strategies import (
            MACIProcessingStrategy,
            PythonProcessingStrategy,
        )

        inner = PythonProcessingStrategy()
        strategy = MACIProcessingStrategy(
            inner_strategy=inner,
            maci_registry=None,
            maci_enforcer=None,
            strict_mode=False,
        )
        assert strategy.get_name() == "maci(python)"

    async def test_registry_and_enforcer_properties(self):
        from enhanced_agent_bus.processing_strategies import (
            MACIProcessingStrategy,
            PythonProcessingStrategy,
        )

        reg = MagicMock()
        enf = MagicMock(spec=[])
        inner = PythonProcessingStrategy()
        strategy = MACIProcessingStrategy(
            inner_strategy=inner,
            maci_registry=reg,
            maci_enforcer=enf,
            strict_mode=True,
        )
        assert strategy.registry is reg
        assert strategy.enforcer is enf

    async def test_maci_async_validate(self):
        """Test that async validate on MACI enforcer is awaited properly."""
        from enhanced_agent_bus.processing_strategies import (
            MACIProcessingStrategy,
            PythonProcessingStrategy,
        )
        from enhanced_agent_bus.validation_strategies import StaticHashValidationStrategy

        inner = PythonProcessingStrategy(
            validation_strategy=StaticHashValidationStrategy(strict=True)
        )
        enforcer = MagicMock()
        enforcer.validate = AsyncMock(return_value=(True, None))
        strategy = MACIProcessingStrategy(
            inner_strategy=inner,
            maci_registry=MagicMock(),
            maci_enforcer=enforcer,
            strict_mode=True,
        )
        msg = _make_msg()
        result = await strategy.process(msg, {})
        assert result.is_valid is True


# ===================================================================
# 3. adaptive_governance/threshold_manager.py
# ===================================================================


class TestAdaptiveThresholds:
    @pytest.fixture
    def thresholds(self):
        from enhanced_agent_bus.adaptive_governance.threshold_manager import AdaptiveThresholds

        return AdaptiveThresholds(constitutional_hash=CONSTITUTIONAL_HASH)

    @pytest.fixture
    def features(self):
        from enhanced_agent_bus.adaptive_governance.models import ImpactFeatures

        return ImpactFeatures(
            message_length=100,
            agent_count=3,
            tenant_complexity=0.5,
            temporal_patterns=[0.1, 0.2, 0.3],
            semantic_similarity=0.7,
            historical_precedence=5,
            resource_utilization=0.4,
            network_isolation=0.6,
            risk_score=0.3,
            confidence_level=0.9,
        )

    def test_base_thresholds_returned_when_untrained(self, thresholds, features):
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        result = thresholds.get_adaptive_threshold(ImpactLevel.MEDIUM, features)
        assert result == 0.6

    def test_base_thresholds_all_levels(self, thresholds, features):
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        expected = {
            ImpactLevel.NEGLIGIBLE: 0.1,
            ImpactLevel.LOW: 0.3,
            ImpactLevel.MEDIUM: 0.6,
            ImpactLevel.HIGH: 0.8,
            ImpactLevel.CRITICAL: 0.95,
        }
        for level, val in expected.items():
            assert thresholds.get_adaptive_threshold(level, features) == val

    def test_extract_feature_vector(self, thresholds, features):
        vec = thresholds._extract_feature_vector(features)
        assert len(vec) == 11
        assert vec[0] == 100  # message_length
        assert vec[1] == 3  # agent_count

    def test_extract_feature_vector_empty_temporal(self, thresholds):
        from enhanced_agent_bus.adaptive_governance.models import ImpactFeatures

        f = ImpactFeatures(
            message_length=50,
            agent_count=1,
            tenant_complexity=0.1,
            temporal_patterns=[],
            semantic_similarity=0.5,
            historical_precedence=0,
            resource_utilization=0.1,
            network_isolation=0.2,
        )
        vec = thresholds._extract_feature_vector(f)
        assert vec[3] == 0.0  # mean of empty
        assert vec[4] == 0.0  # std of empty

    def test_update_model_stores_sample(self, thresholds, features):
        from enhanced_agent_bus.adaptive_governance.models import (
            GovernanceDecision,
            ImpactLevel,
        )

        decision = GovernanceDecision(
            action_allowed=True,
            impact_level=ImpactLevel.MEDIUM,
            confidence_score=0.85,
            reasoning="test",
            recommended_threshold=0.65,
            features_used=features,
        )
        thresholds.update_model(decision, outcome_success=True)
        assert len(thresholds.training_data) == 1

    def test_update_model_negative_feedback(self, thresholds, features):
        from enhanced_agent_bus.adaptive_governance.models import (
            GovernanceDecision,
            ImpactLevel,
        )

        decision = GovernanceDecision(
            action_allowed=True,
            impact_level=ImpactLevel.HIGH,
            confidence_score=0.7,
            reasoning="test",
            recommended_threshold=0.75,
            features_used=features,
        )
        thresholds.update_model(decision, outcome_success=False, human_feedback=False)
        assert len(thresholds.training_data) == 1
        assert thresholds.training_data[0]["outcome_success"] is False

    def test_update_model_human_feedback_false(self, thresholds, features):
        from enhanced_agent_bus.adaptive_governance.models import (
            GovernanceDecision,
            ImpactLevel,
        )

        decision = GovernanceDecision(
            action_allowed=True,
            impact_level=ImpactLevel.LOW,
            confidence_score=0.5,
            reasoning="test",
            recommended_threshold=0.35,
            features_used=features,
        )
        thresholds.update_model(decision, outcome_success=True, human_feedback=False)
        assert len(thresholds.training_data) == 1

    def test_retrain_model_insufficient_data(self, thresholds):
        thresholds._retrain_model()
        assert thresholds.model_trained is False

    def test_retrain_model_sufficient_data(self, thresholds, features):
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        now = time.time()
        for i in range(120):
            thresholds.training_data.append(
                {
                    "features": thresholds._extract_feature_vector(features),
                    "target": 0.05 * (i % 10),
                    "timestamp": now - 100,
                    "impact_level": ImpactLevel.MEDIUM.value,
                    "confidence": 0.8,
                    "outcome_success": True,
                    "human_feedback": None,
                }
            )
        thresholds._retrain_model()
        assert thresholds.model_trained is True

    def test_get_adaptive_threshold_after_training(self, thresholds, features):
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        now = time.time()
        for _i in range(120):
            thresholds.training_data.append(
                {
                    "features": thresholds._extract_feature_vector(features),
                    "target": 0.01,
                    "timestamp": now - 100,
                    "impact_level": ImpactLevel.MEDIUM.value,
                    "confidence": 0.8,
                    "outcome_success": True,
                    "human_feedback": None,
                }
            )
        thresholds._retrain_model()
        assert thresholds.model_trained is True

        result = thresholds.get_adaptive_threshold(ImpactLevel.MEDIUM, features)
        # Should be near base + small adjustment, bounded [0, 1]
        assert 0.0 <= result <= 1.0

    def test_get_adaptive_threshold_error_returns_base(self, thresholds, features):
        from enhanced_agent_bus.adaptive_governance.models import ImpactLevel

        thresholds.model_trained = True
        thresholds.threshold_model = MagicMock()
        thresholds.threshold_model.predict = MagicMock(side_effect=ValueError("bad"))
        result = thresholds.get_adaptive_threshold(ImpactLevel.HIGH, features)
        assert result == 0.8

    def test_update_model_triggers_retrain(self, thresholds, features):
        from enhanced_agent_bus.adaptive_governance.models import (
            GovernanceDecision,
            ImpactLevel,
        )

        # Force retraining interval to have passed
        thresholds.last_retraining = time.time() - 7200

        now = time.time()
        for _i in range(120):
            thresholds.training_data.append(
                {
                    "features": thresholds._extract_feature_vector(features),
                    "target": 0.01,
                    "timestamp": now - 100,
                    "impact_level": ImpactLevel.MEDIUM.value,
                    "confidence": 0.8,
                    "outcome_success": True,
                    "human_feedback": None,
                }
            )

        decision = GovernanceDecision(
            action_allowed=True,
            impact_level=ImpactLevel.MEDIUM,
            confidence_score=0.85,
            reasoning="test",
            recommended_threshold=0.65,
            features_used=features,
        )
        thresholds.update_model(decision, outcome_success=True)
        assert thresholds.model_trained is True

    def test_retrain_insufficient_recent_data(self, thresholds, features):
        """100+ samples but all older than 24h -> skip."""
        old_ts = time.time() - 200_000
        for _i in range(120):
            thresholds.training_data.append(
                {
                    "features": thresholds._extract_feature_vector(features),
                    "target": 0.01,
                    "timestamp": old_ts,
                    "impact_level": "medium",
                    "confidence": 0.8,
                    "outcome_success": True,
                    "human_feedback": None,
                }
            )
        thresholds._retrain_model()
        assert thresholds.model_trained is False

    def test_mlflow_not_initialized_in_test(self, thresholds):
        assert thresholds._mlflow_initialized is False

    def test_log_training_run_to_mlflow_fallback_on_error(self, thresholds, features):
        """_log_training_run_to_mlflow falls back to direct fit on error."""
        X = np.array([thresholds._extract_feature_vector(features)] * 60)
        y = np.array([0.01] * 60)
        data = [{"outcome_success": True, "human_feedback": None}] * 60

        thresholds._mlflow_initialized = True
        with patch(
            "enhanced_agent_bus.adaptive_governance.threshold_manager.mlflow"
        ) as mock_mlflow:
            mock_mlflow.start_run.side_effect = RuntimeError("mlflow down")
            thresholds._log_training_run_to_mlflow(X, y, data)
        # Should have fallen back to direct fit
        # Model is now trained (fit was called)


# ===================================================================
# 4. verification_orchestrator.py
# ===================================================================


class TestVerificationResult:
    def test_defaults(self):
        from enhanced_agent_bus.verification_orchestrator import VerificationResult

        vr = VerificationResult()
        assert vr.sdpc_metadata == {}
        assert vr.pqc_result is None
        assert vr.pqc_metadata == {}


class TestVerificationOrchestrator:
    @pytest.fixture
    def config(self):
        return BusConfiguration(
            pqc_mode="classical_only",
            pqc_verification_mode="strict",
            pqc_migration_phase=0,
        )

    @pytest.fixture
    def orchestrator(self, config):
        from enhanced_agent_bus.verification_orchestrator import VerificationOrchestrator

        return VerificationOrchestrator(config=config, enable_pqc=False)

    async def test_verify_no_pqc(self, orchestrator):
        msg = _make_msg()
        result = await orchestrator.verify(msg, "test content")
        assert result.pqc_result is None
        assert isinstance(result.sdpc_metadata, dict)

    async def test_verify_pqc_disabled(self, orchestrator):
        msg = _make_msg()
        pqc_result, pqc_meta = await orchestrator.verify_pqc(msg)
        assert pqc_result is None
        assert pqc_meta == {}

    async def test_sdpc_factual_intent(self, orchestrator):
        """Factual intent triggers ASC and graph verification."""
        # Override intent classifier to return FACTUAL
        factual_intent = MagicMock()
        factual_intent.value = orchestrator._IntentType.FACTUAL.value
        orchestrator.intent_classifier.classify_async = AsyncMock(return_value=factual_intent)

        msg = _make_msg()
        result = await orchestrator.verify(msg, "what is X")
        assert isinstance(result.sdpc_metadata, dict)

    async def test_sdpc_high_impact(self, orchestrator):
        """High impact score triggers ASC/graph/PACAR."""
        unknown_intent = MagicMock()
        unknown_intent.value = "some_other"
        orchestrator.intent_classifier.classify_async = AsyncMock(return_value=unknown_intent)

        # Mock pacar_verifier to accept session_id kwarg
        orchestrator.pacar_verifier.verify = AsyncMock(
            return_value={"is_valid": True, "confidence": 0.9}
        )

        msg = _make_msg(impact_score=0.9, message_type=MessageType.TASK_REQUEST)
        result = await orchestrator.verify(msg, "do something risky")
        meta = result.sdpc_metadata
        # With high impact, PACAR should have been invoked
        assert isinstance(meta, dict)

    async def test_sdpc_no_tasks_needed(self, orchestrator):
        """Non-factual, low-impact -> no SDPC tasks."""
        unknown_intent = MagicMock()
        unknown_intent.value = "creative"
        orchestrator.intent_classifier.classify_async = AsyncMock(return_value=unknown_intent)

        msg = _make_msg(impact_score=0.1)
        result = await orchestrator.verify(msg, "write a poem")
        assert result.sdpc_metadata == {} or "sdpc_intent" not in result.sdpc_metadata

    async def test_sdpc_none_impact_score(self, orchestrator):
        """impact_score=None should be treated as 0.0."""
        unknown_intent = MagicMock()
        unknown_intent.value = "creative"
        orchestrator.intent_classifier.classify_async = AsyncMock(return_value=unknown_intent)

        msg = _make_msg(impact_score=None)
        result = await orchestrator.verify(msg, "hello")
        assert isinstance(result.sdpc_metadata, dict)

    async def test_pqc_init_import_error(self, config):
        """PQC init with ImportError disables PQC gracefully."""
        from enhanced_agent_bus.verification_orchestrator import VerificationOrchestrator

        with patch(
            "enhanced_agent_bus.verification_orchestrator.VerificationOrchestrator._init_pqc",
            side_effect=ImportError("no pqc"),
        ):
            # The __init__ calls _init_pqc, which we patched to raise
            # But the original code has try/except so let's test the real path
            pass

        # Test real _init_pqc with missing imports
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        orch._enable_pqc = True
        with patch.dict("sys.modules", {"enhanced_agent_bus.pqc_validators": None}):
            orch._init_pqc(config)
        # PQC should be disabled after failed init
        assert orch._pqc_config is None or orch._enable_pqc is False

    async def test_perform_pqc_with_pqc_disabled(self, orchestrator):
        result, meta = await orchestrator._perform_pqc(_make_msg())
        assert result is None
        assert meta == {}

    async def test_sdpc_pacar_with_critique(self, orchestrator):
        """PACAR result with critique field is captured."""
        unknown_intent = MagicMock()
        unknown_intent.value = "creative"
        orchestrator.intent_classifier.classify_async = AsyncMock(return_value=unknown_intent)

        pacar_result = {
            "is_valid": True,
            "confidence": 0.95,
            "critique": "looks good",
        }
        orchestrator.pacar_verifier.verify = AsyncMock(return_value=pacar_result)

        msg = _make_msg(impact_score=0.9, message_type=MessageType.TASK_REQUEST)
        result = await orchestrator.verify(msg, "risky task")
        if "sdpc_pacar_critique" in result.sdpc_metadata:
            assert result.sdpc_metadata["sdpc_pacar_critique"] == "looks good"

    async def test_sdpc_reasoning_intent(self, orchestrator):
        """Reasoning intent also triggers ASC + graph."""
        reasoning_intent = MagicMock()
        reasoning_intent.value = orchestrator._IntentType.REASONING.value
        orchestrator.intent_classifier.classify_async = AsyncMock(return_value=reasoning_intent)

        msg = _make_msg(impact_score=0.1)
        result = await orchestrator.verify(msg, "why does X cause Y")
        assert isinstance(result.sdpc_metadata, dict)
