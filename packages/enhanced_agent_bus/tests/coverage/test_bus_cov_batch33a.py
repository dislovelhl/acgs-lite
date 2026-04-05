"""
Coverage tests for enhanced_agent_bus modules:
- impact_scorer_infra/algorithms/minicpm_semantic.py
- enterprise_sso/ldap_integration.py

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from queue import Full
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# ldap_integration imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.enterprise_sso.ldap_integration import (
    CircuitBreakerState,
    LDAPAuthenticationResult,
    LDAPBindError,
    LDAPCircuitBreaker,
    LDAPCircuitOpenError,
    LDAPConfig,
    LDAPConnection,
    LDAPConnectionError,
    LDAPConnectionPool,
    LDAPIntegration,
    LDAPIntegrationError,
    LDAPSearchError,
    build_search_filter,
    decode_ldap_value,
    escape_dn_chars,
    escape_filter_chars,
    extract_cn_from_dn,
    parse_dn,
    parse_ldap_entry,
)

# ---------------------------------------------------------------------------
# minicpm_semantic imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.impact_scorer_infra.algorithms.minicpm_semantic import (
    GovernanceDomain,
    MiniCPMScorerConfig,
    MiniCPMSemanticScorer,
    cosine_similarity,
    create_minicpm_scorer,
)
from enhanced_agent_bus.impact_scorer_infra.models import ScoringMethod

# ============================================================================
# MiniCPM Semantic Scorer — uncovered lines
# ============================================================================


class TestMiniCPMInitializeProvider:
    """Cover _initialize_provider error/fallback paths."""

    def test_initialize_provider_already_attempted(self):
        scorer = MiniCPMSemanticScorer()
        scorer._initialization_attempted = True
        scorer._provider_available = False
        result = scorer._initialize_provider()
        assert result is False

    def test_initialize_provider_already_attempted_true(self):
        scorer = MiniCPMSemanticScorer()
        scorer._initialization_attempted = True
        scorer._provider_available = True
        result = scorer._initialize_provider()
        assert result is True

    def test_initialize_provider_already_has_provider(self):
        scorer = MiniCPMSemanticScorer()
        scorer._provider = MagicMock()
        scorer._provider_available = True
        result = scorer._initialize_provider()
        assert result is True

    def test_initialize_provider_outer_import_error(self):
        """Cover outer ImportError in _initialize_provider (line 290-293)."""
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "enhanced_agent_bus.embeddings.provider":
                raise ImportError("no embeddings module")
            return real_import(name, *args, **kwargs)

        scorer = MiniCPMSemanticScorer()
        scorer._initialization_attempted = False
        scorer._provider = None
        with patch("builtins.__import__", side_effect=fake_import):
            result = scorer._initialize_provider()
            assert result is False
            assert scorer._provider_available is False

    def test_initialize_provider_embed_import_error(self):
        """Cover inner ImportError when provider.embed fails (line 279-283)."""
        import builtins

        real_import = builtins.__import__

        mock_provider = MagicMock()
        mock_provider.embed.side_effect = ImportError("transformers not installed")

        mock_module = MagicMock()
        mock_module.create_embedding_provider.return_value = mock_provider

        def fake_import(name, *args, **kwargs):
            if name == "enhanced_agent_bus.embeddings.provider":
                return mock_module
            return real_import(name, *args, **kwargs)

        scorer = MiniCPMSemanticScorer()
        scorer._initialization_attempted = False
        scorer._provider = None
        with patch("builtins.__import__", side_effect=fake_import):
            result = scorer._initialize_provider()
            assert result is False
            assert scorer._provider is None

    def test_initialize_provider_embed_runtime_error(self):
        """Cover inner RuntimeError when provider.embed fails (line 284-288)."""
        import builtins

        real_import = builtins.__import__

        mock_provider = MagicMock()
        mock_provider.embed.side_effect = RuntimeError("model load failed")

        mock_module = MagicMock()
        mock_module.create_embedding_provider.return_value = mock_provider

        def fake_import(name, *args, **kwargs):
            if name == "enhanced_agent_bus.embeddings.provider":
                return mock_module
            return real_import(name, *args, **kwargs)

        scorer = MiniCPMSemanticScorer()
        scorer._initialization_attempted = False
        scorer._provider = None
        with patch("builtins.__import__", side_effect=fake_import):
            result = scorer._initialize_provider()
            assert result is False
            assert scorer._provider is None

    def test_initialize_provider_create_raises_runtime(self):
        """Cover outer RuntimeError from create_embedding_provider (line 294-297)."""
        import builtins

        real_import = builtins.__import__

        mock_module = MagicMock()
        mock_module.create_embedding_provider.side_effect = RuntimeError("config error")

        def fake_import(name, *args, **kwargs):
            if name == "enhanced_agent_bus.embeddings.provider":
                return mock_module
            return real_import(name, *args, **kwargs)

        scorer = MiniCPMSemanticScorer()
        scorer._initialization_attempted = False
        scorer._provider = None
        with patch("builtins.__import__", side_effect=fake_import):
            result = scorer._initialize_provider()
            assert result is False


class TestMiniCPMComputeDomainEmbeddings:
    """Cover _compute_domain_embeddings paths."""

    def test_domain_embeddings_already_computed(self):
        scorer = MiniCPMSemanticScorer()
        scorer._domain_embeddings = {GovernanceDomain.SAFETY: [0.1]}
        scorer._compute_domain_embeddings()
        # Should return early, not overwrite
        assert scorer._domain_embeddings == {GovernanceDomain.SAFETY: [0.1]}

    def test_domain_embeddings_provider_unavailable(self):
        scorer = MiniCPMSemanticScorer()
        scorer._initialization_attempted = True
        scorer._provider_available = False
        scorer._compute_domain_embeddings()
        assert scorer._domain_embeddings is None

    def test_domain_embeddings_exception_path(self):
        """Cover exception in _compute_domain_embeddings (line 322-325)."""
        scorer = MiniCPMSemanticScorer()
        scorer._provider_available = True
        scorer._initialization_attempted = True
        mock_provider = MagicMock()
        mock_provider.embed_batch.side_effect = RuntimeError("batch fail")
        scorer._provider = mock_provider
        scorer._compute_domain_embeddings()
        assert scorer._domain_embeddings is None
        assert scorer._provider_available is False


class TestMiniCPMGetEmbedding:
    """Cover _get_embedding paths."""

    def test_get_embedding_provider_unavailable(self):
        scorer = MiniCPMSemanticScorer()
        scorer._provider_available = False
        result = scorer._get_embedding("test")
        assert result is None

    def test_get_embedding_cache_hit(self):
        scorer = MiniCPMSemanticScorer()
        scorer._provider_available = True
        cache_key = scorer._get_cache_key("test")
        scorer._embedding_cache[cache_key] = [0.5, 0.6]
        result = scorer._get_embedding("test")
        assert result == [0.5, 0.6]

    def test_get_embedding_error_path(self):
        """Cover exception in _get_embedding (line 340-342)."""
        scorer = MiniCPMSemanticScorer()
        scorer._provider_available = True
        mock_provider = MagicMock()
        mock_provider.embed.side_effect = RuntimeError("embed fail")
        scorer._provider = mock_provider
        result = scorer._get_embedding("test")
        assert result is None


class TestMiniCPMSemanticSimilarity:
    """Cover _calculate_semantic_similarity."""

    def test_semantic_similarity_no_domain_embeddings(self):
        scorer = MiniCPMSemanticScorer()
        scorer._domain_embeddings = None
        result = scorer._calculate_semantic_similarity([0.1], GovernanceDomain.SAFETY)
        assert result == 0.0

    def test_semantic_similarity_domain_missing(self):
        scorer = MiniCPMSemanticScorer()
        scorer._domain_embeddings = {}
        result = scorer._calculate_semantic_similarity([0.1], GovernanceDomain.SAFETY)
        assert result == 0.0

    def test_semantic_similarity_normal(self):
        scorer = MiniCPMSemanticScorer()
        scorer._domain_embeddings = {GovernanceDomain.SAFETY: [1.0, 0.0]}
        result = scorer._calculate_semantic_similarity([1.0, 0.0], GovernanceDomain.SAFETY)
        # cosine similarity = 1.0, normalized = (1+1)/2 = 1.0
        assert abs(result - 1.0) < 1e-6

    def test_semantic_similarity_orthogonal(self):
        scorer = MiniCPMSemanticScorer()
        scorer._domain_embeddings = {GovernanceDomain.SAFETY: [1.0, 0.0]}
        result = scorer._calculate_semantic_similarity([0.0, 1.0], GovernanceDomain.SAFETY)
        # cosine similarity = 0.0, normalized = (0+1)/2 = 0.5
        assert abs(result - 0.5) < 1e-6


class TestMiniCPMExtractContent:
    """Cover extraction edge cases."""

    def test_extract_message_string(self):
        """Cover non-dict message path (line 408)."""
        scorer = MiniCPMSemanticScorer()
        context = {"message": "plain string message"}
        text = scorer._extract_text_content(context)
        assert "plain string message" in text

    def test_extract_tools_non_dict(self):
        """Cover non-dict tool in tools list (line 433)."""
        scorer = MiniCPMSemanticScorer()
        context = {"tools": ["tool_a", "tool_b"]}
        text = scorer._extract_text_content(context)
        assert "tool_a" in text
        assert "tool_b" in text

    def test_extract_tools_empty_list(self):
        scorer = MiniCPMSemanticScorer()
        context = {"tools": []}
        text = scorer._extract_text_content(context)
        assert text == ""

    def test_extract_tools_mixed(self):
        scorer = MiniCPMSemanticScorer()
        context = {"tools": [{"name": "dict_tool"}, "string_tool"]}
        text = scorer._extract_text_content(context)
        assert "dict_tool" in text
        assert "string_tool" in text

    def test_extract_message_dict_no_content(self):
        scorer = MiniCPMSemanticScorer()
        context = {"message": {"other_key": "value"}}
        text = scorer._extract_text_content(context)
        assert text == ""

    def test_extract_message_payload_not_dict(self):
        scorer = MiniCPMSemanticScorer()
        context = {"message": {"payload": "not_a_dict"}}
        text = scorer._extract_text_content(context)
        assert text == ""


class TestMiniCPMScoreFallbackDisabled:
    """Cover fallback_to_keywords=False path (line 488)."""

    def test_score_no_fallback(self):
        config = MiniCPMScorerConfig(fallback_to_keywords=False)
        scorer = MiniCPMSemanticScorer(config)
        scorer._provider_available = False
        scorer._initialization_attempted = True
        result = scorer.score({"content": "breach danger emergency"})
        # Without fallback and without semantic, all scores should be 0
        assert result.aggregate_score == 0.0
        assert result.metadata["semantic_enabled"] is False


class TestMiniCPMScoreWithSemanticEnabled:
    """Cover score() with use_semantic=True paths."""

    def test_score_semantic_path(self):
        scorer = MiniCPMSemanticScorer()
        scorer._provider_available = True
        scorer._initialization_attempted = True
        # Set up domain embeddings manually
        scorer._domain_embeddings = {domain: [0.1] * 4 for domain in GovernanceDomain}
        mock_provider = MagicMock()
        mock_provider.embed.return_value = [0.1] * 4
        scorer._provider = mock_provider

        result = scorer.score({"content": "breach emergency"})
        assert result.confidence == 0.95
        assert result.metadata["semantic_enabled"] is True

    def test_score_high_impact_threshold(self):
        config = MiniCPMScorerConfig(high_impact_threshold=0.01)
        scorer = MiniCPMSemanticScorer(config)
        scorer._provider_available = True
        scorer._initialization_attempted = True
        scorer._domain_embeddings = {domain: [1.0, 0.0] for domain in GovernanceDomain}
        mock_provider = MagicMock()
        mock_provider.embed.return_value = [1.0, 0.0]
        scorer._provider = mock_provider

        result = scorer.score({"content": "breach danger"})
        assert result.metadata["is_high_impact"] is True


class TestMiniCPMBatchWithProvider:
    """Cover score_batch with provider available (lines 562-574)."""

    def test_batch_with_provider(self):
        scorer = MiniCPMSemanticScorer()
        scorer._provider_available = True
        scorer._initialization_attempted = True
        scorer._domain_embeddings = {domain: [0.1] * 4 for domain in GovernanceDomain}
        mock_provider = MagicMock()
        mock_provider.embed.return_value = [0.1] * 4
        mock_provider.embed_batch.return_value = [[0.1] * 4, [0.2] * 4]
        scorer._provider = mock_provider

        contexts = [
            {"content": "first"},
            {"content": "second"},
        ]
        results = scorer.score_batch(contexts)
        assert len(results) == 2
        mock_provider.embed_batch.assert_called_once()

    def test_batch_with_provider_embed_error(self):
        """Cover batch embed failure path (line 573-574)."""
        scorer = MiniCPMSemanticScorer()
        scorer._provider_available = True
        scorer._initialization_attempted = True
        scorer._domain_embeddings = {domain: [0.1] * 4 for domain in GovernanceDomain}
        mock_provider = MagicMock()
        mock_provider.embed.return_value = [0.1] * 4
        mock_provider.embed_batch.side_effect = RuntimeError("batch fail")
        scorer._provider = mock_provider

        contexts = [{"content": "test"}]
        results = scorer.score_batch(contexts)
        assert len(results) == 1

    def test_batch_with_empty_texts(self):
        """Cover batch where some texts are empty."""
        scorer = MiniCPMSemanticScorer()
        scorer._provider_available = True
        scorer._initialization_attempted = True
        scorer._domain_embeddings = {domain: [0.1] * 4 for domain in GovernanceDomain}
        mock_provider = MagicMock()
        mock_provider.embed.return_value = [0.1] * 4
        mock_provider.embed_batch.return_value = [[0.1] * 4]
        scorer._provider = mock_provider

        contexts = [{}, {"content": "valid"}]
        results = scorer.score_batch(contexts)
        assert len(results) == 2


class TestMiniCPMUnloadWithProvider:
    """Cover unload with provider that has unload method (line 582)."""

    def test_unload_with_unload_method(self):
        scorer = MiniCPMSemanticScorer()
        mock_provider = MagicMock()
        mock_provider.unload = MagicMock()
        scorer._provider = mock_provider
        scorer._provider_available = True
        scorer._domain_embeddings = {GovernanceDomain.SAFETY: [0.1]}
        scorer._embedding_cache["k"] = [0.1]

        scorer.unload()

        mock_provider.unload.assert_called_once()
        assert scorer._provider is None
        assert scorer._provider_available is False
        assert scorer._domain_embeddings is None
        assert len(scorer._embedding_cache) == 0

    def test_unload_without_unload_method(self):
        scorer = MiniCPMSemanticScorer()
        mock_provider = MagicMock(spec=[])  # no unload attr
        scorer._provider = mock_provider
        scorer.unload()
        assert scorer._provider is None


class TestMiniCPMCosineEdgeCases:
    """Additional cosine similarity edge cases."""

    def test_both_zero_vectors(self):
        assert cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0

    def test_single_element(self):
        assert abs(cosine_similarity([3.0], [3.0]) - 1.0) < 1e-6

    def test_negative_similarity(self):
        result = cosine_similarity([1.0, 0.0], [-1.0, 0.0])
        assert result < 0


# ============================================================================
# LDAP Integration — uncovered lines
# ============================================================================


def _make_ldap_config(**overrides):
    """Helper to create a test LDAPConfig."""
    defaults = {
        "server_uri": "ldap://test.example.com",
        "base_dn": "dc=example,dc=com",
        "bind_dn": "cn=admin,dc=example,dc=com",
        "bind_password": "secret",
        "circuit_breaker_enabled": False,
    }
    defaults.update(overrides)
    return LDAPConfig(**defaults)


class TestLDAPEscapeDnChars:
    """Cover escape_dn_chars (lines 916-933)."""

    def test_escape_comma(self):
        assert "\\," in escape_dn_chars("a,b")

    def test_escape_plus(self):
        assert "\\+" in escape_dn_chars("a+b")

    def test_escape_quote(self):
        assert '\\"' in escape_dn_chars('a"b')

    def test_escape_backslash(self):
        assert "\\\\" in escape_dn_chars("a\\b")

    def test_escape_angle_brackets(self):
        result = escape_dn_chars("<a>")
        assert "\\<" in result
        assert "\\>" in result

    def test_escape_semicolon(self):
        assert "\\;" in escape_dn_chars("a;b")

    def test_escape_equals(self):
        assert "\\=" in escape_dn_chars("a=b")

    def test_no_escape_needed(self):
        assert escape_dn_chars("simple") == "simple"


class TestLDAPEscapeFilterChars:
    """Cover escape_filter_chars."""

    def test_escape_backslash_first(self):
        result = escape_filter_chars("a\\b")
        assert "\\5c" in result

    def test_escape_star(self):
        assert "\\2a" in escape_filter_chars("a*b")

    def test_escape_parens(self):
        result = escape_filter_chars("(a)")
        assert "\\28" in result
        assert "\\29" in result

    def test_escape_null(self):
        assert "\\00" in escape_filter_chars("a\x00b")


class TestBuildSearchFilter:
    """Cover build_search_filter."""

    def test_basic_substitution(self):
        result = build_search_filter("(uid={username})", username="john")
        assert result == "(uid=john)"

    def test_escapes_values(self):
        result = build_search_filter("(uid={username})", username="john*doe")
        assert "\\2a" in result

    def test_multiple_params(self):
        result = build_search_filter(
            "(&(uid={username})(member={user_dn}))",
            username="john",
            user_dn="cn=john,dc=example,dc=com",
        )
        assert "john" in result
        assert "cn=john" in result


class TestParseDn:
    """Cover parse_dn and extract_cn_from_dn."""

    def test_parse_simple_dn(self):
        result = parse_dn("cn=admin,dc=example,dc=com")
        assert result["cn"] == "admin"
        # Last dc wins
        assert "dc" in result

    def test_parse_empty_dn(self):
        result = parse_dn("")
        assert result == {}

    def test_extract_cn(self):
        assert extract_cn_from_dn("cn=Users,dc=example,dc=com") == "Users"

    def test_extract_cn_missing(self):
        assert extract_cn_from_dn("dc=example,dc=com") is None


class TestParseLdapEntry:
    """Cover parse_ldap_entry and decode_ldap_value."""

    def test_parse_entry_with_bytes(self):
        entry = ("cn=admin,dc=example,dc=com", {"cn": [b"admin"], "mail": [b"a@b.com"]})
        result = parse_ldap_entry(entry)
        assert result["dn"] == "cn=admin,dc=example,dc=com"
        assert result["cn"] == "admin"
        assert result["mail"] == "a@b.com"

    def test_parse_entry_multiple_values(self):
        entry = ("cn=admin", {"memberOf": [b"cn=g1", b"cn=g2"]})
        result = parse_ldap_entry(entry)
        assert isinstance(result["memberOf"], list)
        assert len(result["memberOf"]) == 2

    def test_decode_non_bytes(self):
        result = decode_ldap_value([42])
        assert result == "42"

    def test_decode_single(self):
        result = decode_ldap_value([b"hello"])
        assert result == "hello"

    def test_decode_multiple(self):
        result = decode_ldap_value([b"a", b"b"])
        assert result == ["a", "b"]

    def test_decode_utf8_replacement(self):
        result = decode_ldap_value([b"\xff\xfe"])
        assert isinstance(result, str)


class TestLDAPCircuitBreakerAdvanced:
    """Cover circuit breaker transitions."""

    def test_half_open_transition(self):
        cb = LDAPCircuitBreaker(failure_threshold=2, recovery_timeout=0.01)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN.value

        # Wait for recovery
        time.sleep(0.02)
        assert cb.state == CircuitBreakerState.HALF_OPEN.value

    def test_half_open_to_closed_on_success(self):
        cb = LDAPCircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitBreakerState.HALF_OPEN.value
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED.value

    def test_is_available_when_closed(self):
        cb = LDAPCircuitBreaker()
        assert cb.is_available is True

    def test_is_available_when_open(self):
        cb = LDAPCircuitBreaker(failure_threshold=1)
        cb.record_failure()
        assert cb.is_available is False

    def test_consecutive_failures_property(self):
        cb = LDAPCircuitBreaker()
        assert cb.consecutive_failures == 0
        cb.record_failure()
        assert cb.consecutive_failures == 1

    def test_record_success_resets_from_open(self):
        cb = LDAPCircuitBreaker(failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN.value
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED.value
        assert cb.consecutive_failures == 0


class TestLDAPConnectionNoLdapModule:
    """Cover LDAPConnection when LDAP_AVAILABLE is False."""

    def test_raises_when_ldap_unavailable(self):
        config = _make_ldap_config()
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", False):
            with pytest.raises(LDAPIntegrationError, match="python-ldap"):
                LDAPConnection(config)


class TestLDAPConnectionMocked:
    """Cover LDAPConnection methods with mocked ldap module."""

    @pytest.fixture
    def mock_conn(self):
        config = _make_ldap_config()
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.ldap") as mock_ldap:
                mock_inner = MagicMock()
                mock_ldap.initialize.return_value = mock_inner
                mock_ldap.OPT_REFERRALS = 0
                mock_ldap.OPT_PROTOCOL_VERSION = 0
                mock_ldap.VERSION3 = 3
                mock_ldap.OPT_X_TLS_REQUIRE_CERT = 0
                mock_ldap.OPT_X_TLS_DEMAND = 0
                mock_ldap.OPT_X_TLS_CACERTFILE = 0
                conn = LDAPConnection(config)
                yield conn, mock_inner, mock_ldap

    def test_connect_success(self, mock_conn):
        conn, mock_inner, _ = mock_conn
        assert conn.connect() is True
        assert conn.is_connected is True

    def test_bind_not_connected(self):
        config = _make_ldap_config()
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            conn = LDAPConnection(config)
            with pytest.raises(LDAPConnectionError, match="Not connected"):
                conn.bind()

    def test_bind_success(self, mock_conn):
        conn, mock_inner, _ = mock_conn
        conn.connect()
        assert conn.bind() is True

    def test_bind_anonymous(self, mock_conn):
        conn, mock_inner, _ = mock_conn
        conn.config = _make_ldap_config(bind_dn=None, bind_password=None)
        conn.connect()
        conn.bind()
        mock_inner.simple_bind_s.assert_called_with("", "")

    def test_bind_error(self, mock_conn):
        conn, mock_inner, _ = mock_conn
        conn.connect()
        mock_inner.simple_bind_s.side_effect = RuntimeError("bind fail")
        with pytest.raises(LDAPBindError):
            conn.bind()

    def test_disconnect(self, mock_conn):
        conn, mock_inner, _ = mock_conn
        conn.connect()
        conn.bind()
        conn.disconnect()
        assert conn.is_connected is False

    def test_disconnect_error_suppressed(self, mock_conn):
        conn, mock_inner, _ = mock_conn
        conn.connect()
        mock_inner.unbind_s.side_effect = RuntimeError("unbind fail")
        conn.disconnect()
        assert conn.is_connected is False

    def test_whoami_not_bound(self, mock_conn):
        conn, _, _ = mock_conn
        with pytest.raises(LDAPConnectionError, match="Not bound"):
            conn.whoami()

    def test_whoami_success(self, mock_conn):
        conn, mock_inner, _ = mock_conn
        conn.connect()
        conn.bind()
        mock_inner.whoami_s.return_value = "dn:cn=admin"
        assert conn.whoami() == "dn:cn=admin"

    def test_search_not_bound(self, mock_conn):
        conn, _, _ = mock_conn
        with pytest.raises(LDAPConnectionError, match="Not bound"):
            conn.search("dc=example", "(uid=test)")

    def test_search_success(self, mock_conn):
        conn, mock_inner, _ = mock_conn
        conn.connect()
        conn.bind()
        mock_inner.search_s.return_value = [("cn=test", {"cn": [b"test"]})]
        results = conn.search("dc=example", "(uid=test)")
        assert len(results) == 1

    def test_search_error(self, mock_conn):
        conn, mock_inner, _ = mock_conn
        conn.connect()
        conn.bind()
        mock_inner.search_s.side_effect = RuntimeError("search fail")
        with pytest.raises(LDAPSearchError):
            conn.search("dc=example", "(uid=test)")

    def test_context_manager(self, mock_conn):
        """Cover __enter__ and __exit__ (lines 394-402)."""
        conn, mock_inner, _ = mock_conn
        # Re-create to test context manager from scratch
        config = conn.config
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.ldap") as ml:
                mi = MagicMock()
                ml.initialize.return_value = mi
                ml.OPT_REFERRALS = 0
                ml.OPT_PROTOCOL_VERSION = 0
                ml.VERSION3 = 3
                ml.OPT_X_TLS_REQUIRE_CERT = 0
                ml.OPT_X_TLS_DEMAND = 0
                ml.OPT_X_TLS_CACERTFILE = 0
                c = LDAPConnection(config)
                with c as ctx:
                    assert ctx.is_connected is True
                assert c.is_connected is False


class TestLDAPConnectionPoolAdvanced:
    """Cover pool edge cases."""

    def test_pool_shutdown_empty(self):
        config = _make_ldap_config()
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            pool = LDAPConnectionPool(config)
            pool.shutdown()
            assert pool.active_connections == 0

    def test_pool_health_check(self):
        config = _make_ldap_config()
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            pool = LDAPConnectionPool(config)
            health = pool.health_check()
            assert health["healthy"] is True
            assert health["max_size"] == config.pool_size


class TestLDAPIntegrationBuildUserDn:
    """Cover build_user_dn and resolve_user_dn."""

    def test_build_user_dn_with_pattern(self):
        config = _make_ldap_config(
            user_dn_pattern="uid={username},ou=users,dc=example,dc=com",
            circuit_breaker_enabled=False,
        )
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            integration = LDAPIntegration(config)
            dn = integration.build_user_dn("john")
            assert dn == "uid=john,ou=users,dc=example,dc=com"

    def test_build_user_dn_default(self):
        config = _make_ldap_config(circuit_breaker_enabled=False)
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            integration = LDAPIntegration(config)
            dn = integration.build_user_dn("john")
            assert dn == "uid=john,dc=example,dc=com"


class TestLDAPIntegrationMapGroupsToMaciRoles:
    """Cover _map_groups_to_maci_roles (lines 831-844)."""

    def test_map_groups_empty(self):
        config = _make_ldap_config(circuit_breaker_enabled=False)
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            integration = LDAPIntegration(config)
            roles = integration._map_groups_to_maci_roles([])
            assert roles == []

    def test_map_groups_with_mapping(self):
        config = _make_ldap_config(
            circuit_breaker_enabled=False,
            group_to_maci_role_mapping={"Admins": "proposer", "Reviewers": "validator"},
        )
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            integration = LDAPIntegration(config)
            roles = integration._map_groups_to_maci_roles(["admins", "reviewers"])
            assert "proposer" in roles
            assert "validator" in roles

    def test_map_groups_no_duplicates(self):
        config = _make_ldap_config(
            circuit_breaker_enabled=False,
            group_to_maci_role_mapping={"Admins": "proposer"},
        )
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            integration = LDAPIntegration(config)
            roles = integration._map_groups_to_maci_roles(["admins", "Admins"])
            assert roles.count("proposer") == 1

    def test_map_groups_no_match(self):
        config = _make_ldap_config(
            circuit_breaker_enabled=False,
            group_to_maci_role_mapping={"Admins": "proposer"},
        )
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            integration = LDAPIntegration(config)
            roles = integration._map_groups_to_maci_roles(["users"])
            assert roles == []


class TestLDAPIntegrationCheckCircuitBreaker:
    """Cover _check_circuit_breaker (line 527-529)."""

    def test_circuit_breaker_open_raises(self):
        config = _make_ldap_config(
            circuit_breaker_enabled=True,
            circuit_breaker_failure_threshold=1,
        )
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            integration = LDAPIntegration(config)
            integration.circuit_breaker.record_failure()
            with pytest.raises(LDAPCircuitOpenError):
                integration._check_circuit_breaker()

    def test_circuit_breaker_disabled(self):
        config = _make_ldap_config(circuit_breaker_enabled=False)
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            integration = LDAPIntegration(config)
            # Should not raise
            integration._check_circuit_breaker()


class TestLDAPIntegrationNoPool:
    """Cover LDAPIntegration when LDAP_AVAILABLE is False."""

    def test_no_pool_when_unavailable(self):
        config = _make_ldap_config(circuit_breaker_enabled=False)
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", False):
            integration = LDAPIntegration(config)
            assert integration._pool is None


class TestLDAPIntegrationLogAuth:
    """Cover _log_authentication_attempt (lines 846-868)."""

    def test_log_success(self):
        config = _make_ldap_config(circuit_breaker_enabled=False)
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            integration = LDAPIntegration(config)
            # Should not raise
            integration._log_authentication_attempt(
                username="testuser",
                success=True,
                constitutional_hash="608508a9bd224290",
            )

    def test_log_failure_with_error(self):
        config = _make_ldap_config(circuit_breaker_enabled=False)
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            integration = LDAPIntegration(config)
            integration._log_authentication_attempt(
                username="testuser",
                success=False,
                error="bad password",
                constitutional_hash="608508a9bd224290",
            )


class TestLDAPConfigFromTenant:
    """Cover LDAPConfig.from_tenant_config."""

    def test_from_tenant_config(self):
        config = LDAPConfig.from_tenant_config(
            tenant_id="t1",
            server_uri="ldap://test",
            base_dn="dc=test",
        )
        assert config.tenant_id == "t1"
        assert config.server_uri == "ldap://test"


class TestLDAPAuthenticationResult:
    """Cover LDAPAuthenticationResult model."""

    def test_failed_result(self):
        result = LDAPAuthenticationResult(
            success=False,
            error="User not found",
            error_code="USER_NOT_FOUND",
        )
        assert result.success is False
        assert result.maci_roles == []
        assert result.groups == []

    def test_successful_result(self):
        result = LDAPAuthenticationResult(
            success=True,
            user_dn="cn=test",
            email="test@example.com",
            display_name="Test User",
            groups=["admins"],
            maci_roles=["proposer"],
            session_token="tok123",
            expires_at=datetime.now(UTC),
            tenant_id="t1",
        )
        assert result.success is True
        assert result.user_dn == "cn=test"


class TestLDAPExceptions:
    """Cover exception classes."""

    def test_integration_error(self):
        err = LDAPIntegrationError("test error")
        assert "test error" in str(err)
        assert err.http_status_code == 500
        assert err.error_code == "LDAP_INTEGRATION_ERROR"

    def test_connection_error(self):
        err = LDAPConnectionError("conn fail")
        assert err.http_status_code == 503

    def test_bind_error(self):
        err = LDAPBindError("bind fail")
        assert err.http_status_code == 401

    def test_search_error(self):
        err = LDAPSearchError("search fail")
        assert isinstance(err, LDAPIntegrationError)

    def test_circuit_open_error(self):
        err = LDAPCircuitOpenError("circuit open")
        assert isinstance(err, LDAPIntegrationError)


class TestLDAPIntegrationIsMemberOf:
    """Cover is_member_of (lines 755-758)."""

    def test_is_member_of_true(self):
        config = _make_ldap_config(circuit_breaker_enabled=False)
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            integration = LDAPIntegration(config)
            with patch.object(integration, "get_user_groups", return_value=["Admins", "Users"]):
                assert integration.is_member_of("john", "admins") is True

    def test_is_member_of_false(self):
        config = _make_ldap_config(circuit_breaker_enabled=False)
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            integration = LDAPIntegration(config)
            with patch.object(integration, "get_user_groups", return_value=["Users"]):
                assert integration.is_member_of("john", "admins") is False


class TestLDAPIntegrationGetGroupMembers:
    """Cover get_group_members (lines 790-798)."""

    def test_get_group_members_list(self):
        config = _make_ldap_config(circuit_breaker_enabled=False)
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            integration = LDAPIntegration(config)
            with patch.object(
                integration,
                "search_group",
                return_value={"dn": "cn=admins", "member": ["cn=a", "cn=b"]},
            ):
                members = integration.get_group_members("admins")
                assert members == ["cn=a", "cn=b"]

    def test_get_group_members_string(self):
        config = _make_ldap_config(circuit_breaker_enabled=False)
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            integration = LDAPIntegration(config)
            with patch.object(
                integration,
                "search_group",
                return_value={"dn": "cn=solo", "member": "cn=only"},
            ):
                members = integration.get_group_members("solo")
                assert members == ["cn=only"]

    def test_get_group_members_not_found(self):
        config = _make_ldap_config(circuit_breaker_enabled=False)
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            integration = LDAPIntegration(config)
            with patch.object(integration, "search_group", return_value=None):
                members = integration.get_group_members("missing")
                assert members == []


class TestLDAPIntegrationGetUserAttributes:
    """Cover get_user_attributes (lines 678-681)."""

    def test_get_user_attributes_found(self):
        config = _make_ldap_config(circuit_breaker_enabled=False)
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            integration = LDAPIntegration(config)
            with patch.object(
                integration,
                "search_user",
                return_value={"dn": "cn=test", "cn": "test"},
            ):
                attrs = integration.get_user_attributes("test")
                assert attrs["cn"] == "test"

    def test_get_user_attributes_not_found(self):
        config = _make_ldap_config(circuit_breaker_enabled=False)
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            integration = LDAPIntegration(config)
            with patch.object(integration, "search_user", return_value=None):
                assert integration.get_user_attributes("missing") is None


class TestLDAPIntegrationResolveUserDn:
    """Cover resolve_user_dn (lines 563-566)."""

    def test_resolve_user_dn_found(self):
        config = _make_ldap_config(circuit_breaker_enabled=False)
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            integration = LDAPIntegration(config)
            with patch.object(
                integration,
                "search_user",
                return_value={"dn": "uid=john,dc=example,dc=com"},
            ):
                dn = integration.resolve_user_dn("john")
                assert dn == "uid=john,dc=example,dc=com"

    def test_resolve_user_dn_not_found(self):
        config = _make_ldap_config(circuit_breaker_enabled=False)
        with patch("enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE", True):
            integration = LDAPIntegration(config)
            with patch.object(integration, "search_user", return_value=None):
                assert integration.resolve_user_dn("missing") is None
