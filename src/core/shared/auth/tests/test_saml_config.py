"""Tests for SAML Configuration module.

Covers SAMLSPConfig, SAMLIdPConfig, SAMLConfig dataclasses,
validation, certificate handling, and factory methods.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.core.shared.auth.saml_config import (
    SAMLConfig,
    SAMLConfigurationError,
    SAMLIdPConfig,
    SAMLSPConfig,
)


# ---------------------------------------------------------------------------
# SAMLSPConfig tests
# ---------------------------------------------------------------------------


class TestSAMLSPConfig:
    def test_creation_minimal(self):
        sp = SAMLSPConfig(entity_id="urn:test:sp", acs_url="https://sp/acs")
        assert sp.entity_id == "urn:test:sp"
        assert sp.acs_url == "https://sp/acs"
        assert sp.sign_authn_requests is True
        assert sp.want_assertions_signed is True
        assert sp.clock_skew_tolerance == 120

    def test_empty_entity_id_raises(self):
        with pytest.raises(SAMLConfigurationError, match="SP entity ID is required"):
            SAMLSPConfig(entity_id="", acs_url="https://sp/acs")

    def test_empty_acs_url_raises(self):
        with pytest.raises(SAMLConfigurationError, match="ACS URL is required"):
            SAMLSPConfig(entity_id="urn:test:sp", acs_url="")

    def test_xmlsec_auto_detect_env_var(self):
        with patch.dict(os.environ, {"SAML_XMLSEC_BINARY": "/usr/bin/xmlsec1"}), \
             patch("os.path.isfile", return_value=True):
            sp = SAMLSPConfig(entity_id="urn:test", acs_url="https://sp/acs")
            assert sp.xmlsec_binary == "/usr/bin/xmlsec1"

    def test_xmlsec_from_common_paths(self):
        def isfile_side_effect(path):
            return path == "/usr/bin/xmlsec1"

        with patch.dict(os.environ, {}, clear=True), \
             patch("os.path.isfile", side_effect=isfile_side_effect):
            # Remove SAML_XMLSEC_BINARY if present
            os.environ.pop("SAML_XMLSEC_BINARY", None)
            sp = SAMLSPConfig(entity_id="urn:test", acs_url="https://sp/acs")
            assert sp.xmlsec_binary == "/usr/bin/xmlsec1"

    def test_xmlsec_from_shutil_which(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch("os.path.isfile", return_value=False), \
             patch("shutil.which", return_value="/custom/path/xmlsec1"):
            os.environ.pop("SAML_XMLSEC_BINARY", None)
            sp = SAMLSPConfig(entity_id="urn:test", acs_url="https://sp/acs")
            assert sp.xmlsec_binary == "/custom/path/xmlsec1"

    def test_xmlsec_not_found(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch("os.path.isfile", return_value=False), \
             patch("shutil.which", return_value=None):
            os.environ.pop("SAML_XMLSEC_BINARY", None)
            sp = SAMLSPConfig(entity_id="urn:test", acs_url="https://sp/acs")
            assert sp.xmlsec_binary is None

    def test_get_cert_content_from_content(self):
        sp = SAMLSPConfig(
            entity_id="urn:test",
            acs_url="https://sp/acs",
            cert_content="CERT_DATA",
        )
        assert sp.get_cert_content() == "CERT_DATA"

    def test_get_cert_content_from_file(self, tmp_path):
        cert_file = tmp_path / "sp.crt"
        cert_file.write_text("FILE_CERT_DATA")
        sp = SAMLSPConfig(
            entity_id="urn:test",
            acs_url="https://sp/acs",
            cert_file=str(cert_file),
        )
        assert sp.get_cert_content() == "FILE_CERT_DATA"

    def test_get_cert_content_none(self):
        with patch("os.path.isfile", return_value=False), \
             patch("shutil.which", return_value=None):
            sp = SAMLSPConfig(entity_id="urn:test", acs_url="https://sp/acs")
            sp.cert_file = None
            sp.cert_content = None
            assert sp.get_cert_content() is None

    def test_get_key_content_from_content(self):
        sp = SAMLSPConfig(
            entity_id="urn:test",
            acs_url="https://sp/acs",
            key_content="KEY_DATA",
        )
        assert sp.get_key_content() == "KEY_DATA"

    def test_get_key_content_from_file(self, tmp_path):
        key_file = tmp_path / "sp.key"
        key_file.write_text("FILE_KEY_DATA")
        sp = SAMLSPConfig(
            entity_id="urn:test",
            acs_url="https://sp/acs",
            key_file=str(key_file),
        )
        assert sp.get_key_content() == "FILE_KEY_DATA"

    def test_has_signing_credentials_true(self):
        sp = SAMLSPConfig(
            entity_id="urn:test",
            acs_url="https://sp/acs",
            cert_content="CERT",
            key_content="KEY",
        )
        assert sp.has_signing_credentials() is True

    def test_has_signing_credentials_false(self):
        with patch("os.path.isfile", return_value=False), \
             patch("shutil.which", return_value=None):
            sp = SAMLSPConfig(entity_id="urn:test", acs_url="https://sp/acs")
            sp.cert_file = None
            sp.cert_content = None
            sp.key_file = None
            sp.key_content = None
            assert sp.has_signing_credentials() is False

    def test_validate_valid_config(self):
        sp = SAMLSPConfig(
            entity_id="urn:test",
            acs_url="https://sp/acs",
            cert_content="CERT",
            key_content="KEY",
            sign_authn_requests=False,
        )
        errors = sp.validate()
        assert not any("SP entity ID" in e for e in errors)
        assert not any("ACS URL" in e for e in errors)

    def test_validate_signing_without_credentials(self):
        with patch("os.path.isfile", return_value=False), \
             patch("shutil.which", return_value=None):
            sp = SAMLSPConfig(
                entity_id="urn:test",
                acs_url="https://sp/acs",
                sign_authn_requests=True,
            )
            sp.cert_file = None
            sp.cert_content = None
            sp.key_file = None
            sp.key_content = None
            errors = sp.validate()
            assert any("certificate and key" in e for e in errors)

    def test_validate_signing_without_xmlsec(self):
        with patch("os.path.isfile", return_value=False), \
             patch("shutil.which", return_value=None):
            sp = SAMLSPConfig(
                entity_id="urn:test",
                acs_url="https://sp/acs",
                sign_authn_requests=True,
            )
            sp.cert_content = "CERT"
            sp.key_content = "KEY"
            sp.cert_file = None
            sp.key_file = None
            errors = sp.validate()
            assert any("xmlsec1 binary is required" in e for e in errors)


# ---------------------------------------------------------------------------
# SAMLIdPConfig tests
# ---------------------------------------------------------------------------


class TestSAMLIdPConfig:
    def test_creation_minimal(self):
        idp = SAMLIdPConfig(name="okta")
        assert idp.name == "okta"
        assert idp.enabled is True
        assert idp.sso_binding == "redirect"

    def test_empty_name_raises(self):
        with pytest.raises(SAMLConfigurationError, match="IdP name is required"):
            SAMLIdPConfig(name="")

    def test_invalid_sso_binding_raises(self):
        with pytest.raises(SAMLConfigurationError, match="Invalid SSO binding"):
            SAMLIdPConfig(name="test", sso_binding="invalid")

    def test_invalid_slo_binding_raises(self):
        with pytest.raises(SAMLConfigurationError, match="Invalid SLO binding"):
            SAMLIdPConfig(name="test", slo_binding="invalid")

    def test_binding_normalized_to_lowercase(self):
        idp = SAMLIdPConfig(name="test", sso_binding="POST", slo_binding="REDIRECT")
        assert idp.sso_binding == "post"
        assert idp.slo_binding == "redirect"

    def test_has_metadata_url(self):
        idp = SAMLIdPConfig(name="test", metadata_url="https://idp/metadata")
        assert idp.has_metadata() is True

    def test_has_metadata_xml(self):
        idp = SAMLIdPConfig(name="test", metadata_xml="<xml/>")
        assert idp.has_metadata() is True

    def test_has_metadata_none(self):
        idp = SAMLIdPConfig(name="test")
        assert idp.has_metadata() is False

    def test_has_manual_config(self):
        idp = SAMLIdPConfig(
            name="test",
            sso_url="https://idp/sso",
            certificate="CERT",
        )
        assert idp.has_manual_config() is True

    def test_has_manual_config_false(self):
        idp = SAMLIdPConfig(name="test")
        assert idp.has_manual_config() is False

    def test_is_configured_metadata(self):
        idp = SAMLIdPConfig(name="test", metadata_url="https://idp/metadata")
        assert idp.is_configured() is True

    def test_is_configured_manual(self):
        idp = SAMLIdPConfig(
            name="test",
            sso_url="https://idp/sso",
            certificate="CERT",
        )
        assert idp.is_configured() is True

    def test_is_configured_false(self):
        idp = SAMLIdPConfig(name="test")
        assert idp.is_configured() is False

    def test_validate_no_config(self):
        idp = SAMLIdPConfig(name="test")
        errors = idp.validate()
        assert any("metadata" in e.lower() or "manual" in e.lower() for e in errors)

    def test_validate_manual_without_entity_id(self):
        idp = SAMLIdPConfig(
            name="test",
            sso_url="https://idp/sso",
            certificate="CERT",
        )
        errors = idp.validate()
        assert any("entity ID" in e for e in errors)

    def test_validate_valid_metadata(self):
        idp = SAMLIdPConfig(name="test", metadata_url="https://idp/metadata")
        errors = idp.validate()
        assert len(errors) == 0


# ---------------------------------------------------------------------------
# SAMLConfig tests
# ---------------------------------------------------------------------------


class TestSAMLConfig:
    def _make_sp(self):
        with patch("os.path.isfile", return_value=False), \
             patch("shutil.which", return_value=None):
            return SAMLSPConfig(
                entity_id="urn:test",
                acs_url="https://sp/acs",
                sign_authn_requests=False,
            )

    def test_creation(self):
        sp = self._make_sp()
        config = SAMLConfig(sp=sp)
        assert config.debug is False
        assert config.strict is True
        assert config.metadata_cache_duration == 86400

    def test_add_and_get_idp(self):
        sp = self._make_sp()
        config = SAMLConfig(sp=sp)
        idp = SAMLIdPConfig(name="okta", metadata_url="https://okta/metadata")
        config.add_idp(idp)
        assert config.get_idp("okta") is idp
        assert config.get_idp("nonexistent") is None

    def test_list_enabled_idps(self):
        sp = self._make_sp()
        config = SAMLConfig(sp=sp)
        config.add_idp(SAMLIdPConfig(name="okta", metadata_url="https://okta/m", enabled=True))
        config.add_idp(SAMLIdPConfig(name="azure", metadata_url="https://azure/m", enabled=False))
        enabled = config.list_enabled_idps()
        assert "okta" in enabled
        assert "azure" not in enabled

    def test_validate_aggregates_errors(self):
        sp = self._make_sp()
        config = SAMLConfig(sp=sp)
        # Add an IdP with no configuration
        config.add_idp(SAMLIdPConfig(name="broken"))
        errors = config.validate()
        assert any("IdP 'broken'" in e for e in errors)

    def test_from_settings(self):
        sso = MagicMock()
        sso.saml_entity_id = "urn:test:sp"
        sso.saml_sign_requests = False
        sso.saml_want_assertions_signed = True
        sso.saml_want_assertions_encrypted = False
        sso.saml_sp_certificate = "CERT_CONTENT"
        sso.saml_sp_private_key = "KEY_CONTENT"
        sso.saml_idp_metadata_url = "https://idp/metadata"
        sso.saml_idp_sso_url = "https://idp/sso"
        sso.saml_idp_slo_url = None
        sso.saml_idp_certificate = None

        settings = MagicMock()
        settings.sso = sso

        config = SAMLConfig.from_settings(settings)
        assert config.sp.entity_id == "urn:test:sp"
        assert config.sp.cert_content == "CERT_CONTENT"
        assert config.sp.key_content == "KEY_CONTENT"
        assert "default" in config.idps

    def test_from_settings_with_secret_value(self):
        sso = MagicMock()
        sso.saml_entity_id = "urn:test"
        sso.saml_sign_requests = False
        sso.saml_want_assertions_signed = True
        sso.saml_want_assertions_encrypted = False
        sso.saml_sp_certificate = None
        sso.saml_sp_private_key = MagicMock()
        sso.saml_sp_private_key.get_secret_value.return_value = "SECRET_KEY"
        sso.saml_idp_metadata_url = None

        settings = MagicMock()
        settings.sso = sso

        config = SAMLConfig.from_settings(settings)
        assert config.sp.key_content == "SECRET_KEY"

    def test_from_settings_no_sso_raises(self):
        settings = MagicMock(spec=[])
        with pytest.raises(SAMLConfigurationError, match="SSO settings not found"):
            SAMLConfig.from_settings(settings)
