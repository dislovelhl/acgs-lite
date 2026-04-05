"""
ACGS-2 Enhanced Agent Bus - Payload Integrity Coverage Tests
Constitutional Hash: 608508a9bd224290

Covers: enhanced_agent_bus/payload_integrity.py (29 stmts, 0% -> target 100%)
Tests HMAC-SHA256 signing and verification for payload integrity (OWASP AA05).
"""

from __future__ import annotations

import hashlib

import pytest

pytestmark = [pytest.mark.governance, pytest.mark.constitutional, pytest.mark.security]


class TestPayloadIntegrity:
    def test_sign_payload_basic(self) -> None:
        from enhanced_agent_bus.payload_integrity import sign_payload

        payload = {"action": "test", "value": 42}
        sig = sign_payload(payload)
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA-256 hex digest

    def test_sign_payload_deterministic(self) -> None:
        from enhanced_agent_bus.payload_integrity import sign_payload

        payload = {"key": "value", "number": 1}
        sig1 = sign_payload(payload)
        sig2 = sign_payload(payload)
        assert sig1 == sig2

    def test_sign_payload_key_order_irrelevant(self) -> None:
        """Canonical JSON sorts keys, so insertion order should not matter."""
        from enhanced_agent_bus.payload_integrity import sign_payload

        sig1 = sign_payload({"a": 1, "b": 2})
        sig2 = sign_payload({"b": 2, "a": 1})
        assert sig1 == sig2

    def test_sign_payload_different_payloads_differ(self) -> None:
        from enhanced_agent_bus.payload_integrity import sign_payload

        sig1 = sign_payload({"action": "create"})
        sig2 = sign_payload({"action": "delete"})
        assert sig1 != sig2

    def test_sign_payload_custom_key(self) -> None:
        from enhanced_agent_bus.payload_integrity import sign_payload

        custom_key = hashlib.sha256(b"custom-seed").digest()
        payload = {"test": True}
        sig_default = sign_payload(payload)
        sig_custom = sign_payload(payload, key=custom_key)
        # Different keys should produce different signatures
        assert sig_default != sig_custom

    def test_verify_payload_valid(self) -> None:
        from enhanced_agent_bus.payload_integrity import sign_payload, verify_payload

        payload = {"agent_id": "agent-001", "message": "hello"}
        sig = sign_payload(payload)
        assert verify_payload(payload, sig) is True

    def test_verify_payload_invalid_signature(self) -> None:
        from enhanced_agent_bus.payload_integrity import verify_payload

        payload = {"agent_id": "agent-001"}
        assert verify_payload(payload, "0" * 64) is False

    def test_verify_payload_tampered(self) -> None:
        from enhanced_agent_bus.payload_integrity import sign_payload, verify_payload

        payload = {"amount": 100}
        sig = sign_payload(payload)
        tampered = {"amount": 999}
        assert verify_payload(tampered, sig) is False

    def test_verify_payload_custom_key(self) -> None:
        from enhanced_agent_bus.payload_integrity import sign_payload, verify_payload

        custom_key = hashlib.sha256(b"test-key").digest()
        payload = {"data": "sensitive"}
        sig = sign_payload(payload, key=custom_key)
        assert verify_payload(payload, sig, key=custom_key) is True
        # Wrong key should fail
        wrong_key = hashlib.sha256(b"wrong-key").digest()
        assert verify_payload(payload, sig, key=wrong_key) is False

    def test_empty_payload(self) -> None:
        from enhanced_agent_bus.payload_integrity import sign_payload, verify_payload

        payload: dict = {}
        sig = sign_payload(payload)
        assert verify_payload(payload, sig) is True

    def test_nested_payload(self) -> None:
        from enhanced_agent_bus.payload_integrity import sign_payload, verify_payload

        payload = {"outer": {"inner": [1, 2, 3]}, "flag": True}
        sig = sign_payload(payload)
        assert verify_payload(payload, sig) is True
