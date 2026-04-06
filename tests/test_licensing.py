"""Tests for acgs-lite license management.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import os
import struct
import time
from unittest.mock import patch

import pytest

from acgs_lite.licensing import (
    _DEFAULT_DEV_SECRET,
    LicenseError,
    LicenseExpiredError,
    LicenseInfo,
    LicenseManager,
    Tier,
    generate_license_key,
    validate_license_key,
)

SECRET = _DEFAULT_DEV_SECRET


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_manager():
    """Ensure a fresh LicenseManager for every test."""
    LicenseManager.reset()
    yield
    LicenseManager.reset()


@pytest.fixture()
def pro_key():
    return generate_license_key("PRO", 365, SECRET)


@pytest.fixture()
def team_key():
    return generate_license_key("TEAM", 365, SECRET)


@pytest.fixture()
def enterprise_key():
    return generate_license_key("ENTERPRISE", 365, SECRET)


@pytest.fixture()
def free_key():
    return generate_license_key("FREE", 365, SECRET)


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenerateLicenseKey:
    def test_format_pro(self, pro_key: str) -> None:
        assert pro_key.startswith("ACGS-PRO-")
        parts = pro_key.split("-")
        assert len(parts) == 7

    def test_format_team(self, team_key: str) -> None:
        assert team_key.startswith("ACGS-TEAM-")

    def test_format_enterprise(self, enterprise_key: str) -> None:
        assert enterprise_key.startswith("ACGS-ENTERPRISE-")

    def test_format_free(self, free_key: str) -> None:
        assert free_key.startswith("ACGS-FREE-")

    def test_unknown_tier_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown tier"):
            generate_license_key("GOLD", 30, SECRET)

    def test_case_insensitive_tier(self) -> None:
        key = generate_license_key("pro", 30, SECRET)
        assert key.startswith("ACGS-PRO-")

    def test_zero_days_no_expiry(self) -> None:
        key = generate_license_key("PRO", 0, SECRET)
        info = validate_license_key(key, SECRET)
        assert info.expiry is None

    def test_positive_days_sets_expiry(self) -> None:
        key = generate_license_key("PRO", 30, SECRET)
        info = validate_license_key(key, SECRET)
        assert info.expiry is not None
        # Should expire roughly 30 days from now
        delta = info.expiry - int(time.time())
        assert 29 * 86400 < delta < 31 * 86400

    def test_two_keys_differ(self) -> None:
        # Random nonce means keys are not deterministic
        k1 = generate_license_key("PRO", 365, SECRET)
        k2 = generate_license_key("PRO", 365, SECRET)
        assert k1 != k2


# ---------------------------------------------------------------------------
# Key validation — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateLicenseKey:
    def test_validate_pro(self, pro_key: str) -> None:
        info = validate_license_key(pro_key, SECRET)
        assert info.tier == Tier.PRO
        assert info.is_valid

    def test_validate_team(self, team_key: str) -> None:
        info = validate_license_key(team_key, SECRET)
        assert info.tier == Tier.TEAM

    def test_validate_enterprise(self, enterprise_key: str) -> None:
        info = validate_license_key(enterprise_key, SECRET)
        assert info.tier == Tier.ENTERPRISE

    def test_validate_free(self, free_key: str) -> None:
        info = validate_license_key(free_key, SECRET)
        assert info.tier == Tier.FREE

    def test_key_stored_in_info(self, pro_key: str) -> None:
        info = validate_license_key(pro_key, SECRET)
        assert info.key == pro_key

    def test_expiry_date_format(self, pro_key: str) -> None:
        info = validate_license_key(pro_key, SECRET)
        assert info.expiry_date is not None
        assert len(info.expiry_date) == 10  # YYYY-MM-DD

    def test_features_pro(self, pro_key: str) -> None:
        info = validate_license_key(pro_key, SECRET)
        features = info.features
        assert any("Article 12" in f for f in features)
        assert not any("Article 13" in f for f in features)

    def test_features_team(self, team_key: str) -> None:
        info = validate_license_key(team_key, SECRET)
        features = info.features
        assert any("Article 13" in f for f in features)
        assert any("Article 14" in f for f in features)


# ---------------------------------------------------------------------------
# Expired keys
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExpiredKeys:
    def test_expired_key_raises(self) -> None:
        # Generate a key that expired 1 second ago
        expiry = int(time.time()) - 1
        nonce = b"\x01\x02\x03\x04"
        tier_code = int(Tier.PRO)
        expiry_b = struct.pack(">I", expiry)
        tier_b = struct.pack(">H", tier_code)
        import hashlib
        import hmac as _hmac

        msg = expiry_b + nonce + tier_b
        sig = _hmac.new(SECRET.encode(), msg, hashlib.sha256).digest()[:16]
        g1, g2, g3, g4, g5 = (
            expiry_b.hex(),
            nonce[:2].hex(),
            nonce[2:].hex(),
            tier_b.hex(),
            sig.hex(),
        )
        key = f"ACGS-PRO-{g1}-{g2}-{g3}-{g4}-{g5}"

        with pytest.raises(LicenseExpiredError, match="expired"):
            validate_license_key(key, SECRET)

    def test_future_expiry_valid(self) -> None:
        expiry = int(time.time()) + 86400
        nonce = b"\x05\x06\x07\x08"
        tier_code = int(Tier.PRO)
        expiry_b = struct.pack(">I", expiry)
        tier_b = struct.pack(">H", tier_code)
        import hashlib
        import hmac as _hmac

        msg = expiry_b + nonce + tier_b
        sig = _hmac.new(SECRET.encode(), msg, hashlib.sha256).digest()[:16]
        g1, g2, g3, g4, g5 = (
            expiry_b.hex(),
            nonce[:2].hex(),
            nonce[2:].hex(),
            tier_b.hex(),
            sig.hex(),
        )
        key = f"ACGS-PRO-{g1}-{g2}-{g3}-{g4}-{g5}"
        info = validate_license_key(key, SECRET)
        assert info.is_valid


# ---------------------------------------------------------------------------
# Tampered keys (HMAC failures)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTamperedKeys:
    def test_wrong_secret_fails(self, pro_key: str) -> None:
        with pytest.raises(LicenseError, match="invalid signature"):
            validate_license_key(pro_key, "wrong-secret")

    def test_flip_tier_label_fails(self, pro_key: str) -> None:
        # Change ACGS-PRO-... to ACGS-TEAM-...
        tampered = pro_key.replace("ACGS-PRO-", "ACGS-TEAM-", 1)
        with pytest.raises(LicenseError):
            validate_license_key(tampered, SECRET)

    def test_flip_expiry_byte_fails(self, pro_key: str) -> None:
        parts = pro_key.split("-")
        expiry_hex = parts[2]
        # Flip first byte
        first_byte = int(expiry_hex[:2], 16) ^ 0xFF
        parts[2] = f"{first_byte:02x}" + expiry_hex[2:]
        tampered = "-".join(parts)
        with pytest.raises(LicenseError):
            validate_license_key(tampered, SECRET)

    def test_flip_hmac_byte_fails(self, pro_key: str) -> None:
        parts = pro_key.split("-")
        hmac_hex = parts[6]
        first_byte = int(hmac_hex[:2], 16) ^ 0xFF
        parts[6] = f"{first_byte:02x}" + hmac_hex[2:]
        tampered = "-".join(parts)
        with pytest.raises(LicenseError, match="invalid signature"):
            validate_license_key(tampered, SECRET)

    def test_truncated_key_fails(self) -> None:
        with pytest.raises(LicenseError, match="Invalid license key format"):
            validate_license_key("ACGS-PRO-short", SECRET)

    def test_wrong_prefix_fails(self) -> None:
        key = generate_license_key("PRO", 30, SECRET)
        bad = "XYZX-PRO-" + key[9:]
        with pytest.raises(LicenseError, match="Invalid license key format"):
            validate_license_key(bad, SECRET)

    def test_non_hex_data_fails(self) -> None:
        with pytest.raises(LicenseError, match="decode error"):
            validate_license_key("ACGS-PRO-ZZZZZZZZ-YYYY-XXXX-WWWW-VVVVVVVVVVVV", SECRET)


# ---------------------------------------------------------------------------
# LicenseManager
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLicenseManager:
    def test_default_is_free(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ACGS_LICENSE_KEY", None)
            manager = LicenseManager()
            info = manager.load()
        assert info.tier == Tier.FREE

    def test_set_license(self, pro_key: str) -> None:
        manager = LicenseManager()
        info = manager.set_license(pro_key)
        assert info.tier == Tier.PRO
        assert manager.load().tier == Tier.PRO

    def test_env_var_key_loaded(self, pro_key: str) -> None:
        with patch.dict(os.environ, {"ACGS_LICENSE_KEY": pro_key, "ACGS_LICENSE_SECRET": SECRET}):
            manager = LicenseManager()
            info = manager.load()
        assert info.tier == Tier.PRO

    def test_require_passes_when_tier_sufficient(self, pro_key: str) -> None:
        manager = LicenseManager()
        manager.set_license(pro_key)
        manager.require(Tier.PRO)  # should not raise
        manager.require(Tier.FREE)  # lower tier, also fine

    def test_require_fails_free_tier(self) -> None:
        manager = LicenseManager()  # defaults to FREE
        with pytest.raises(LicenseError, match="requires acgs-lite Pro"):
            manager.require(Tier.PRO)

    def test_require_fails_pro_needs_team(self, pro_key: str) -> None:
        manager = LicenseManager()
        manager.set_license(pro_key)
        with pytest.raises(LicenseError, match="TEAM"):
            manager.require(Tier.TEAM, "Article 13")

    def test_singleton_pattern(self) -> None:
        m1 = LicenseManager()
        m2 = LicenseManager()
        assert m1 is m2

    def test_current_tier_free(self) -> None:
        assert LicenseManager().current_tier() == Tier.FREE

    def test_license_file_loaded(self, tmp_path, pro_key: str) -> None:
        license_path = tmp_path / ".acgs-lite" / "license"
        license_path.parent.mkdir()
        license_path.write_text(pro_key + "\n")

        from acgs_lite import licensing

        original = licensing._LICENSE_FILE
        try:
            licensing._LICENSE_FILE = license_path
            manager = LicenseManager()
            info = manager.load()
            assert info.tier == Tier.PRO
        finally:
            licensing._LICENSE_FILE = original


# ---------------------------------------------------------------------------
# EU AI Act availability
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEuAiActNoGating:
    def test_article12_accessible_without_license(self) -> None:
        from acgs_lite.eu_ai_act import Article12Logger

        logger = Article12Logger(system_id="test")
        assert logger is not None

    def test_risk_classifier_accessible_without_license(self) -> None:
        from acgs_lite.eu_ai_act import RiskClassifier

        classifier = RiskClassifier()
        assert classifier is not None

    def test_transparency_accessible_without_license(self) -> None:
        from acgs_lite.eu_ai_act import TransparencyDisclosure

        td = TransparencyDisclosure(  # type: ignore[call-arg]
            system_id="test",
            system_name="Test",
            provider="Test",
            intended_purpose="Test",
            capabilities=[],
            limitations=[],
            human_oversight_measures=[],
            contact_email="test@example.com",
        )
        assert td is not None

    def test_human_oversight_accessible_without_license(self) -> None:
        from acgs_lite.eu_ai_act import HumanOversightGateway

        gw = HumanOversightGateway(system_id="test")
        assert gw is not None

    def test_enterprise_has_all_features(self, enterprise_key: str) -> None:
        info = validate_license_key(enterprise_key, SECRET)
        assert info.has_tier(Tier.PRO)
        assert info.has_tier(Tier.TEAM)
        assert info.has_tier(Tier.ENTERPRISE)
        features = info.features
        assert any("Priority support" in f for f in features)

    def test_check_license_free_returns_no_features(self) -> None:
        from acgs_lite.eu_ai_act import check_license

        result = check_license()
        assert result["tier"] == "FREE"
        assert result["pro_features"] is False
        assert result["available_classes"] == []

    def test_check_license_pro_has_pro_classes(self, pro_key: str) -> None:
        LicenseManager().set_license(pro_key)
        from acgs_lite.eu_ai_act import check_license

        result = check_license()
        assert result["tier"] == "PRO"
        assert result["pro_features"] is True
        assert result["team_features"] is False
        assert "Article12Logger" in result["available_classes"]
        assert "ComplianceChecklist" in result["available_classes"]
        assert "TransparencyDisclosure" not in result["available_classes"]


# ---------------------------------------------------------------------------
# LicenseInfo helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLicenseInfo:
    def test_has_tier_hierarchy(self, enterprise_key: str) -> None:
        info = validate_license_key(enterprise_key, SECRET)
        assert info.has_tier(Tier.FREE)
        assert info.has_tier(Tier.PRO)
        assert info.has_tier(Tier.TEAM)
        assert info.has_tier(Tier.ENTERPRISE)

    def test_free_has_no_higher_tiers(self) -> None:
        info = LicenseInfo(tier=Tier.FREE, expiry=None, key=None)
        assert info.has_tier(Tier.FREE)
        assert not info.has_tier(Tier.PRO)
        assert not info.has_tier(Tier.TEAM)

    def test_repr(self, pro_key: str) -> None:
        info = validate_license_key(pro_key, SECRET)
        r = repr(info)
        assert "PRO" in r
