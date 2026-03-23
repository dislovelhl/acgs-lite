"""
Comprehensive tests for SAML auth modules to maximize coverage.

Targets uncovered lines in:
- saml_handler.py (lines 60-62, 90-95, 319-322, 352-366, 432-435, 455-458,
                   503-523, 576-632, 645-692, 750-798, 817-848, 904-929)
- saml_config.py (lines 134, 136, 144, 146, 160, 175-186, 197-198, 210-211,
                  230-246, 298, 305, 309, 335, 346, 355, 406, 414, 422-429,
                  441-482)
- saml_types.py (lines 97-180)
- provisioning.py (lines 277, 330-456, 551-582, 601-615)
- role_mapper.py (lines 194, 313-318, 333-344, 351, 355, 392-405, 478-502,
                  518-539, 555-568)
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# saml_config.py tests
# ---------------------------------------------------------------------------


class TestSAMLSPConfigPostInit:
    """Cover __post_init__ validation in SAMLSPConfig (lines 134, 136)."""

    def test_empty_entity_id_raises(self):
        from src.core.shared.auth.saml_config import SAMLConfigurationError, SAMLSPConfig

        with pytest.raises(SAMLConfigurationError, match="entity ID"):
            SAMLSPConfig(entity_id="", acs_url="http://acs")

    def test_empty_acs_url_raises(self):
        from src.core.shared.auth.saml_config import SAMLConfigurationError, SAMLSPConfig

        with pytest.raises(SAMLConfigurationError, match="ACS URL"):
            SAMLSPConfig(entity_id="urn:test", acs_url="")


class TestSAMLSPConfigDefaultCerts:
    """Cover lines 143-146: default cert/key file usage when files exist."""

    def test_default_cert_used_when_file_exists(self, tmp_path):
        from src.core.shared.auth.saml_config import SAMLSPConfig

        cert = tmp_path / "sp.crt"
        cert.write_text("CERT")
        key = tmp_path / "sp.key"
        key.write_text("KEY")

        with (
            patch("src.core.shared.auth.saml_config.DEFAULT_SP_CERT", cert),
            patch("src.core.shared.auth.saml_config.DEFAULT_SP_KEY", key),
        ):
            cfg = SAMLSPConfig(entity_id="urn:test", acs_url="/acs")
            assert cfg.cert_file == str(cert)
            assert cfg.key_file == str(key)


class TestSAMLSPConfigFindXmlsec:
    """Cover _find_xmlsec_binary lines 160, 175-186."""

    def test_env_var_valid(self, tmp_path):
        from src.core.shared.auth.saml_config import SAMLSPConfig

        fake = tmp_path / "xmlsec1"
        fake.write_text("#!/bin/sh")
        with patch.dict(os.environ, {"SAML_XMLSEC_BINARY": str(fake)}):
            cfg = SAMLSPConfig(entity_id="urn:x", acs_url="/acs")
            assert cfg.xmlsec_binary == str(fake)

    def test_env_var_not_file(self):
        from src.core.shared.auth.saml_config import SAMLSPConfig

        with patch.dict(os.environ, {"SAML_XMLSEC_BINARY": "/nonexistent/xmlsec1"}):
            # Falls through to common paths and shutil.which
            with patch("shutil.which", return_value=None):
                with patch("os.path.isfile", side_effect=lambda p: False):
                    cfg = SAMLSPConfig(entity_id="urn:x", acs_url="/acs")
                    assert cfg.xmlsec_binary is None

    def test_shutil_which_fallback(self):
        from src.core.shared.auth.saml_config import SAMLSPConfig

        with (
            patch.dict(os.environ, {}, clear=False),
            patch("os.path.isfile", return_value=False),
            patch("shutil.which", return_value="/usr/bin/xmlsec1"),
        ):
            os.environ.pop("SAML_XMLSEC_BINARY", None)
            cfg = SAMLSPConfig(entity_id="urn:x", acs_url="/acs")
            assert cfg.xmlsec_binary == "/usr/bin/xmlsec1"

    def test_nothing_found_returns_none(self):
        from src.core.shared.auth.saml_config import SAMLSPConfig

        with (
            patch.dict(os.environ, {}, clear=False),
            patch("os.path.isfile", return_value=False),
            patch("shutil.which", return_value=None),
        ):
            os.environ.pop("SAML_XMLSEC_BINARY", None)
            cfg = SAMLSPConfig(entity_id="urn:x", acs_url="/acs")
            assert cfg.xmlsec_binary is None


class TestSAMLSPConfigGetCertContent:
    """Cover get_cert_content / get_key_content (lines 197-198, 210-211)."""

    def test_cert_content_from_file(self, tmp_path):
        from src.core.shared.auth.saml_config import SAMLSPConfig

        cert = tmp_path / "c.crt"
        cert.write_text("CERTDATA")
        cfg = SAMLSPConfig(entity_id="urn:x", acs_url="/a", cert_file=str(cert))
        assert cfg.get_cert_content() == "CERTDATA"

    def test_key_content_from_file(self, tmp_path):
        from src.core.shared.auth.saml_config import SAMLSPConfig

        key = tmp_path / "k.key"
        key.write_text("KEYDATA")
        cfg = SAMLSPConfig(entity_id="urn:x", acs_url="/a", key_file=str(key))
        assert cfg.get_key_content() == "KEYDATA"

    def test_cert_content_inline_takes_precedence(self, tmp_path):
        from src.core.shared.auth.saml_config import SAMLSPConfig

        cert = tmp_path / "c.crt"
        cert.write_text("FILE")
        cfg = SAMLSPConfig(
            entity_id="urn:x", acs_url="/a", cert_file=str(cert), cert_content="INLINE"
        )
        assert cfg.get_cert_content() == "INLINE"

    def test_key_content_inline_takes_precedence(self, tmp_path):
        from src.core.shared.auth.saml_config import SAMLSPConfig

        key = tmp_path / "k.key"
        key.write_text("FILE")
        cfg = SAMLSPConfig(
            entity_id="urn:x", acs_url="/a", key_file=str(key), key_content="INLINE"
        )
        assert cfg.get_key_content() == "INLINE"


class TestSAMLSPConfigValidate:
    """Cover validate() lines 230-246."""

    def test_validate_sign_without_creds(self):
        from src.core.shared.auth.saml_config import SAMLSPConfig

        cfg = SAMLSPConfig(entity_id="urn:x", acs_url="/a", sign_authn_requests=True)
        errors = cfg.validate()
        assert any("certificate and key" in e for e in errors)

    def test_validate_sign_without_xmlsec(self):
        from src.core.shared.auth.saml_config import SAMLSPConfig

        with (
            patch("os.path.isfile", return_value=False),
            patch("shutil.which", return_value=None),
        ):
            os.environ.pop("SAML_XMLSEC_BINARY", None)
            cfg = SAMLSPConfig(
                entity_id="urn:x",
                acs_url="/a",
                sign_authn_requests=True,
                cert_content="CERT",
                key_content="KEY",
            )
            assert cfg.xmlsec_binary is None
            errors = cfg.validate()
            assert any("xmlsec1 binary is required" in e for e in errors)

    def test_validate_sign_xmlsec_not_found(self, tmp_path):
        from src.core.shared.auth.saml_config import SAMLSPConfig

        cfg = SAMLSPConfig(
            entity_id="urn:x",
            acs_url="/a",
            sign_authn_requests=True,
            cert_content="CERT",
            key_content="KEY",
            xmlsec_binary="/nonexistent/xmlsec1",
        )
        errors = cfg.validate()
        assert any("not found at" in e for e in errors)

    def test_validate_no_sign_no_errors(self):
        from src.core.shared.auth.saml_config import SAMLSPConfig

        cfg = SAMLSPConfig(entity_id="urn:x", acs_url="/a", sign_authn_requests=False)
        errors = cfg.validate()
        assert not errors


class TestSAMLIdPConfigPostInit:
    """Cover IdP __post_init__ lines 298, 305, 309."""

    def test_empty_name_raises(self):
        from src.core.shared.auth.saml_config import SAMLConfigurationError, SAMLIdPConfig

        with pytest.raises(SAMLConfigurationError, match="name is required"):
            SAMLIdPConfig(name="")

    def test_invalid_sso_binding_raises(self):
        from src.core.shared.auth.saml_config import SAMLConfigurationError, SAMLIdPConfig

        with pytest.raises(SAMLConfigurationError, match="Invalid SSO binding"):
            SAMLIdPConfig(name="test", sso_binding="invalid")

    def test_invalid_slo_binding_raises(self):
        from src.core.shared.auth.saml_config import SAMLConfigurationError, SAMLIdPConfig

        with pytest.raises(SAMLConfigurationError, match="Invalid SLO binding"):
            SAMLIdPConfig(name="test", slo_binding="invalid")


class TestSAMLIdPConfigMethods:
    """Cover IdP helper methods lines 335, 346, 355."""

    def test_is_configured_with_metadata_url(self):
        from src.core.shared.auth.saml_config import SAMLIdPConfig

        idp = SAMLIdPConfig(name="test", metadata_url="http://meta")
        assert idp.is_configured()

    def test_is_configured_with_manual(self):
        from src.core.shared.auth.saml_config import SAMLIdPConfig

        idp = SAMLIdPConfig(name="test", sso_url="http://sso", certificate="CERT")
        assert idp.is_configured()

    def test_not_configured(self):
        from src.core.shared.auth.saml_config import SAMLIdPConfig

        idp = SAMLIdPConfig(name="test")
        assert not idp.is_configured()

    def test_validate_no_config(self):
        from src.core.shared.auth.saml_config import SAMLIdPConfig

        idp = SAMLIdPConfig(name="test")
        errors = idp.validate()
        assert any("metadata" in e.lower() or "manual" in e.lower() for e in errors)

    def test_validate_manual_no_entity_id(self):
        from src.core.shared.auth.saml_config import SAMLIdPConfig

        idp = SAMLIdPConfig(name="test", sso_url="http://sso", certificate="CERT")
        errors = idp.validate()
        assert any("entity ID" in e for e in errors)

    def test_validate_ok_with_metadata(self):
        from src.core.shared.auth.saml_config import SAMLIdPConfig

        idp = SAMLIdPConfig(name="test", metadata_url="http://meta")
        errors = idp.validate()
        assert not errors


class TestSAMLConfigMethods:
    """Cover SAMLConfig lines 406, 414, 422-429."""

    def test_get_idp(self):
        from src.core.shared.auth.saml_config import SAMLConfig, SAMLIdPConfig, SAMLSPConfig

        sp = SAMLSPConfig(entity_id="urn:x", acs_url="/a")
        cfg = SAMLConfig(sp=sp)
        idp = SAMLIdPConfig(name="okta", metadata_url="http://m")
        cfg.add_idp(idp)
        assert cfg.get_idp("okta") is idp
        assert cfg.get_idp("nonexistent") is None

    def test_list_enabled_idps(self):
        from src.core.shared.auth.saml_config import SAMLConfig, SAMLIdPConfig, SAMLSPConfig

        sp = SAMLSPConfig(entity_id="urn:x", acs_url="/a")
        cfg = SAMLConfig(sp=sp)
        cfg.add_idp(SAMLIdPConfig(name="a", metadata_url="http://m", enabled=True))
        cfg.add_idp(SAMLIdPConfig(name="b", metadata_url="http://m", enabled=False))
        assert cfg.list_enabled_idps() == ["a"]

    def test_validate_aggregates_errors(self):
        from src.core.shared.auth.saml_config import SAMLConfig, SAMLIdPConfig, SAMLSPConfig

        sp = SAMLSPConfig(entity_id="urn:x", acs_url="/a", sign_authn_requests=False)
        cfg = SAMLConfig(sp=sp)
        # IdP with no config
        cfg.add_idp(SAMLIdPConfig(name="bad"))
        errors = cfg.validate()
        assert any("IdP 'bad'" in e for e in errors)


class TestSAMLConfigFromSettings:
    """Cover from_settings lines 441-482."""

    def test_from_settings_no_sso(self):
        from src.core.shared.auth.saml_config import SAMLConfig, SAMLConfigurationError

        settings = MagicMock(spec=[])
        with pytest.raises(SAMLConfigurationError, match="SSO settings not found"):
            SAMLConfig.from_settings(settings)

    def test_from_settings_basic(self):
        from src.core.shared.auth.saml_config import SAMLConfig

        sso = MagicMock()
        sso.saml_entity_id = "urn:test"
        sso.saml_sign_requests = False
        sso.saml_want_assertions_signed = True
        sso.saml_want_assertions_encrypted = False
        sso.saml_sp_certificate = "CERT"
        sso.saml_sp_private_key = "KEY"
        sso.saml_idp_metadata_url = "http://idp/meta"
        sso.saml_idp_sso_url = "http://idp/sso"
        sso.saml_idp_slo_url = "http://idp/slo"
        sso.saml_idp_certificate = "IDP_CERT"

        settings = MagicMock()
        settings.sso = sso

        cfg = SAMLConfig.from_settings(settings)
        assert cfg.sp.entity_id == "urn:test"
        assert cfg.sp.cert_content == "CERT"
        assert cfg.sp.key_content == "KEY"
        assert "default" in cfg.idps

    def test_from_settings_secret_key(self):
        from src.core.shared.auth.saml_config import SAMLConfig

        secret_key = MagicMock()
        secret_key.get_secret_value.return_value = "SECRET_KEY"

        sso = MagicMock()
        sso.saml_entity_id = "urn:t"
        sso.saml_sign_requests = False
        sso.saml_want_assertions_signed = True
        sso.saml_want_assertions_encrypted = False
        sso.saml_sp_certificate = None
        sso.saml_sp_private_key = secret_key
        sso.saml_idp_metadata_url = None

        settings = MagicMock()
        settings.sso = sso

        cfg = SAMLConfig.from_settings(settings)
        assert cfg.sp.key_content == "SECRET_KEY"

    def test_from_settings_no_idp_metadata(self):
        from src.core.shared.auth.saml_config import SAMLConfig

        sso = MagicMock()
        sso.saml_entity_id = "urn:t"
        sso.saml_sign_requests = False
        sso.saml_want_assertions_signed = True
        sso.saml_want_assertions_encrypted = False
        sso.saml_sp_certificate = None
        sso.saml_sp_private_key = None
        sso.saml_idp_metadata_url = None

        settings = MagicMock()
        settings.sso = sso

        cfg = SAMLConfig.from_settings(settings)
        assert len(cfg.idps) == 0


# ---------------------------------------------------------------------------
# saml_types.py tests
# ---------------------------------------------------------------------------


class TestSAMLUserInfoFromResponse:
    """Cover SAMLUserInfo.from_response lines 97-180."""

    def test_no_pysaml2_raises(self):
        from src.core.shared.auth.saml_types import SAMLUserInfo

        with pytest.raises(Exception, match="PySAML2"):
            SAMLUserInfo.from_response(MagicMock(), has_pysaml2=False)

    def test_full_attribute_extraction(self):
        from src.core.shared.auth.saml_types import SAMLUserInfo

        name_id = MagicMock()
        name_id.__str__ = lambda self: "user@example.com"
        name_id.format = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"

        response = MagicMock()
        response.name_id = name_id
        response.session_info.return_value = {"session_index": "_sess123"}
        response.ava = {
            "email": ["user@example.com"],
            "name": ["John Doe"],
            "givenName": ["John"],
            "surname": ["Doe"],
            "groups": ["Engineering", "Admin"],
        }
        response.issuer.return_value = "http://idp.example.com"

        info = SAMLUserInfo.from_response(response, has_pysaml2=True)
        assert info.name_id == "user@example.com"
        assert info.email == "user@example.com"
        assert info.name == "John Doe"
        assert info.given_name == "John"
        assert info.family_name == "Doe"
        assert info.groups == ["Engineering", "Admin"]
        assert info.issuer == "http://idp.example.com"
        assert info.session_index == "_sess123"

    def test_claims_uri_attributes(self):
        from src.core.shared.auth.saml_types import SAMLUserInfo

        name_id = MagicMock()
        name_id.__str__ = lambda self: "u@e.com"
        name_id.format = None

        response = MagicMock()
        response.name_id = name_id
        response.session_info.return_value = {}
        response.ava = {
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress": ["alt@e.com"],
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name": ["Alt Name"],
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname": ["Alt"],
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname": ["Name"],
            "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups": ["G1"],
        }
        response.issuer.return_value = None

        info = SAMLUserInfo.from_response(response, has_pysaml2=True)
        assert info.email == "alt@e.com"
        assert info.name == "Alt Name"
        assert info.given_name == "Alt"
        assert info.family_name == "Name"
        assert info.groups == ["G1"]

    def test_no_name_id(self):
        from src.core.shared.auth.saml_types import SAMLUserInfo

        response = MagicMock()
        response.name_id = None
        response.session_info.return_value = {}
        response.ava = {}
        response.issuer.return_value = None

        info = SAMLUserInfo.from_response(response, has_pysaml2=True)
        assert info.name_id == ""
        assert info.email == ""  # Falls back to empty name_id

    def test_empty_attr_lists(self):
        from src.core.shared.auth.saml_types import SAMLUserInfo

        name_id = MagicMock()
        name_id.__str__ = lambda self: "u"
        name_id.format = "fmt"

        response = MagicMock()
        response.name_id = name_id
        response.session_info.return_value = {}
        response.ava = {
            "email": [],
            "name": [],
            "givenName": [],
            "surname": [],
            "groups": [],
        }
        response.issuer.return_value = None

        info = SAMLUserInfo.from_response(response, has_pysaml2=True)
        assert info.email is None or info.email == "u"  # Falls back to name_id
        assert info.groups == []

    def test_no_issuer_method(self):
        from src.core.shared.auth.saml_types import SAMLUserInfo

        name_id = MagicMock()
        name_id.__str__ = lambda self: "u"
        name_id.format = None

        response = MagicMock(spec=[])
        response.name_id = name_id
        response.session_info = MagicMock(return_value={})
        response.ava = {}

        info = SAMLUserInfo.from_response(response, has_pysaml2=True)
        assert info.issuer is None

    def test_alt_email_attrs(self):
        """Cover emailAddress and mail attribute paths."""
        from src.core.shared.auth.saml_types import SAMLUserInfo

        name_id = MagicMock()
        name_id.__str__ = lambda self: "u"
        name_id.format = None

        response = MagicMock()
        response.name_id = name_id
        response.session_info.return_value = {}
        response.ava = {"mail": ["mail@example.com"]}
        response.issuer.return_value = None

        info = SAMLUserInfo.from_response(response, has_pysaml2=True)
        assert info.email == "mail@example.com"

    def test_alt_name_attrs(self):
        """Cover displayName, cn, firstName, lastName, familyName, memberOf."""
        from src.core.shared.auth.saml_types import SAMLUserInfo

        name_id = MagicMock()
        name_id.__str__ = lambda self: "u"
        name_id.format = None

        response = MagicMock()
        response.name_id = name_id
        response.session_info.return_value = {}
        response.ava = {
            "displayName": ["Display"],
            "firstName": ["First"],
            "lastName": ["Last"],
            "memberOf": ["Group1", "Group2"],
        }
        response.issuer.return_value = None

        info = SAMLUserInfo.from_response(response, has_pysaml2=True)
        assert info.name == "Display"
        assert info.given_name == "First"
        assert info.family_name == "Last"
        assert info.groups == ["Group1", "Group2"]

    def test_emailAddress_attr(self):
        """Cover emailAddress attribute key."""
        from src.core.shared.auth.saml_types import SAMLUserInfo

        name_id = MagicMock()
        name_id.__str__ = lambda self: "u"
        name_id.format = None

        response = MagicMock()
        response.name_id = name_id
        response.session_info.return_value = {}
        response.ava = {"emailAddress": ["ea@example.com"]}
        response.issuer.return_value = None

        info = SAMLUserInfo.from_response(response, has_pysaml2=True)
        assert info.email == "ea@example.com"

    def test_cn_attr(self):
        """Cover cn attribute key for name."""
        from src.core.shared.auth.saml_types import SAMLUserInfo

        name_id = MagicMock()
        name_id.__str__ = lambda self: "u"
        name_id.format = None

        response = MagicMock()
        response.name_id = name_id
        response.session_info.return_value = {}
        response.ava = {
            "cn": ["Common Name"],
            "sn": ["Surname"],
            "familyName": ["Family"],  # Won't be used since sn comes first
        }
        response.issuer.return_value = None

        info = SAMLUserInfo.from_response(response, has_pysaml2=True)
        assert info.name == "Common Name"
        assert info.family_name == "Surname"


# ---------------------------------------------------------------------------
# saml_handler.py tests
# ---------------------------------------------------------------------------


class TestSAMLHandlerInit:
    """Cover handler init and basic methods."""

    def test_default_init(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        assert handler.sp_config.entity_id == "urn:acgs2:saml:sp"

    def test_init_with_sp_config(self):
        from src.core.shared.auth.saml_config import SAMLSPConfig
        from src.core.shared.auth.saml_handler import SAMLHandler

        sp = SAMLSPConfig(entity_id="urn:custom", acs_url="/custom/acs")
        handler = SAMLHandler(sp_config=sp)
        assert handler.sp_config.entity_id == "urn:custom"

    def test_init_with_full_config(self):
        from src.core.shared.auth.saml_config import SAMLConfig, SAMLSPConfig
        from src.core.shared.auth.saml_handler import SAMLHandler

        sp = SAMLSPConfig(entity_id="urn:full", acs_url="/full/acs")
        config = SAMLConfig(sp=sp)
        handler = SAMLHandler(config=config)
        assert handler.sp_config.entity_id == "urn:full"


class TestSAMLHandlerRegisterIdP:
    """Cover register_idp and related."""

    def test_register_idp_with_metadata_url(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://meta")
        assert "okta" in handler.list_idps()
        assert handler.get_idp("okta").metadata_url == "http://meta"

    def test_register_idp_invalid_raises(self):
        from src.core.shared.auth.saml_config import SAMLConfigurationError
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        with pytest.raises(SAMLConfigurationError, match="Invalid IdP"):
            handler.register_idp(name="bad")

    def test_register_clears_cached_client(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        handler._saml_clients["okta"] = MagicMock()
        handler.register_idp(name="okta", metadata_url="http://meta")
        assert "okta" not in handler._saml_clients

    def test_get_idp_not_registered(self):
        from src.core.shared.auth.saml_config import SAMLConfigurationError
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        with pytest.raises(SAMLConfigurationError, match="not registered"):
            handler.get_idp("missing")


class TestSAMLHandlerRegisterIdPFromModel:
    """Cover register_idp_from_model line 277 (not SAML) path."""

    def test_not_saml_raises(self):
        from src.core.shared.auth.saml_config import SAMLConfigurationError
        from src.core.shared.auth.saml_handler import SAMLHandler

        provider = MagicMock()
        provider.is_saml = False
        provider.name = "oidc-provider"

        handler = SAMLHandler()
        with pytest.raises(SAMLConfigurationError, match="not a SAML"):
            handler.register_idp_from_model(provider)

    def test_saml_validation_errors(self):
        from src.core.shared.auth.saml_config import SAMLConfigurationError
        from src.core.shared.auth.saml_handler import SAMLHandler

        provider = MagicMock()
        provider.is_saml = True
        provider.name = "bad-saml"
        provider.validate_saml_config.return_value = ["missing cert"]

        handler = SAMLHandler()
        with pytest.raises(SAMLConfigurationError, match="Invalid SAML"):
            handler.register_idp_from_model(provider)


class TestSAMLHandlerHttpClient:
    """Cover _get_http_client lines 319-322."""

    @pytest.mark.asyncio
    async def test_get_http_client_no_httpx(self):
        from src.core.shared.auth.saml_handler import SAMLHandler
        from src.core.shared.auth.saml_types import SAMLError

        handler = SAMLHandler()
        with patch("src.core.shared.auth.saml_handler.HAS_HTTPX", False):
            with pytest.raises(SAMLError, match="httpx"):
                await handler._get_http_client()

    @pytest.mark.asyncio
    async def test_get_http_client_creates_client(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        mock_client = MagicMock()
        with (
            patch("src.core.shared.auth.saml_handler.HAS_HTTPX", True),
            patch("src.core.shared.auth.saml_handler.httpx") as mock_httpx,
        ):
            mock_httpx.AsyncClient.return_value = mock_client
            mock_httpx.Timeout = MagicMock()
            client = await handler._get_http_client()
            assert client is mock_client
            # Second call returns cached
            client2 = await handler._get_http_client()
            assert client2 is mock_client


class TestSAMLHandlerFetchMetadata:
    """Cover _fetch_metadata lines 352-366."""

    @pytest.mark.asyncio
    async def test_returns_inline_xml(self):
        from src.core.shared.auth.saml_config import SAMLIdPConfig
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        idp = SAMLIdPConfig(name="test", metadata_xml="<xml/>")
        result = await handler._fetch_metadata(idp)
        assert result == "<xml/>"

    @pytest.mark.asyncio
    async def test_returns_cached(self):
        from src.core.shared.auth.saml_config import SAMLIdPConfig
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        idp = SAMLIdPConfig(name="test", metadata_url="http://meta")
        handler._metadata_cache["test"] = ("<cached/>", datetime.now(UTC))
        result = await handler._fetch_metadata(idp)
        assert result == "<cached/>"

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        from src.core.shared.auth.saml_config import SAMLIdPConfig
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        idp = SAMLIdPConfig(name="test", metadata_url="http://meta")

        mock_response = MagicMock()
        mock_response.text = "<fresh/>"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        handler._http_client = mock_client

        with patch("src.core.shared.auth.saml_handler.HAS_HTTPX", True):
            result = await handler._fetch_metadata(idp, force_refresh=True)
            assert result == "<fresh/>"
            assert "test" in handler._metadata_cache

    @pytest.mark.asyncio
    async def test_fetch_error_uses_cache(self):
        from src.core.shared.auth.saml_config import SAMLIdPConfig
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        idp = SAMLIdPConfig(name="test", metadata_url="http://meta")
        handler._metadata_cache["test"] = ("<old/>", datetime.now(UTC))

        mock_client = AsyncMock()
        mock_client.get.side_effect = RuntimeError("network error")
        handler._http_client = mock_client

        with patch("src.core.shared.auth.saml_handler.HAS_HTTPX", True):
            result = await handler._fetch_metadata(idp, force_refresh=True)
            assert result == "<old/>"

    @pytest.mark.asyncio
    async def test_fetch_error_no_cache_raises(self):
        from src.core.shared.auth.saml_config import SAMLIdPConfig
        from src.core.shared.auth.saml_handler import SAMLHandler
        from src.core.shared.auth.saml_types import SAMLProviderError

        handler = SAMLHandler()
        idp = SAMLIdPConfig(name="test", metadata_url="http://meta")

        mock_client = AsyncMock()
        mock_client.get.side_effect = RuntimeError("network error")
        handler._http_client = mock_client

        with (
            patch("src.core.shared.auth.saml_handler.HAS_HTTPX", True),
            pytest.raises(SAMLProviderError, match="Failed to fetch"),
        ):
            await handler._fetch_metadata(idp, force_refresh=True)


class TestSAMLHandlerBuildConfig:
    """Cover _build_pysaml2_config lines 432-435, 455-458."""

    def test_build_with_certs(self, tmp_path):
        from src.core.shared.auth.saml_config import SAMLIdPConfig, SAMLSPConfig
        from src.core.shared.auth.saml_handler import SAMLHandler

        sp = SAMLSPConfig(
            entity_id="urn:x",
            acs_url="/acs",
            sls_url="/sls",
            cert_content="CERT",
            key_content="KEY",
        )
        handler = SAMLHandler(sp_config=sp)
        idp = SAMLIdPConfig(name="test", metadata_url="http://m")

        config = handler._build_pysaml2_config(idp, "<metadata/>")
        assert "cert_file" in config
        assert "key_file" in config
        assert "metadata" in config

    def test_build_manual_idp(self):
        from src.core.shared.auth.saml_config import SAMLIdPConfig, SAMLSPConfig
        from src.core.shared.auth.saml_handler import SAMLHandler

        sp = SAMLSPConfig(entity_id="urn:x", acs_url="/acs")
        handler = SAMLHandler(sp_config=sp)
        idp = SAMLIdPConfig(
            name="manual",
            entity_id="urn:idp",
            sso_url="http://sso",
            slo_url="http://slo",
            certificate="CERT",
        )

        config = handler._build_pysaml2_config(idp, None)
        assert config["metadata"]["inline"][0]["entity_id"] == "urn:idp"

    def test_build_cleanup_old_temp_files(self):
        from src.core.shared.auth.saml_config import SAMLIdPConfig, SAMLSPConfig
        from src.core.shared.auth.saml_handler import SAMLHandler

        sp = SAMLSPConfig(entity_id="urn:x", acs_url="/acs", cert_content="C", key_content="K")
        handler = SAMLHandler(sp_config=sp)
        idp = SAMLIdPConfig(name="t", metadata_url="http://m")

        # Set old temp files
        old_cert = MagicMock()
        old_cert.name = "/tmp/old.crt"
        old_key = MagicMock()
        old_key.name = "/tmp/old.key"
        old_meta = MagicMock()
        old_meta.name = "/tmp/old.xml"
        handler._temp_cert_file = old_cert
        handler._temp_key_file = old_key
        handler._temp_metadata_file = old_meta

        with patch("pathlib.Path.unlink"):
            config = handler._build_pysaml2_config(idp, "<xml/>")
            assert "cert_file" in config


class TestSAMLHandlerGetSamlClient:
    """Cover _get_saml_client lines 503-523."""

    @pytest.mark.asyncio
    async def test_no_pysaml2_raises(self):
        from src.core.shared.auth.saml_handler import SAMLHandler
        from src.core.shared.auth.saml_types import SAMLError

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://m")
        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", False):
            with pytest.raises(SAMLError, match="PySAML2"):
                await handler._get_saml_client("okta")

    @pytest.mark.asyncio
    async def test_returns_cached_client(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://m")
        mock_client = MagicMock()
        handler._saml_clients["okta"] = mock_client
        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True):
            result = await handler._get_saml_client("okta")
            assert result is mock_client

    @pytest.mark.asyncio
    async def test_creates_new_client(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://m")

        mock_config = MagicMock()
        mock_client = MagicMock()

        with (
            patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True),
            patch.object(handler, "_fetch_metadata", new_callable=AsyncMock, return_value="<xml/>"),
            patch("src.core.shared.auth.saml_handler.Saml2Config", return_value=mock_config),
            patch("src.core.shared.auth.saml_handler.Saml2Client", return_value=mock_client),
        ):
            result = await handler._get_saml_client("okta")
            assert result is mock_client
            assert handler._saml_clients["okta"] is mock_client


class TestSAMLHandlerInitiateLogin:
    """Cover initiate_login lines 576-632."""

    @pytest.mark.asyncio
    async def test_initiate_login_success(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://m", entity_id="urn:idp")

        mock_client = MagicMock()
        mock_client.prepare_for_authenticate.return_value = (
            "req_123",
            {"headers": [("Location", "http://idp/login?SAMLRequest=abc")]},
        )

        with (
            patch.object(
                handler, "_get_saml_client", new_callable=AsyncMock, return_value=mock_client
            ),
        ):
            url, req_id = await handler.initiate_login("okta", relay_state="/dashboard")
            assert url == "http://idp/login?SAMLRequest=abc"
            assert req_id == "req_123"

    @pytest.mark.asyncio
    async def test_initiate_login_no_entity_id_from_metadata(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://m")

        mock_client = MagicMock()
        mock_client.metadata.identity_providers.return_value = ["urn:idp:auto"]
        mock_client.prepare_for_authenticate.return_value = (
            "req_456",
            {"headers": [("Location", "http://idp/login")]},
        )

        with patch.object(
            handler, "_get_saml_client", new_callable=AsyncMock, return_value=mock_client
        ):
            url, req_id = await handler.initiate_login("okta")
            assert url == "http://idp/login"

    @pytest.mark.asyncio
    async def test_initiate_login_no_entity_id_raises(self):
        from src.core.shared.auth.saml_config import SAMLConfigurationError
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://m")

        mock_client = MagicMock()
        mock_client.metadata.identity_providers.return_value = []

        with (
            patch.object(
                handler, "_get_saml_client", new_callable=AsyncMock, return_value=mock_client
            ),
            pytest.raises(SAMLConfigurationError, match="Cannot determine entity ID"),
        ):
            await handler.initiate_login("okta")

    @pytest.mark.asyncio
    async def test_initiate_login_no_redirect_url(self):
        from src.core.shared.auth.saml_handler import SAMLHandler
        from src.core.shared.auth.saml_types import SAMLError

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://m", entity_id="urn:idp")

        mock_client = MagicMock()
        mock_client.prepare_for_authenticate.return_value = (
            "req_789",
            {"headers": [("X-Other", "value")]},
        )

        class _NarrowExc(Exception):
            pass

        with (
            patch.object(
                handler, "_get_saml_client", new_callable=AsyncMock, return_value=mock_client
            ),
            patch("src.core.shared.auth.saml_handler.UnknownPrincipal", _NarrowExc),
            patch("src.core.shared.auth.saml_handler.UnsupportedBinding", _NarrowExc),
            pytest.raises(SAMLError, match="redirect URL"),
        ):
            await handler.initiate_login("okta")

    @pytest.mark.asyncio
    async def test_initiate_login_unknown_principal(self):
        from src.core.shared.auth.saml_config import SAMLConfigurationError
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://m", entity_id="urn:idp")

        mock_client = MagicMock()
        # Use the fallback exception class
        from src.core.shared.auth.saml_handler import UnknownPrincipal

        mock_client.prepare_for_authenticate.side_effect = UnknownPrincipal("bad principal")

        with (
            patch.object(
                handler, "_get_saml_client", new_callable=AsyncMock, return_value=mock_client
            ),
            pytest.raises(SAMLConfigurationError, match="configuration error"),
        ):
            await handler.initiate_login("okta")

    @pytest.mark.asyncio
    async def test_initiate_login_runtime_error(self):
        """Cover the generic error handler (line 631-632).

        Note: When pysaml2 is not installed, UnknownPrincipal = Exception,
        so RuntimeError is caught by the first handler. Use a patched
        UnknownPrincipal that doesn't catch our test error.
        """
        from src.core.shared.auth.saml_handler import SAMLHandler
        from src.core.shared.auth.saml_types import SAMLError

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://m", entity_id="urn:idp")

        mock_client = MagicMock()
        mock_client.prepare_for_authenticate.side_effect = TypeError("type fail")

        # Patch UnknownPrincipal/UnsupportedBinding to narrow exception classes
        # so our TypeError falls through to the generic handler
        class _NarrowExc(Exception):
            pass

        with (
            patch.object(
                handler, "_get_saml_client", new_callable=AsyncMock, return_value=mock_client
            ),
            patch("src.core.shared.auth.saml_handler.UnknownPrincipal", _NarrowExc),
            patch("src.core.shared.auth.saml_handler.UnsupportedBinding", _NarrowExc),
            pytest.raises(SAMLError, match="Failed to initiate"),
        ):
            await handler.initiate_login("okta")

    @pytest.mark.asyncio
    async def test_initiate_login_idp_entity_detect_oserror(self):
        """Cover the OSError/PermissionError/RuntimeError catch in entity_id detection."""
        from src.core.shared.auth.saml_config import SAMLConfigurationError
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://m")

        mock_client = MagicMock()
        mock_client.metadata.identity_providers.side_effect = OSError("disk error")

        with (
            patch.object(
                handler, "_get_saml_client", new_callable=AsyncMock, return_value=mock_client
            ),
            pytest.raises(SAMLConfigurationError, match="Cannot determine"),
        ):
            await handler.initiate_login("okta")


class TestSAMLHandlerProcessACS:
    """Cover process_acs_response lines 645-692."""

    @pytest.mark.asyncio
    async def test_process_no_pysaml2(self):
        from src.core.shared.auth.saml_handler import SAMLHandler
        from src.core.shared.auth.saml_types import SAMLError

        handler = SAMLHandler()
        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", False):
            with pytest.raises(SAMLError, match="PySAML2"):
                await handler.process_acs_response("response")

    @pytest.mark.asyncio
    async def test_process_success(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://m")
        req_id = handler.store_outstanding_request(idp_name="okta")

        mock_name_id = MagicMock()
        mock_name_id.__str__ = lambda s: "user@test.com"
        mock_name_id.format = None

        mock_response = MagicMock()
        mock_response.name_id = mock_name_id
        mock_response.session_info.return_value = {}
        mock_response.ava = {"email": ["user@test.com"]}
        mock_response.issuer.return_value = "urn:idp"

        mock_client = MagicMock()
        mock_client.parse_authn_request_response.return_value = mock_response

        with (
            patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True),
            patch.object(
                handler, "_get_saml_client", new_callable=AsyncMock, return_value=mock_client
            ),
        ):
            info = await handler.process_acs_response("response", request_id=req_id, idp_name="okta")
            assert info.email == "user@test.com"

    @pytest.mark.asyncio
    async def test_process_none_response(self):
        from src.core.shared.auth.saml_handler import SAMLHandler
        from src.core.shared.auth.saml_types import SAMLValidationError

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://m")

        mock_client = MagicMock()
        mock_client.parse_authn_request_response.return_value = None

        with (
            patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True),
            patch.object(
                handler, "_get_saml_client", new_callable=AsyncMock, return_value=mock_client
            ),
            pytest.raises(SAMLValidationError, match="Failed to parse"),
        ):
            await handler.process_acs_response("response", idp_name="okta")

    @pytest.mark.asyncio
    async def test_process_replay_detected(self):
        from src.core.shared.auth.saml_handler import SAMLHandler
        from src.core.shared.auth.saml_types import SAMLReplayError

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://m")

        mock_name_id = MagicMock()
        mock_name_id.__str__ = lambda s: "u"
        mock_name_id.format = None

        mock_response = MagicMock()
        mock_response.name_id = mock_name_id
        mock_response.session_info.return_value = {}
        mock_response.ava = {}
        mock_response.issuer.return_value = None

        mock_client = MagicMock()
        mock_client.parse_authn_request_response.return_value = mock_response

        with (
            patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True),
            patch.object(
                handler, "_get_saml_client", new_callable=AsyncMock, return_value=mock_client
            ),
            pytest.raises(SAMLReplayError),
        ):
            # Pass a request_id that doesn't exist -> replay
            await handler.process_acs_response("r", request_id="fake_id", idp_name="okta")

    @pytest.mark.asyncio
    async def test_process_runtime_error(self):
        from src.core.shared.auth.saml_handler import SAMLHandler
        from src.core.shared.auth.saml_types import SAMLValidationError

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://m")

        mock_client = MagicMock()
        mock_client.parse_authn_request_response.side_effect = RuntimeError("bad")

        with (
            patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True),
            patch.object(
                handler, "_get_saml_client", new_callable=AsyncMock, return_value=mock_client
            ),
            pytest.raises(SAMLValidationError, match="validation failed"),
        ):
            await handler.process_acs_response("r", idp_name="okta")

    @pytest.mark.asyncio
    async def test_detect_idp_from_request(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://m")
        req_id = handler.store_outstanding_request(idp_name="okta")

        result = handler._detect_idp_name(req_id)
        assert result == "okta"

    def test_detect_idp_no_request_uses_first(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        handler.register_idp(name="first", metadata_url="http://m")
        handler.register_idp(name="second", metadata_url="http://m2")

        result = handler._detect_idp_name(None)
        assert result == "first"

    def test_detect_idp_no_idps_raises(self):
        from src.core.shared.auth.saml_config import SAMLConfigurationError
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        with pytest.raises(SAMLConfigurationError, match="No IdPs"):
            handler._detect_idp_name(None)


class TestSAMLHandlerInitiateLogout:
    """Cover initiate_logout lines 750-798."""

    @pytest.mark.asyncio
    async def test_no_pysaml2_returns_none(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://m")
        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", False):
            result = await handler.initiate_logout("okta", name_id="user")
            assert result is None

    @pytest.mark.asyncio
    async def test_no_slo_url_returns_none(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://m")
        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True):
            result = await handler.initiate_logout("okta", name_id="user")
            assert result is None

    @pytest.mark.asyncio
    async def test_logout_success(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        handler.register_idp(
            name="okta", metadata_url="http://m", entity_id="urn:idp", slo_url="http://slo"
        )

        mock_client = MagicMock()
        mock_client.do_logout.return_value = (
            "logout_req",
            {"headers": [("Location", "http://idp/logout")]},
        )

        with (
            patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True),
            patch.object(
                handler, "_get_saml_client", new_callable=AsyncMock, return_value=mock_client
            ),
        ):
            result = await handler.initiate_logout(
                "okta", name_id="user", session_index="_sess", relay_state="/home"
            )
            assert "http://idp/logout" in result
            assert "RelayState" in result

    @pytest.mark.asyncio
    async def test_logout_no_entity_id_from_metadata(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://m", slo_url="http://slo")

        mock_client = MagicMock()
        mock_client.metadata.identity_providers.return_value = []

        with (
            patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True),
            patch.object(
                handler, "_get_saml_client", new_callable=AsyncMock, return_value=mock_client
            ),
        ):
            result = await handler.initiate_logout("okta", name_id="user")
            assert result is None

    @pytest.mark.asyncio
    async def test_logout_with_entity_from_metadata(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://m", slo_url="http://slo")

        mock_client = MagicMock()
        mock_client.metadata.identity_providers.return_value = ["urn:auto"]
        mock_client.do_logout.return_value = (
            "req",
            {"headers": [("Location", "http://idp/logout?q=1")]},
        )

        with (
            patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True),
            patch.object(
                handler, "_get_saml_client", new_callable=AsyncMock, return_value=mock_client
            ),
        ):
            result = await handler.initiate_logout(
                "okta", name_id="user", relay_state="/dashboard"
            )
            assert "RelayState" in result
            assert "&" in result  # Uses & separator since ? already exists

    @pytest.mark.asyncio
    async def test_logout_error_returns_none(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        handler.register_idp(
            name="okta", metadata_url="http://m", entity_id="urn:idp", slo_url="http://slo"
        )

        mock_client = MagicMock()
        mock_client.do_logout.side_effect = RuntimeError("fail")

        with (
            patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True),
            patch.object(
                handler, "_get_saml_client", new_callable=AsyncMock, return_value=mock_client
            ),
        ):
            result = await handler.initiate_logout("okta", name_id="user")
            assert result is None

    @pytest.mark.asyncio
    async def test_logout_no_location_no_relay(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        handler.register_idp(
            name="okta", metadata_url="http://m", entity_id="urn:idp", slo_url="http://slo"
        )

        mock_client = MagicMock()
        mock_client.do_logout.return_value = ("req", {"headers": []})

        with (
            patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True),
            patch.object(
                handler, "_get_saml_client", new_callable=AsyncMock, return_value=mock_client
            ),
        ):
            result = await handler.initiate_logout("okta", name_id="user")
            assert result is None


class TestSAMLHandlerProcessSLS:
    """Cover process_sls_response lines 817-848."""

    @pytest.mark.asyncio
    async def test_no_pysaml2_returns_true(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", False):
            result = await handler.process_sls_response("resp", "okta")
            assert result is True

    @pytest.mark.asyncio
    async def test_sls_success(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://m")

        mock_response = MagicMock()
        mock_response.status_ok.return_value = True

        mock_client = MagicMock()
        mock_client.parse_logout_request_response.return_value = mock_response

        with (
            patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True),
            patch.object(
                handler, "_get_saml_client", new_callable=AsyncMock, return_value=mock_client
            ),
        ):
            result = await handler.process_sls_response("resp", "okta")
            assert result is True

    @pytest.mark.asyncio
    async def test_sls_error_returns_false(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://m")

        mock_client = MagicMock()
        mock_client.parse_logout_request_response.side_effect = RuntimeError("fail")

        with (
            patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True),
            patch.object(
                handler, "_get_saml_client", new_callable=AsyncMock, return_value=mock_client
            ),
        ):
            result = await handler.process_sls_response("resp", "okta")
            assert result is False


class TestSAMLHandlerGenerateMetadata:
    """Cover generate_metadata lines 904-929."""

    @pytest.mark.asyncio
    async def test_generate_metadata_no_pysaml2(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        with patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", False):
            metadata = await handler.generate_metadata()
            assert "EntityDescriptor" in metadata
            assert "urn:acgs2:saml:sp" in metadata

    @pytest.mark.asyncio
    async def test_generate_metadata_with_pysaml2_and_idps(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        handler.register_idp(name="okta", metadata_url="http://m")

        mock_client = MagicMock()

        # create_metadata_string may not exist in module scope if pysaml2 not installed
        with (
            patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True),
            patch.object(
                handler, "_get_saml_client", new_callable=AsyncMock, return_value=mock_client
            ),
            patch(
                "src.core.shared.auth.saml_handler.create_metadata_string",
                create=True,
                return_value=b"<metadata/>",
            ),
        ):
            result = await handler.generate_metadata()
            assert result == "<metadata/>"

    @pytest.mark.asyncio
    async def test_generate_metadata_with_pysaml2_no_idps(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()

        mock_config = MagicMock()
        mock_client = MagicMock()

        with (
            patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True),
            patch("src.core.shared.auth.saml_handler.Saml2Config", return_value=mock_config),
            patch("src.core.shared.auth.saml_handler.Saml2Client", return_value=mock_client),
            patch(
                "src.core.shared.auth.saml_handler.create_metadata_string",
                create=True,
                return_value="<str_metadata/>",
            ),
        ):
            result = await handler.generate_metadata()
            assert result == "<str_metadata/>"

    @pytest.mark.asyncio
    async def test_generate_metadata_error(self):
        from src.core.shared.auth.saml_handler import SAMLHandler
        from src.core.shared.auth.saml_types import SAMLError

        handler = SAMLHandler()

        with (
            patch("src.core.shared.auth.saml_handler.HAS_PYSAML2", True),
            patch(
                "src.core.shared.auth.saml_handler.Saml2Config",
                side_effect=RuntimeError("config fail"),
            ),
            pytest.raises(SAMLError, match="Failed to generate"),
        ):
            await handler.generate_metadata()


class TestSAMLHandlerClose:
    """Cover close() cleanup."""

    @pytest.mark.asyncio
    async def test_close_cleans_up(self):
        from src.core.shared.auth.saml_handler import SAMLHandler

        handler = SAMLHandler()
        mock_client = AsyncMock()
        handler._http_client = mock_client

        # Set temp files
        temp_cert = MagicMock()
        temp_cert.name = "/tmp/c.crt"
        handler._temp_cert_file = temp_cert

        with patch("pathlib.Path.unlink"):
            await handler.close()
            mock_client.aclose.assert_awaited_once()
            assert handler._http_client is None


# ---------------------------------------------------------------------------
# provisioning.py tests
# ---------------------------------------------------------------------------


class TestJITProvisionerInMemory:
    """Cover _provision_in_memory and get_or_create_user without session."""

    @pytest.mark.asyncio
    async def test_in_memory_provision(self):
        from src.core.shared.auth.provisioning import JITProvisioner

        p = JITProvisioner(default_roles=["viewer"])
        result = await p.get_or_create_user(
            email="USER@Example.com",
            name="Test User",
            sso_provider="saml",
            idp_user_id="idp-123",
            provider_id="prov-456",
            roles=["admin"],
            name_id="user@example.com",
            session_index="_sess",
        )
        assert result.created is True
        assert result.user["email"] == "user@example.com"
        assert result.user["sso_provider"] == "saml"
        assert "admin" in result.user["roles"]

    @pytest.mark.asyncio
    async def test_in_memory_default_roles(self):
        from src.core.shared.auth.provisioning import JITProvisioner

        p = JITProvisioner(default_roles=["viewer"])
        result = await p.get_or_create_user(email="a@b.com")
        assert "viewer" in result.user["roles"]

    @pytest.mark.asyncio
    async def test_domain_not_allowed(self):
        from src.core.shared.auth.provisioning import DomainNotAllowedError, JITProvisioner

        p = JITProvisioner(allowed_domains=["allowed.com"])
        with pytest.raises(DomainNotAllowedError, match="not allowed"):
            await p.get_or_create_user(email="user@blocked.com")


def _setup_provisioning_user_module():
    """Mock the src.core.shared.models.user module for provisioning tests."""
    mock_user_module = MagicMock()

    class MockSSOProviderType:
        SAML = MagicMock()
        SAML.value = "saml"
        OIDC = MagicMock()
        OIDC.value = "oidc"

    mock_user_module.SSOProviderType = MockSSOProviderType
    mock_user_module.User = MagicMock()
    return mock_user_module


def _provisioning_orm_patches(mock_user_module):
    """Return context managers for provisioning ORM tests.

    Must be used with `with` statement. Patches:
    - src.core.shared.models.user in sys.modules
    - sqlalchemy.select
    - sqlalchemy.orm.joinedload
    """
    mock_select = MagicMock()
    mock_select.return_value.options.return_value.where.return_value = "stmt"

    return (
        patch.dict(sys.modules, {"src.core.shared.models.user": mock_user_module}),
        patch("sqlalchemy.select", mock_select),
        patch("sqlalchemy.orm.joinedload", MagicMock()),
    )


class TestJITProvisionerORM:
    """Cover _provision_with_orm lines 330-456."""

    @pytest.mark.asyncio
    async def test_provision_new_user_saml(self):
        from src.core.shared.auth.provisioning import JITProvisioner

        mock_user_module = _setup_provisioning_user_module()
        mock_user_instance = MagicMock()
        mock_user_instance.id = "u-1"
        mock_user_instance.email = "test@example.com"
        mock_user_instance.name = "Test"
        mock_user_instance.sso_enabled = True
        mock_user_instance.sso_provider = mock_user_module.SSOProviderType.SAML
        mock_user_instance.sso_idp_user_id = "idp-1"
        mock_user_instance.sso_provider_id = "p-1"
        mock_user_instance.sso_name_id = "nid"
        mock_user_instance.sso_session_index = "si"
        mock_user_instance.role_list = ["admin"]
        mock_user_instance.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        mock_user_instance.last_login = datetime.now(UTC)
        mock_user_module.User.return_value = mock_user_instance

        mock_result = MagicMock()
        mock_result.unique.return_value.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session.add = MagicMock()

        p = JITProvisioner(default_roles=["viewer"])
        p1, p2, p3 = _provisioning_orm_patches(mock_user_module)

        with p1, p2, p3:
            result = await p._provision_with_orm(
                session=mock_session,
                email="test@example.com",
                name="Test",
                sso_provider="saml",
                idp_user_id="idp-1",
                provider_id="p-1",
                roles=["admin"],
                name_id="nid",
                session_index="si",
            )
            assert result.created is True
            assert result.user["email"] == "test@example.com"
            mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_provision_existing_user_oidc(self):
        from src.core.shared.auth.provisioning import JITProvisioner

        mock_user_module = _setup_provisioning_user_module()

        existing_user = MagicMock()
        existing_user.id = "u-2"
        existing_user.email = "existing@example.com"
        existing_user.name = "Old Name"
        existing_user.sso_enabled = True
        existing_user.sso_provider = mock_user_module.SSOProviderType.OIDC
        existing_user.sso_idp_user_id = "old-id"
        existing_user.sso_provider_id = "p-2"
        existing_user.sso_name_id = None
        existing_user.sso_session_index = None
        existing_user.role_list = ["viewer"]
        existing_user.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        existing_user.last_login = datetime(2024, 6, 1, tzinfo=UTC)

        mock_result = MagicMock()
        mock_result.unique.return_value.scalar_one_or_none.return_value = existing_user

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        p = JITProvisioner()
        p1, p2, p3 = _provisioning_orm_patches(mock_user_module)

        with p1, p2, p3:
            result = await p._provision_with_orm(
                session=mock_session,
                email="existing@example.com",
                name="New Name",
                sso_provider="oidc",
                idp_user_id="new-id",
                provider_id="p-2",
                roles=["admin", "developer"],
                name_id=None,
                session_index=None,
            )
            assert result.created is False
            assert result.roles_updated is True
            existing_user.update_sso_info.assert_called_once()
            existing_user.set_roles.assert_called_once()

    @pytest.mark.asyncio
    async def test_provision_disabled_raises(self):
        from src.core.shared.auth.provisioning import JITProvisioner, ProvisioningDisabledError

        mock_user_module = _setup_provisioning_user_module()

        mock_result = MagicMock()
        mock_result.unique.return_value.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        p = JITProvisioner(auto_provision_enabled=False)
        p1, p2, p3 = _provisioning_orm_patches(mock_user_module)

        with p1, p2, p3, pytest.raises(ProvisioningDisabledError):
            await p._provision_with_orm(
                session=mock_session,
                email="test@example.com",
                name=None,
                sso_provider="oidc",
                idp_user_id=None,
                provider_id=None,
                roles=None,
                name_id=None,
                session_index=None,
            )

    @pytest.mark.asyncio
    async def test_provision_existing_no_role_change(self):
        from src.core.shared.auth.provisioning import JITProvisioner

        mock_user_module = _setup_provisioning_user_module()

        existing_user = MagicMock()
        existing_user.id = "u-3"
        existing_user.email = "same@example.com"
        existing_user.name = "Same"
        existing_user.sso_enabled = True
        existing_user.sso_provider = mock_user_module.SSOProviderType.OIDC
        existing_user.sso_idp_user_id = "id"
        existing_user.sso_provider_id = "p"
        existing_user.sso_name_id = None
        existing_user.sso_session_index = None
        existing_user.role_list = ["viewer"]
        existing_user.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        existing_user.last_login = datetime.now(UTC)

        mock_result = MagicMock()
        mock_result.unique.return_value.scalar_one_or_none.return_value = existing_user

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        p = JITProvisioner()
        p1, p2, p3 = _provisioning_orm_patches(mock_user_module)

        with p1, p2, p3:
            result = await p._provision_with_orm(
                session=mock_session,
                email="same@example.com",
                name="Same",  # Same name, no change
                sso_provider="oidc",
                idp_user_id=None,
                provider_id=None,
                roles=None,  # No roles from IdP
                name_id=None,
                session_index=None,
            )
            assert result.created is False
            assert result.roles_updated is False


class TestJITProvisionerUpdateRoles:
    """Cover update_user_roles lines 551-582."""

    @pytest.mark.asyncio
    async def test_update_user_roles_not_found(self):
        from src.core.shared.auth.provisioning import JITProvisioner, ProvisioningError

        mock_user_module = _setup_provisioning_user_module()

        mock_result = MagicMock()
        mock_result.unique.return_value.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        p = JITProvisioner()
        p1, p2, p3 = _provisioning_orm_patches(mock_user_module)

        with p1, p2, p3, pytest.raises(ProvisioningError, match="not found"):
            await p.update_user_roles("u-1", ["admin"], mock_session)

    @pytest.mark.asyncio
    async def test_update_user_roles_changed(self):
        from src.core.shared.auth.provisioning import JITProvisioner

        mock_user_module = _setup_provisioning_user_module()

        existing_user = MagicMock()
        existing_user.role_list = ["viewer"]

        mock_result = MagicMock()
        mock_result.unique.return_value.scalar_one_or_none.return_value = existing_user

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        p = JITProvisioner()
        p1, p2, p3 = _provisioning_orm_patches(mock_user_module)

        with p1, p2, p3:
            changed = await p.update_user_roles("u-1", ["admin"], mock_session)
            assert changed is True
            existing_user.set_roles.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_user_roles_no_change(self):
        from src.core.shared.auth.provisioning import JITProvisioner

        mock_user_module = _setup_provisioning_user_module()

        existing_user = MagicMock()
        existing_user.role_list = ["admin"]

        mock_result = MagicMock()
        mock_result.unique.return_value.scalar_one_or_none.return_value = existing_user

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        p = JITProvisioner()
        p1, p2, p3 = _provisioning_orm_patches(mock_user_module)

        with p1, p2, p3:
            # Pass same roles - no change
            changed = await p.update_user_roles("u-1", ["admin"], mock_session)
            assert changed is False


class TestJITProvisionerClearSession:
    """Cover clear_sso_session lines 601-615."""

    @pytest.mark.asyncio
    async def test_clear_session_not_found(self):
        from src.core.shared.auth.provisioning import JITProvisioner, ProvisioningError

        mock_user_module = _setup_provisioning_user_module()

        mock_result = MagicMock()
        mock_result.unique.return_value.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        p = JITProvisioner()
        p1, p2, p3 = _provisioning_orm_patches(mock_user_module)

        with p1, p2, p3, pytest.raises(ProvisioningError, match="not found"):
            await p.clear_sso_session("u-1", mock_session)

    @pytest.mark.asyncio
    async def test_clear_session_success(self):
        from src.core.shared.auth.provisioning import JITProvisioner

        mock_user_module = _setup_provisioning_user_module()

        existing_user = MagicMock()

        mock_result = MagicMock()
        mock_result.unique.return_value.scalar_one_or_none.return_value = existing_user

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        p = JITProvisioner()
        p1, p2, p3 = _provisioning_orm_patches(mock_user_module)

        with p1, p2, p3:
            await p.clear_sso_session("u-1", mock_session)
            existing_user.clear_sso_session.assert_called_once()


class TestProvisionerSingleton:
    """Cover get_provisioner / reset_provisioner."""

    def test_singleton(self):
        from src.core.shared.auth.provisioning import (
            get_provisioner,
            reset_provisioner,
        )

        reset_provisioner()
        p1 = get_provisioner(default_roles=["admin"])
        p2 = get_provisioner()
        assert p1 is p2
        reset_provisioner()


class TestMergeRoles:
    """Cover _merge_roles edge cases."""

    def test_no_new_roles_no_existing_with_defaults(self):
        from src.core.shared.auth.provisioning import JITProvisioner

        p = JITProvisioner(default_roles=["viewer"])
        merged, changed = p._merge_roles([], [], ["viewer"])
        assert merged == ["viewer"]
        assert changed is True

    def test_existing_preserved_when_no_new(self):
        from src.core.shared.auth.provisioning import JITProvisioner

        p = JITProvisioner()
        merged, changed = p._merge_roles(["admin"], [])
        assert merged == ["admin"]
        assert changed is False

    def test_new_roles_override(self):
        from src.core.shared.auth.provisioning import JITProvisioner

        p = JITProvisioner()
        merged, changed = p._merge_roles(["old"], ["new"])
        assert merged == ["new"]
        assert changed is True


# ---------------------------------------------------------------------------
# role_mapper.py tests
# ---------------------------------------------------------------------------


class TestRoleMapperCaseSensitive:
    """Cover case_sensitive path line 194."""

    def test_case_sensitive_match(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper(
            default_mappings={"Admin": "admin"}, case_sensitive=True
        )
        # Exact case match
        assert mapper.map_groups(["Admin"]) == ["admin"]
        # Wrong case does not match
        assert mapper.map_groups(["admin"]) == []

    def test_case_sensitive_normalize(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper(case_sensitive=True)
        assert mapper._normalize_group("  Test  ") == "Test"

    def test_case_insensitive_normalize(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper(case_sensitive=False)
        assert mapper._normalize_group("  TEST  ") == "test"


class TestRoleMapperAsyncMapping:
    """Cover map_groups_async lines 313-318, 333-344, 351, 355."""

    @pytest.mark.asyncio
    async def test_empty_groups(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper()
        result = await mapper.map_groups_async([])
        assert result.roles == []
        assert result.source == "none"

    @pytest.mark.asyncio
    async def test_default_mapping_only(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper()
        result = await mapper.map_groups_async(["admins", "unknown_group"])
        assert "admin" in result.roles
        assert "unknown_group" in result.unmapped_groups
        assert result.source == "default"

    @pytest.mark.asyncio
    async def test_db_mapping_success(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper()
        mock_session = AsyncMock()

        with patch.object(
            mapper,
            "_fetch_provider_mappings",
            new_callable=AsyncMock,
            return_value={"engineering": ("developer", 10)},
        ):
            result = await mapper.map_groups_async(
                ["engineering", "unknown"],
                provider_id="p-1",
                session=mock_session,
            )
            assert "developer" in result.roles
            assert result.source == "database"

    @pytest.mark.asyncio
    async def test_db_mapping_fallback_on_error(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper()
        mock_session = AsyncMock()

        with patch.object(
            mapper,
            "_fetch_provider_mappings",
            new_callable=AsyncMock,
            side_effect=RuntimeError("db error"),
        ):
            result = await mapper.map_groups_async(
                ["admins"],
                provider_id="p-1",
                session=mock_session,
            )
            assert "admin" in result.roles
            assert result.source == "default"

    @pytest.mark.asyncio
    async def test_db_mapping_with_fallback_role(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper(fallback_role="viewer")
        mock_session = AsyncMock()

        with patch.object(
            mapper,
            "_fetch_provider_mappings",
            new_callable=AsyncMock,
            return_value={"eng": ("developer", 10)},
        ):
            result = await mapper.map_groups_async(
                ["unknown"],
                provider_id="p-1",
                session=mock_session,
            )
            assert "viewer" in result.roles

    @pytest.mark.asyncio
    async def test_db_mapping_case_sensitive(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper(case_sensitive=True)
        mock_session = AsyncMock()

        with patch.object(
            mapper,
            "_fetch_provider_mappings",
            new_callable=AsyncMock,
            return_value={"Engineering": ("developer", 10)},
        ):
            result = await mapper.map_groups_async(
                ["Engineering"],
                provider_id="p-1",
                session=mock_session,
            )
            assert "developer" in result.roles


def _setup_role_mapper_db_mocks():
    """Set up sys.modules mocks for role_mapper DB tests.

    Returns (mock_module, mock_select) context managers are NOT used --
    caller must use patch.dict on sys.modules.
    """
    mock_module = MagicMock()
    mock_module.SSORoleMapping = MagicMock()
    mock_module.SSORoleMapping.provider_id = MagicMock()
    mock_module.SSORoleMapping.priority = MagicMock()
    mock_module.SSORoleMapping.idp_group = MagicMock()
    mock_module.SSORoleMapping.id = MagicMock()
    mock_module.SSORoleMapping.create_mapping = MagicMock()
    return mock_module


class TestRoleMapperFetchProviderMappings:
    """Cover _fetch_provider_mappings lines 392-405."""

    @pytest.mark.asyncio
    async def test_fetch_provider_mappings(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper()

        mock_mapping = MagicMock()
        mock_mapping.idp_group = "eng"
        mock_mapping.acgs_role = "developer"
        mock_mapping.priority = 5

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_mapping]

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_module = _setup_role_mapper_db_mocks()
        mock_select = MagicMock()
        mock_select.return_value.where.return_value.order_by.return_value = "stmt"

        with (
            patch.dict(sys.modules, {"src.core.shared.models.sso_role_mapping": mock_module}),
            patch("sqlalchemy.select", mock_select),
        ):
            result = await mapper._fetch_provider_mappings("p-1", mock_session)
            assert result == {"eng": ("developer", 5)}


class TestRoleMapperCreateMapping:
    """Cover create_mapping lines 478-502."""

    @pytest.mark.asyncio
    async def test_create_mapping(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper()
        mock_session = MagicMock()

        mock_mapping = MagicMock()
        mock_mapping.id = "m-1"

        mock_module = _setup_role_mapper_db_mocks()
        mock_module.SSORoleMapping.create_mapping.return_value = mock_mapping

        with patch.dict(sys.modules, {"src.core.shared.models.sso_role_mapping": mock_module}):
            result = await mapper.create_mapping(
                provider_id="p-1",
                idp_group="eng",
                acgs_role="developer",
                session=mock_session,
                priority=5,
                description="Test",
            )
            assert result is mock_mapping
            mock_session.add.assert_called_once_with(mock_mapping)


class TestRoleMapperDeleteMapping:
    """Cover delete_mapping lines 518-539."""

    @pytest.mark.asyncio
    async def test_delete_mapping_found(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper()
        mock_mapping = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_mapping

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_module = _setup_role_mapper_db_mocks()
        mock_select = MagicMock()
        mock_select.return_value.where.return_value = "stmt"

        with (
            patch.dict(sys.modules, {"src.core.shared.models.sso_role_mapping": mock_module}),
            patch("sqlalchemy.select", mock_select),
        ):
            result = await mapper.delete_mapping("m-1", mock_session)
            assert result is True
            mock_session.delete.assert_awaited_once_with(mock_mapping)

    @pytest.mark.asyncio
    async def test_delete_mapping_not_found(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_module = _setup_role_mapper_db_mocks()
        mock_select = MagicMock()
        mock_select.return_value.where.return_value = "stmt"

        with (
            patch.dict(sys.modules, {"src.core.shared.models.sso_role_mapping": mock_module}),
            patch("sqlalchemy.select", mock_select),
        ):
            result = await mapper.delete_mapping("m-999", mock_session)
            assert result is False


class TestRoleMapperGetProviderMappings:
    """Cover get_provider_mappings lines 555-568."""

    @pytest.mark.asyncio
    async def test_get_provider_mappings(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper()

        mock_mapping = MagicMock()
        mock_mapping.id = "m-1"
        mock_mapping.provider_id = "p-1"
        mock_mapping.idp_group = "eng"
        mock_mapping.acgs_role = "developer"
        mock_mapping.priority = 5
        mock_mapping.description = "Test"
        mock_mapping.created_at = datetime(2024, 1, 1, tzinfo=UTC)
        mock_mapping.updated_at = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_mapping]

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        mock_module = _setup_role_mapper_db_mocks()
        mock_select = MagicMock()
        mock_select.return_value.where.return_value.order_by.return_value = "stmt"

        with (
            patch.dict(sys.modules, {"src.core.shared.models.sso_role_mapping": mock_module}),
            patch("sqlalchemy.select", mock_select),
        ):
            result = await mapper.get_provider_mappings("p-1", mock_session)
            assert len(result) == 1
            assert result[0]["idp_group"] == "eng"
            assert result[0]["acgs_role"] == "developer"
            assert result[0]["created_at"] == "2024-01-01T00:00:00+00:00"
            assert result[0]["updated_at"] is None


class TestRoleMapperAddRemove:
    """Cover add/remove default mapping methods."""

    def test_add_default_mapping(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper(default_mappings={})
        mapper.add_default_mapping("Custom Group", "custom_role")
        assert mapper.default_mappings["custom group"] == "custom_role"

    def test_add_default_mapping_case_sensitive(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper(default_mappings={}, case_sensitive=True)
        mapper.add_default_mapping("Custom", "custom_role")
        assert mapper.default_mappings["Custom"] == "custom_role"

    def test_remove_default_mapping(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper(default_mappings={"test": "role"})
        assert mapper.remove_default_mapping("test") is True
        assert mapper.remove_default_mapping("nonexistent") is False

    def test_get_default_mappings_returns_copy(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper(default_mappings={"a": "b"})
        mappings = mapper.get_default_mappings()
        assert mappings == {"a": "b"}
        mappings["c"] = "d"
        assert "c" not in mapper.default_mappings


class TestRoleMapperSingleton:
    """Cover get_role_mapper / reset_role_mapper."""

    def test_singleton(self):
        from src.core.shared.auth.role_mapper import get_role_mapper, reset_role_mapper

        reset_role_mapper()
        m1 = get_role_mapper(fallback_role="viewer")
        m2 = get_role_mapper()
        assert m1 is m2
        reset_role_mapper()


class TestRoleMapperFallbackRole:
    """Cover fallback role application in sync map_groups."""

    def test_fallback_applied(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper(
            default_mappings={},
            fallback_role="viewer",
        )
        roles = mapper.map_groups(["unknown_group"])
        assert roles == ["viewer"]

    def test_no_fallback(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper(default_mappings={}, fallback_role=None)
        roles = mapper.map_groups(["unknown"])
        assert roles == []

    def test_empty_groups(self):
        from src.core.shared.auth.role_mapper import RoleMapper

        mapper = RoleMapper()
        roles = mapper.map_groups([])
        assert roles == []
