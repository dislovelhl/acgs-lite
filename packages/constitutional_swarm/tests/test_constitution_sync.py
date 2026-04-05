"""Tests for constitution sync (Phase 1 — Protocol Bridge)."""

from __future__ import annotations

import hashlib
import time

import pytest
from constitutional_swarm.bittensor.constitution_sync import (
    ConstitutionDistributor,
    ConstitutionReceiver,
    ConstitutionSyncMessage,
    ConstitutionVersionRecord,
)

YAML_V1 = """\
name: test-constitution-v1
rules:
  - id: safety-01
    text: Do not cause harm
    severity: critical
    hardcoded: true
    keywords:
      - harm
      - danger
"""

YAML_V2 = """\
name: test-constitution-v2
rules:
  - id: safety-01
    text: Do not cause harm
    severity: critical
    hardcoded: true
    keywords:
      - harm
      - danger
  - id: privacy-01
    text: Protect personal data
    severity: high
    hardcoded: false
    keywords:
      - PII
      - personal
"""


# ---------------------------------------------------------------------------
# ConstitutionVersionRecord
# ---------------------------------------------------------------------------


class TestConstitutionVersionRecord:
    def test_create_produces_stable_hash(self):
        r1 = ConstitutionVersionRecord.create(YAML_V1)
        r2 = ConstitutionVersionRecord.create(YAML_V1)
        assert r1.constitution_hash == r2.constitution_hash

    def test_different_yaml_different_hash(self):
        r1 = ConstitutionVersionRecord.create(YAML_V1)
        r2 = ConstitutionVersionRecord.create(YAML_V2)
        assert r1.constitution_hash != r2.constitution_hash

    def test_hash_length(self):
        r = ConstitutionVersionRecord.create(YAML_V1)
        assert len(r.constitution_hash) == 16

    def test_version_id_unique(self):
        r1 = ConstitutionVersionRecord.create(YAML_V1)
        r2 = ConstitutionVersionRecord.create(YAML_V1)
        assert r1.version_id != r2.version_id

    def test_age_seconds(self):
        r = ConstitutionVersionRecord.create(YAML_V1)
        assert r.age_seconds >= 0.0
        assert r.age_seconds < 5.0

    def test_immutable(self):
        r = ConstitutionVersionRecord.create(YAML_V1)
        with pytest.raises(AttributeError):
            r.constitution_hash = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ConstitutionSyncMessage
# ---------------------------------------------------------------------------


class TestConstitutionSyncMessage:
    def _make_msg(self, yaml: str = YAML_V1) -> ConstitutionSyncMessage:
        expected = hashlib.sha256(yaml.encode()).hexdigest()[:16]
        return ConstitutionSyncMessage(
            version_id="v001",
            expected_hash=expected,
            yaml_content=yaml,
            issued_at=time.time(),
        )

    def test_verify_valid(self):
        msg = self._make_msg()
        assert msg.verify() is True

    def test_verify_tampered_content(self):
        msg = self._make_msg()
        tampered = ConstitutionSyncMessage(
            version_id=msg.version_id,
            expected_hash=msg.expected_hash,
            yaml_content=msg.yaml_content + "\n# tampered",
            issued_at=msg.issued_at,
        )
        assert tampered.verify() is False

    def test_verify_wrong_hash(self):
        msg = self._make_msg()
        wrong = ConstitutionSyncMessage(
            version_id=msg.version_id,
            expected_hash="wronghash1234567",
            yaml_content=msg.yaml_content,
            issued_at=msg.issued_at,
        )
        assert wrong.verify() is False

    def test_to_dict_from_dict_roundtrip(self):
        msg = self._make_msg()
        restored = ConstitutionSyncMessage.from_dict(msg.to_dict())
        assert restored.version_id == msg.version_id
        assert restored.expected_hash == msg.expected_hash
        assert restored.yaml_content == msg.yaml_content


# ---------------------------------------------------------------------------
# ConstitutionDistributor
# ---------------------------------------------------------------------------


class TestConstitutionDistributor:
    def test_initial_version(self):
        dist = ConstitutionDistributor(YAML_V1)
        assert dist.active_hash
        assert len(dist.version_history) == 1

    def test_broadcast_message_passes_verify(self):
        dist = ConstitutionDistributor(YAML_V1)
        msg = dist.broadcast_message()
        assert msg.verify() is True

    def test_update_creates_new_version(self):
        dist = ConstitutionDistributor(YAML_V1)
        v1_hash = dist.active_hash
        dist.update(YAML_V2, description="Added privacy rule")
        assert dist.active_hash != v1_hash
        assert len(dist.version_history) == 2

    def test_update_same_content_raises(self):
        dist = ConstitutionDistributor(YAML_V1)
        with pytest.raises(ValueError, match="unchanged"):
            dist.update(YAML_V1)

    def test_version_history_ordered(self):
        dist = ConstitutionDistributor(YAML_V1)
        dist.update(YAML_V2)
        history = dist.version_history
        assert history[0].yaml_content == YAML_V1
        assert history[1].yaml_content == YAML_V2

    def test_multiple_updates(self):
        dist = ConstitutionDistributor(YAML_V1)
        for i in range(3):
            extra_yaml = YAML_V1 + f"\n  # update {i}"
            dist.update(extra_yaml)
        assert len(dist.version_history) == 4


# ---------------------------------------------------------------------------
# ConstitutionReceiver
# ---------------------------------------------------------------------------


class TestConstitutionReceiver:
    def test_uninitialised(self):
        r = ConstitutionReceiver("miner-01")
        assert not r.is_initialised
        assert r.active_hash == ""
        assert r.active_yaml == ""

    def test_apply_valid_message(self):
        dist = ConstitutionDistributor(YAML_V1)
        msg = dist.broadcast_message()

        receiver = ConstitutionReceiver("miner-01")
        result = receiver.apply(msg)

        assert result.success is True
        assert receiver.is_initialised
        assert receiver.active_hash == dist.active_hash

    def test_apply_tampered_message(self):
        dist = ConstitutionDistributor(YAML_V1)
        msg = dist.broadcast_message()
        tampered = ConstitutionSyncMessage(
            version_id=msg.version_id,
            expected_hash=msg.expected_hash,
            yaml_content=msg.yaml_content + "\n# tampered",
            issued_at=msg.issued_at,
        )
        receiver = ConstitutionReceiver("miner-01")
        result = receiver.apply(tampered)

        assert result.success is False
        assert not receiver.is_initialised

    def test_apply_noop_same_version(self):
        dist = ConstitutionDistributor(YAML_V1)
        msg = dist.broadcast_message()
        receiver = ConstitutionReceiver("miner-01")
        receiver.apply(msg)

        result = receiver.apply(msg)
        assert result.success is True
        assert "no-op" in result.message.lower()
        assert len(receiver.version_history) == 1  # not duplicated

    def test_apply_version_update(self):
        dist = ConstitutionDistributor(YAML_V1)
        receiver = ConstitutionReceiver("miner-01")
        receiver.apply(dist.broadcast_message())

        dist.update(YAML_V2)
        result = receiver.apply(dist.broadcast_message())

        assert result.success is True
        assert receiver.active_hash == dist.active_hash
        assert len(receiver.version_history) == 2

    def test_verify_task_hash_matches(self):
        dist = ConstitutionDistributor(YAML_V1)
        receiver = ConstitutionReceiver("miner-01")
        receiver.apply(dist.broadcast_message())

        assert receiver.verify_task_hash(dist.active_hash) is True
        assert receiver.verify_task_hash("wrong_hash") is False

    def test_summary(self):
        receiver = ConstitutionReceiver("miner-42")
        s = receiver.summary()
        assert s["node_id"] == "miner-42"
        assert s["is_initialised"] is False

    def test_multiple_receivers_stay_in_sync(self):
        dist = ConstitutionDistributor(YAML_V1)
        miners = [ConstitutionReceiver(f"miner-{i:02d}") for i in range(5)]

        msg = dist.broadcast_message()
        for m in miners:
            result = m.apply(msg)
            assert result.success

        hashes = {m.active_hash for m in miners}
        assert len(hashes) == 1  # all nodes converge to same hash

        # Now update
        dist.update(YAML_V2)
        msg2 = dist.broadcast_message()
        for m in miners:
            result = m.apply(msg2)
            assert result.success

        hashes2 = {m.active_hash for m in miners}
        assert len(hashes2) == 1
        assert hashes2 != hashes  # moved to new version
