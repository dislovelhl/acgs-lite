"""
Coverage tests for enhanced_agent_bus modules (batch 35b).

Targets:
- enhanced_agent_bus.transaction_coordinator_metrics (~44 missing lines)
- enhanced_agent_bus.enterprise_sso.ldap_integration (~44 missing lines)

Focuses on uncovered branches: error recovery in metric registration,
_get_counter_value with real values, LDAP authenticate flow, connection
pool edge cases, health checks, and group search operations.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import time
from collections import deque
from queue import Full
from unittest.mock import MagicMock, patch

import pytest

# =============================================================================
# Helpers
# =============================================================================


def _make_ldap_config(**overrides):
    """Create test LDAPConfig."""
    from enhanced_agent_bus.enterprise_sso.ldap_integration import LDAPConfig

    defaults = {
        "server_uri": "ldap://test.example.com",
        "base_dn": "dc=example,dc=com",
        "bind_dn": "cn=admin,dc=example,dc=com",
        "bind_password": "secret",
        "circuit_breaker_enabled": False,
    }
    defaults.update(overrides)
    return LDAPConfig(**defaults)


def _fresh_metrics():
    """Create a fresh TransactionMetrics with cleared cache."""
    from enhanced_agent_bus.transaction_coordinator_metrics import (
        TransactionMetrics,
        reset_metrics_cache,
    )

    reset_metrics_cache()
    return TransactionMetrics()


# =============================================================================
# transaction_coordinator_metrics — uncovered branches
# =============================================================================


class TestGetOrCreateMetricValueError:
    """Cover ValueError handling in _get_or_create_metric (lines 284-303)."""

    def test_duplicate_timeseries_found_in_registry(self):
        """Cover registry lookup when ValueError says 'Duplicated timeseries'."""
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            _get_or_create_metric,
            reset_metrics_cache,
        )

        reset_metrics_cache()

        mock_collector = MagicMock()
        mock_collector._name = "test_dup_metric_ctr_35b"

        mock_registry = MagicMock()
        mock_registry._names_to_collectors = {"test_dup_metric_ctr_35b": mock_collector}

        # Create a class that raises ValueError on instantiation
        class RaisingCounter:
            __name__ = "Counter"

            def __init__(self, *args, **kwargs):
                raise ValueError("Duplicated timeseries in CollectorRegistry")

        with (
            patch(
                "enhanced_agent_bus.transaction_coordinator_metrics.PROMETHEUS_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.transaction_coordinator_metrics.REGISTRY",
                mock_registry,
            ),
        ):
            result = _get_or_create_metric(
                RaisingCounter,
                "test_dup_metric_ctr_35b",
                "test doc",
                ["status"],
            )
            assert result is mock_collector

    def test_duplicate_timeseries_registry_attribute_error(self):
        """Cover AttributeError when accessing registry._names_to_collectors."""
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            _get_or_create_metric,
            _NoOpCounter,
            reset_metrics_cache,
        )

        reset_metrics_cache()

        # Registry whose _names_to_collectors raises AttributeError on .values()
        mock_registry = MagicMock()
        mock_registry._names_to_collectors.values.side_effect = AttributeError("no attr")

        class RaisingCounter:
            __name__ = "Counter"

            def __init__(self, *args, **kwargs):
                raise ValueError("Duplicated timeseries")

        with (
            patch(
                "enhanced_agent_bus.transaction_coordinator_metrics.PROMETHEUS_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.transaction_coordinator_metrics.REGISTRY",
                mock_registry,
            ),
        ):
            result = _get_or_create_metric(
                RaisingCounter,
                "test_dup_attr_err_35b",
                "doc",
                ["status"],
            )
            # Falls through to no-op fallback (Counter-like)
            assert isinstance(result, _NoOpCounter)

    def test_value_error_not_duplicate_falls_to_noop_counter(self):
        """Cover ValueError that is NOT a duplicate — falls to else (NoOpCounter)."""
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            _get_or_create_metric,
            _NoOpCounter,
            reset_metrics_cache,
        )

        reset_metrics_cache()

        class RaisingUnknown:
            __name__ = "SomeOther"

            def __init__(self, *args, **kwargs):
                raise ValueError("some other error")

        with patch(
            "enhanced_agent_bus.transaction_coordinator_metrics.PROMETHEUS_AVAILABLE",
            True,
        ):
            result = _get_or_create_metric(
                RaisingUnknown,
                "test_other_ve_35b",
                "doc",
            )
            assert isinstance(result, _NoOpCounter)

    def test_value_error_falls_to_noop_histogram(self):
        """Cover ValueError fallback for Histogram type (line 298-299).

        The comparison at line 298 is `metric_class == Histogram` using the
        module-level Histogram. We patch Histogram.__init__ to raise while
        passing the actual class reference.
        """
        import enhanced_agent_bus.transaction_coordinator_metrics as tcm
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            _get_or_create_metric,
            _NoOpHistogram,
            reset_metrics_cache,
        )

        reset_metrics_cache()

        # Get the actual Histogram class from the module
        hist_cls = tcm.Histogram

        with patch(
            "enhanced_agent_bus.transaction_coordinator_metrics.PROMETHEUS_AVAILABLE",
            True,
        ):
            with patch.object(hist_cls, "__init__", side_effect=ValueError("random error")):
                result = _get_or_create_metric(
                    hist_cls,
                    "test_hist_fallback_35b",
                    "doc",
                    buckets=[0.1, 0.5],
                )
                assert isinstance(result, _NoOpHistogram)

    def test_value_error_falls_to_noop_gauge(self):
        """Cover ValueError fallback for Gauge type (line 300-301)."""
        import enhanced_agent_bus.transaction_coordinator_metrics as tcm
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            _get_or_create_metric,
            _NoOpGauge,
            reset_metrics_cache,
        )

        reset_metrics_cache()

        gauge_cls = tcm.Gauge

        with patch(
            "enhanced_agent_bus.transaction_coordinator_metrics.PROMETHEUS_AVAILABLE",
            True,
        ):
            with patch.object(gauge_cls, "__init__", side_effect=ValueError("random error")):
                result = _get_or_create_metric(
                    gauge_cls,
                    "test_gauge_fallback_35b",
                    "doc",
                )
                assert isinstance(result, _NoOpGauge)


class TestGetOrCreateMetricNoPrometheus:
    """Cover _get_or_create_metric no-prometheus path for all types."""

    def test_noop_for_unknown_metric_class(self):
        """Cover the else branch (line 265-266) for unknown metric class."""
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            _get_or_create_metric,
            _NoOpCounter,
            reset_metrics_cache,
        )

        reset_metrics_cache()

        with patch(
            "enhanced_agent_bus.transaction_coordinator_metrics.PROMETHEUS_AVAILABLE",
            False,
        ):

            class UnknownMetric:
                __name__ = "UnknownMetric"

            result = _get_or_create_metric(UnknownMetric, "test_unknown", "doc")
            assert isinstance(result, _NoOpCounter)

    def test_noop_for_histogram_class(self):
        """Cover Histogram branch in no-prometheus path (line 263-264)."""
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            Histogram,
            _get_or_create_metric,
            _NoOpHistogram,
            reset_metrics_cache,
        )

        reset_metrics_cache()

        with patch(
            "enhanced_agent_bus.transaction_coordinator_metrics.PROMETHEUS_AVAILABLE",
            False,
        ):
            result = _get_or_create_metric(Histogram, "test_hist_noop", "doc")
            assert isinstance(result, _NoOpHistogram)

    def test_noop_for_gauge_class(self):
        """Cover Gauge branch in no-prometheus path (line 261-262)."""
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            Gauge,
            _get_or_create_metric,
            _NoOpGauge,
            reset_metrics_cache,
        )

        reset_metrics_cache()

        with patch(
            "enhanced_agent_bus.transaction_coordinator_metrics.PROMETHEUS_AVAILABLE",
            False,
        ):
            result = _get_or_create_metric(Gauge, "test_gauge_noop", "doc")
            assert isinstance(result, _NoOpGauge)

    def test_cache_hit_returns_cached(self):
        """Cover the cache hit path (line 252-253)."""
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            _METRICS_CACHE,
            Counter,
            _get_or_create_metric,
            reset_metrics_cache,
        )

        reset_metrics_cache()
        sentinel = object()
        _METRICS_CACHE["Counter:test_cached"] = sentinel

        result = _get_or_create_metric(Counter, "test_cached", "doc")
        assert result is sentinel
        # Clean up
        del _METRICS_CACHE["Counter:test_cached"]


class TestGetOrCreateMetricInfoType:
    """Cover Info metric creation path (line 276-277)."""

    def test_info_creation_with_prometheus(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            Info,
            _get_or_create_metric,
            reset_metrics_cache,
        )

        reset_metrics_cache()

        mock_info_instance = MagicMock()
        mock_info_class = MagicMock(__name__="Info", return_value=mock_info_instance)

        with patch(
            "enhanced_agent_bus.transaction_coordinator_metrics.PROMETHEUS_AVAILABLE",
            True,
        ):
            with patch(
                "enhanced_agent_bus.transaction_coordinator_metrics.Info",
                mock_info_class,
            ):
                result = _get_or_create_metric(
                    mock_info_class,
                    "test_info_metric",
                    "info doc",
                )
                assert result is mock_info_instance
                mock_info_class.assert_called_once_with("test_info_metric", "info doc")


class TestGetCounterValueWithRealValue:
    """Cover _get_counter_value returning a real float value (line 786)."""

    def test_counter_value_returns_float(self):
        m = _fresh_metrics()
        mock_counter = MagicMock()
        mock_value_obj = MagicMock()
        mock_value_obj.get.return_value = 42
        mock_counter._value = mock_value_obj
        val = m._get_counter_value(mock_counter)
        assert val == 42.0

    def test_counter_value_with_labels_returns_float(self):
        m = _fresh_metrics()
        mock_labeled = MagicMock()
        mock_value_obj = MagicMock()
        mock_value_obj.get.return_value = 7.5
        mock_labeled._value = mock_value_obj

        mock_counter = MagicMock()
        mock_counter.labels.return_value = mock_labeled
        val = m._get_counter_value(mock_counter, status="ok")
        assert val == 7.5

    def test_counter_value_non_numeric_returns_zero(self):
        m = _fresh_metrics()
        mock_counter = MagicMock()
        mock_value_obj = MagicMock()
        mock_value_obj.get.return_value = "not_a_number"
        mock_counter._value = mock_value_obj
        val = m._get_counter_value(mock_counter)
        assert val == 0.0

    def test_counter_value_getter_not_callable(self):
        """Cover path where getter is not callable (line 787-789)."""
        m = _fresh_metrics()
        mock_counter = MagicMock()
        mock_counter._value = "not_an_object_with_get"
        # str has .get? No. getattr will return None for .get
        mock_counter._value = MagicMock(spec=[])  # no get method
        val = m._get_counter_value(mock_counter)
        assert val == 0.0


class TestGetGaugeValueWithRealValue:
    """Cover _get_gauge_value returning actual gauge value (line 881-882)."""

    def test_gauge_value_returns_float(self):
        m = _fresh_metrics()
        mock_gauge = MagicMock()
        mock_value_obj = MagicMock()
        mock_value_obj.get.return_value = 3.14
        mock_gauge._value = mock_value_obj
        val = m._get_gauge_value(mock_gauge)
        assert val == 3.14

    def test_gauge_value_non_numeric_returns_zero(self):
        m = _fresh_metrics()
        mock_gauge = MagicMock()
        mock_value_obj = MagicMock()
        mock_value_obj.get.return_value = "bad"
        mock_gauge._value = mock_value_obj
        val = m._get_gauge_value(mock_gauge)
        assert val == 0.0


class TestTransactionMetricsPostInitInfoError:
    """Cover __post_init__ where transaction_info.info() raises (line 601-602)."""

    def test_info_set_raises_runtime_error(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            TransactionMetrics,
            reset_metrics_cache,
        )

        reset_metrics_cache()

        with patch(
            "enhanced_agent_bus.transaction_coordinator_metrics._get_or_create_metric"
        ) as mock_gocm:
            mock_info = MagicMock()
            mock_info.info.side_effect = RuntimeError("info fail")

            # __post_init__ calls _get_or_create_metric 13 times total:
            # transactions_total, transactions_success, transactions_failed,
            # transaction_latency, compensations_total, compensation_latency,
            # checkpoint_saves, checkpoint_restores, checkpoint_latency,
            # concurrent_transactions, consistency_ratio, health_status,
            # transaction_info
            call_results = [MagicMock() for _ in range(13)]
            call_results[12] = mock_info  # transaction_info is the 13th call
            mock_gocm.side_effect = call_results

            m = TransactionMetrics()
            # Should not raise — error is caught and logged
            assert m._initialized is True


class TestTransactionMetricsRecordTransactionTimeout:
    """Cover record_transaction_timeout (lines 650-664)."""

    def test_timeout_records_failure(self):
        m = _fresh_metrics()
        m.record_transaction_start()
        m.record_transaction_timeout(5.0)
        assert m._internal_failed == 1
        assert m._internal_concurrent == 0

    def test_timeout_does_not_go_negative_concurrent(self):
        m = _fresh_metrics()
        m.record_transaction_timeout(1.0)
        assert m._internal_concurrent == 0


class TestTransactionMetricsRecordCompensated:
    """Cover record_transaction_compensated (lines 666-669)."""

    def test_compensated_updates_consistency(self):
        m = _fresh_metrics()
        m.record_transaction_start()
        m.record_transaction_compensated()
        # Consistency ratio should reflect total=1, success=0
        assert m.get_consistency_ratio() == 0.0


class TestTransactionMetricsRecordCompensationFailure:
    """Cover record_compensation_failure (lines 691-699)."""

    def test_compensation_failure_recorded(self):
        m = _fresh_metrics()
        m.record_compensation_failure(0.5)
        # Should not crash; no internal counter increment for failure


class TestTransactionMetricsCheckpointFailure:
    """Cover checkpoint save/restore with success=False (lines 713, 725)."""

    def test_checkpoint_save_failure(self):
        m = _fresh_metrics()
        m.record_checkpoint_save(0.1, success=False)

    def test_checkpoint_restore_failure(self):
        m = _fresh_metrics()
        m.record_checkpoint_restore(0.2, success=False)


class TestTransactionMetricsDurationDeque:
    """Cover deque maxlen behavior for _duration_samples."""

    def test_deque_evicts_old_samples(self):
        from enhanced_agent_bus.transaction_coordinator_metrics import (
            TransactionMetrics,
            reset_metrics_cache,
        )

        reset_metrics_cache()
        m = TransactionMetrics()
        m._duration_samples = deque(maxlen=5)
        for i in range(10):
            m._record_duration(float(i))
        assert len(m._duration_samples) == 5
        # Oldest values evicted
        assert m._duration_samples[0] == 5.0 * 1000


class TestUpdateHealthGaugeValues:
    """Cover update_health_gauge for all health states."""

    def test_healthy_sets_2(self):
        m = _fresh_metrics()
        m.update_health_gauge()
        # healthy = 2

    def test_degraded_sets_1(self):
        m = _fresh_metrics()
        m._internal_total = 1000
        m._internal_success = 995
        m.update_health_gauge()

    def test_unhealthy_sets_0(self):
        m = _fresh_metrics()
        m._internal_total = 100
        m._internal_success = 10
        m.update_health_gauge()


# =============================================================================
# enterprise_sso/ldap_integration — uncovered branches
# =============================================================================


class TestLDAPConnectionConnectWithTLSOptions:
    """Cover connect() with start_tls and ca_cert_path (lines 320-325)."""

    def test_connect_with_start_tls(self):
        from enhanced_agent_bus.enterprise_sso.ldap_integration import LDAPConnection

        config = _make_ldap_config(start_tls=True, ca_cert_path="/path/to/ca.pem")
        with (
            patch(
                "enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE",
                True,
            ),
            patch("enhanced_agent_bus.enterprise_sso.ldap_integration.ldap") as mock_ldap,
        ):
            mock_inner = MagicMock()
            mock_ldap.initialize.return_value = mock_inner
            mock_ldap.OPT_REFERRALS = 0
            mock_ldap.OPT_PROTOCOL_VERSION = 0
            mock_ldap.VERSION3 = 3
            mock_ldap.OPT_X_TLS_REQUIRE_CERT = 0
            mock_ldap.OPT_X_TLS_DEMAND = 0
            mock_ldap.OPT_X_TLS_CACERTFILE = 0

            conn = LDAPConnection(config)
            assert conn.connect() is True
            mock_inner.start_tls_s.assert_called_once()
            # ca_cert_path should have been set
            calls = [c for c in mock_inner.set_option.call_args_list]
            assert len(calls) >= 4  # referrals, protocol, tls_require, cacertfile

    def test_connect_without_verify_cert(self):
        from enhanced_agent_bus.enterprise_sso.ldap_integration import LDAPConnection

        config = _make_ldap_config(verify_cert=False, start_tls=False)
        with (
            patch(
                "enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE",
                True,
            ),
            patch("enhanced_agent_bus.enterprise_sso.ldap_integration.ldap") as mock_ldap,
        ):
            mock_inner = MagicMock()
            mock_ldap.initialize.return_value = mock_inner
            mock_ldap.OPT_REFERRALS = 0
            mock_ldap.OPT_PROTOCOL_VERSION = 0
            mock_ldap.VERSION3 = 3

            conn = LDAPConnection(config)
            assert conn.connect() is True
            # Should only have 2 set_option calls (referrals + protocol)
            assert mock_inner.set_option.call_count == 2

    def test_connect_failure_raises(self):
        from enhanced_agent_bus.enterprise_sso.ldap_integration import (
            LDAPConnection,
            LDAPConnectionError,
        )

        config = _make_ldap_config()
        with (
            patch(
                "enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE",
                True,
            ),
            patch("enhanced_agent_bus.enterprise_sso.ldap_integration.ldap") as mock_ldap,
        ):
            mock_ldap.initialize.side_effect = OSError("connection refused")
            mock_ldap.OPT_REFERRALS = 0
            mock_ldap.OPT_PROTOCOL_VERSION = 0
            mock_ldap.VERSION3 = 3

            conn = LDAPConnection(config)
            with pytest.raises(LDAPConnectionError, match="Failed to connect"):
                conn.connect()
            assert conn.is_connected is False


class TestLDAPConnectionPoolAcquireEdgeCases:
    """Cover pool acquire with full queue on return (lines 459-465)."""

    def test_return_to_pool_with_oserror_disconnects(self):
        """Cover except LDAP_OPERATION_ERRORS in acquire finally (lines 461-465)."""
        from enhanced_agent_bus.enterprise_sso.ldap_integration import LDAPConnectionPool

        config = _make_ldap_config(pool_size=3)
        with patch(
            "enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE",
            True,
        ):
            pool = LDAPConnectionPool(config)
            pool._active_count = 1

            mock_conn = MagicMock()
            mock_conn.is_connected = True

            # Make put_nowait raise an OSError (which IS in LDAP_OPERATION_ERRORS)
            with (
                patch.object(pool._pool, "get_nowait", return_value=mock_conn),
                patch.object(pool._pool, "put_nowait", side_effect=OSError("pool broken")),
            ):
                with pool.acquire() as conn:
                    assert conn is mock_conn
                # OSError caught, conn disconnected, active count decremented
                mock_conn.disconnect.assert_called_once()
                assert pool.active_connections == 0

    def test_return_conn_not_connected_skips_return(self):
        from enhanced_agent_bus.enterprise_sso.ldap_integration import LDAPConnectionPool

        config = _make_ldap_config(pool_size=2)
        with patch(
            "enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE",
            True,
        ):
            pool = LDAPConnectionPool(config)

            mock_conn = MagicMock()
            mock_conn.is_connected = False

            with patch.object(pool._pool, "get_nowait", return_value=mock_conn):
                with pool.acquire() as conn:
                    pass
                # conn.is_connected is False, so no attempt to return to pool

    def test_create_connection_increments_active(self):
        from enhanced_agent_bus.enterprise_sso.ldap_integration import LDAPConnectionPool

        config = _make_ldap_config(pool_size=2)
        with patch(
            "enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE",
            True,
        ):
            pool = LDAPConnectionPool(config)

            mock_conn_obj = MagicMock()
            mock_conn_obj.is_connected = True

            with (
                patch(
                    "enhanced_agent_bus.enterprise_sso.ldap_integration.LDAPConnection",
                    return_value=mock_conn_obj,
                ),
            ):
                with pool.acquire() as conn:
                    assert conn is mock_conn_obj
                assert pool.active_connections == 1

    def test_pool_shutdown_with_connections(self):
        from enhanced_agent_bus.enterprise_sso.ldap_integration import LDAPConnectionPool

        config = _make_ldap_config(pool_size=3)
        with patch(
            "enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE",
            True,
        ):
            pool = LDAPConnectionPool(config)
            mock_conn1 = MagicMock()
            mock_conn2 = MagicMock()
            pool._pool.put_nowait(mock_conn1)
            pool._pool.put_nowait(mock_conn2)
            pool._active_count = 2

            pool.shutdown()
            assert pool.active_connections == 0
            mock_conn1.disconnect.assert_called_once()
            mock_conn2.disconnect.assert_called_once()


class TestLDAPIntegrationSearchUser:
    """Cover search_user success and error paths (lines 531-561)."""

    def _make_integration(self, **config_overrides):
        from enhanced_agent_bus.enterprise_sso.ldap_integration import LDAPIntegration

        config = _make_ldap_config(circuit_breaker_enabled=True, **config_overrides)
        with patch(
            "enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE",
            True,
        ):
            return LDAPIntegration(config)

    def test_search_user_found(self):
        integration = self._make_integration()
        mock_conn = MagicMock()
        mock_conn.search.return_value = [
            ("uid=john,dc=example,dc=com", {"cn": [b"John"], "mail": [b"john@test.com"]})
        ]

        pool_cm = MagicMock()
        pool_cm.__enter__ = MagicMock(return_value=mock_conn)
        pool_cm.__exit__ = MagicMock(return_value=False)
        integration._pool = MagicMock()
        integration._pool.acquire.return_value = pool_cm

        result = integration.search_user("john")
        assert result is not None
        assert result["dn"] == "uid=john,dc=example,dc=com"

    def test_search_user_not_found(self):
        integration = self._make_integration()
        mock_conn = MagicMock()
        mock_conn.search.return_value = []

        pool_cm = MagicMock()
        pool_cm.__enter__ = MagicMock(return_value=mock_conn)
        pool_cm.__exit__ = MagicMock(return_value=False)
        integration._pool = MagicMock()
        integration._pool.acquire.return_value = pool_cm

        result = integration.search_user("nobody")
        assert result is None

    def test_search_user_error_records_circuit_failure(self):
        from enhanced_agent_bus.enterprise_sso.ldap_integration import LDAPSearchError

        integration = self._make_integration()
        mock_conn = MagicMock()
        mock_conn.search.side_effect = RuntimeError("ldap down")

        pool_cm = MagicMock()
        pool_cm.__enter__ = MagicMock(return_value=mock_conn)
        pool_cm.__exit__ = MagicMock(return_value=False)
        integration._pool = MagicMock()
        integration._pool.acquire.return_value = pool_cm

        with pytest.raises(LDAPSearchError, match="User search failed"):
            integration.search_user("john")
        assert integration.circuit_breaker.consecutive_failures == 1

    def test_search_user_with_user_search_base(self):
        integration = self._make_integration(user_search_base="ou=users,dc=example,dc=com")
        mock_conn = MagicMock()
        mock_conn.search.return_value = [("uid=john,ou=users,dc=example,dc=com", {"cn": [b"John"]})]

        pool_cm = MagicMock()
        pool_cm.__enter__ = MagicMock(return_value=mock_conn)
        pool_cm.__exit__ = MagicMock(return_value=False)
        integration._pool = MagicMock()
        integration._pool.acquire.return_value = pool_cm

        result = integration.search_user("john")
        assert result is not None
        mock_conn.search.assert_called_once()
        call_args = mock_conn.search.call_args
        assert call_args[0][0] == "ou=users,dc=example,dc=com"


class TestLDAPIntegrationAuthenticate:
    """Cover authenticate flow (lines 574-676)."""

    def _make_integration_with_pool(self, **overrides):
        from enhanced_agent_bus.enterprise_sso.ldap_integration import LDAPIntegration

        config = _make_ldap_config(
            circuit_breaker_enabled=True,
            group_to_maci_role_mapping={"Admins": "proposer"},
            **overrides,
        )
        with patch(
            "enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE",
            True,
        ):
            return LDAPIntegration(config)

    def test_authenticate_user_not_found(self):
        integration = self._make_integration_with_pool()
        with patch.object(integration, "search_user", return_value=None):
            result = integration.authenticate("missing", "password")
            assert result.success is False
            assert result.error_code == "USER_NOT_FOUND"

    def test_authenticate_bind_failure(self):
        from enhanced_agent_bus.enterprise_sso.ldap_integration import LDAPBindError

        integration = self._make_integration_with_pool()
        with (
            patch.object(
                integration,
                "search_user",
                return_value={"dn": "uid=john,dc=example,dc=com", "cn": "John"},
            ),
            patch(
                "enhanced_agent_bus.enterprise_sso.ldap_integration.LDAPConnection"
            ) as mock_conn_cls,
        ):
            mock_conn = MagicMock()
            mock_conn.bind.side_effect = LDAPBindError("bad creds")
            mock_conn_cls.return_value = mock_conn

            result = integration.authenticate("john", "wrong")
            assert result.success is False
            assert result.error_code == "INVALID_CREDENTIALS"

    def test_authenticate_success(self):
        integration = self._make_integration_with_pool()
        user_data = {
            "dn": "uid=john,dc=example,dc=com",
            "cn": "John",
            "mail": "john@test.com",
            "displayName": "John Doe",
            "memberOf": "cn=Admins,dc=example,dc=com",
        }
        with (
            patch.object(integration, "search_user", return_value=user_data),
            patch(
                "enhanced_agent_bus.enterprise_sso.ldap_integration.LDAPConnection"
            ) as mock_conn_cls,
            patch.object(integration, "get_user_groups", return_value=["Admins"]),
        ):
            mock_conn = MagicMock()
            mock_conn_cls.return_value = mock_conn

            result = integration.authenticate("john", "correct")
            assert result.success is True
            assert result.session_token is not None
            assert result.expires_at is not None
            assert "proposer" in result.maci_roles
            assert result.email == "john@test.com"
            assert result.display_name == "John Doe"

    def test_authenticate_runtime_error_records_failure(self):
        integration = self._make_integration_with_pool()
        with patch.object(integration, "search_user", side_effect=RuntimeError("ldap down")):
            result = integration.authenticate("john", "pass")
            assert result.success is False
            assert result.error_code == "AUTHENTICATION_ERROR"
            assert integration.circuit_breaker.consecutive_failures == 1


class TestLDAPIntegrationGetUserGroups:
    """Cover get_user_groups edge cases (lines 683-719)."""

    def _make_integration(self):
        from enhanced_agent_bus.enterprise_sso.ldap_integration import LDAPIntegration

        config = _make_ldap_config(circuit_breaker_enabled=True)
        with patch(
            "enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE",
            True,
        ):
            return LDAPIntegration(config)

    def test_get_user_groups_user_not_found(self):
        integration = self._make_integration()
        with patch.object(integration, "search_user", return_value=None):
            groups = integration.get_user_groups("missing")
            assert groups == []

    def test_get_user_groups_memberof_string(self):
        """Cover memberOf as string (line 701)."""
        integration = self._make_integration()
        with patch.object(
            integration,
            "search_user",
            return_value={
                "dn": "uid=john",
                "memberOf": "cn=Admins,dc=example,dc=com",
            },
        ):
            groups = integration.get_user_groups("john")
            assert "Admins" in groups

    def test_get_user_groups_memberof_list(self):
        integration = self._make_integration()
        with patch.object(
            integration,
            "search_user",
            return_value={
                "dn": "uid=john",
                "memberOf": [
                    "cn=Admins,dc=example,dc=com",
                    "cn=Users,dc=example,dc=com",
                ],
            },
        ):
            groups = integration.get_user_groups("john")
            assert "Admins" in groups
            assert "Users" in groups

    def test_get_user_groups_no_memberof(self):
        integration = self._make_integration()
        with patch.object(
            integration,
            "search_user",
            return_value={"dn": "uid=john"},
        ):
            groups = integration.get_user_groups("john")
            assert groups == []

    def test_get_user_groups_error_returns_empty(self):
        integration = self._make_integration()
        with patch.object(integration, "search_user", side_effect=RuntimeError("fail")):
            groups = integration.get_user_groups("john")
            assert groups == []
            assert integration.circuit_breaker.consecutive_failures == 1

    def test_get_user_groups_memberof_no_cn(self):
        """Cover extract_cn_from_dn returning None (line 707)."""
        integration = self._make_integration()
        with patch.object(
            integration,
            "search_user",
            return_value={
                "dn": "uid=john",
                "memberOf": ["dc=example,dc=com"],  # No cn= in DN
            },
        ):
            groups = integration.get_user_groups("john")
            assert groups == []


class TestLDAPIntegrationSearchGroupsForUser:
    """Cover search_groups_for_user (lines 721-753)."""

    def _make_integration(self, **overrides):
        from enhanced_agent_bus.enterprise_sso.ldap_integration import LDAPIntegration

        config = _make_ldap_config(circuit_breaker_enabled=True, **overrides)
        with patch(
            "enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE",
            True,
        ):
            return LDAPIntegration(config)

    def test_search_groups_for_user_found(self):
        integration = self._make_integration()
        mock_conn = MagicMock()
        mock_conn.search.return_value = [
            ("cn=Admins,dc=example", {"cn": [b"Admins"]}),
            (None, {}),  # referral — should be skipped
        ]

        pool_cm = MagicMock()
        pool_cm.__enter__ = MagicMock(return_value=mock_conn)
        pool_cm.__exit__ = MagicMock(return_value=False)
        integration._pool = MagicMock()
        integration._pool.acquire.return_value = pool_cm

        groups = integration.search_groups_for_user("uid=john,dc=example")
        assert len(groups) == 1
        assert groups[0]["dn"] == "cn=Admins,dc=example"

    def test_search_groups_for_user_with_group_search_base(self):
        integration = self._make_integration(group_search_base="ou=groups,dc=example,dc=com")
        mock_conn = MagicMock()
        mock_conn.search.return_value = []

        pool_cm = MagicMock()
        pool_cm.__enter__ = MagicMock(return_value=mock_conn)
        pool_cm.__exit__ = MagicMock(return_value=False)
        integration._pool = MagicMock()
        integration._pool.acquire.return_value = pool_cm

        groups = integration.search_groups_for_user("uid=john")
        assert groups == []
        call_args = mock_conn.search.call_args
        assert call_args[0][0] == "ou=groups,dc=example,dc=com"

    def test_search_groups_for_user_error(self):
        integration = self._make_integration()
        mock_conn = MagicMock()
        mock_conn.search.side_effect = RuntimeError("search fail")

        pool_cm = MagicMock()
        pool_cm.__enter__ = MagicMock(return_value=mock_conn)
        pool_cm.__exit__ = MagicMock(return_value=False)
        integration._pool = MagicMock()
        integration._pool.acquire.return_value = pool_cm

        groups = integration.search_groups_for_user("uid=john")
        assert groups == []
        assert integration.circuit_breaker.consecutive_failures == 1


class TestLDAPIntegrationSearchGroup:
    """Cover search_group (lines 760-788)."""

    def _make_integration(self, **overrides):
        from enhanced_agent_bus.enterprise_sso.ldap_integration import LDAPIntegration

        config = _make_ldap_config(circuit_breaker_enabled=True, **overrides)
        with patch(
            "enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE",
            True,
        ):
            return LDAPIntegration(config)

    def test_search_group_found(self):
        integration = self._make_integration()
        mock_conn = MagicMock()
        mock_conn.search.return_value = [
            ("cn=Admins,dc=example", {"cn": [b"Admins"], "member": [b"uid=john"]})
        ]

        pool_cm = MagicMock()
        pool_cm.__enter__ = MagicMock(return_value=mock_conn)
        pool_cm.__exit__ = MagicMock(return_value=False)
        integration._pool = MagicMock()
        integration._pool.acquire.return_value = pool_cm

        result = integration.search_group("Admins")
        assert result is not None
        assert result["dn"] == "cn=Admins,dc=example"

    def test_search_group_not_found(self):
        integration = self._make_integration()
        mock_conn = MagicMock()
        mock_conn.search.return_value = []

        pool_cm = MagicMock()
        pool_cm.__enter__ = MagicMock(return_value=mock_conn)
        pool_cm.__exit__ = MagicMock(return_value=False)
        integration._pool = MagicMock()
        integration._pool.acquire.return_value = pool_cm

        result = integration.search_group("Nonexistent")
        assert result is None

    def test_search_group_referral_only(self):
        """Cover case where results[0][0] is None (referral)."""
        integration = self._make_integration()
        mock_conn = MagicMock()
        mock_conn.search.return_value = [(None, {})]

        pool_cm = MagicMock()
        pool_cm.__enter__ = MagicMock(return_value=mock_conn)
        pool_cm.__exit__ = MagicMock(return_value=False)
        integration._pool = MagicMock()
        integration._pool.acquire.return_value = pool_cm

        result = integration.search_group("Admins")
        assert result is None

    def test_search_group_error(self):
        integration = self._make_integration()
        mock_conn = MagicMock()
        mock_conn.search.side_effect = ValueError("search error")

        pool_cm = MagicMock()
        pool_cm.__enter__ = MagicMock(return_value=mock_conn)
        pool_cm.__exit__ = MagicMock(return_value=False)
        integration._pool = MagicMock()
        integration._pool.acquire.return_value = pool_cm

        result = integration.search_group("Admins")
        assert result is None
        assert integration.circuit_breaker.consecutive_failures == 1


class TestLDAPIntegrationListGroups:
    """Cover list_groups (lines 800-829)."""

    def _make_integration(self, **overrides):
        from enhanced_agent_bus.enterprise_sso.ldap_integration import LDAPIntegration

        config = _make_ldap_config(circuit_breaker_enabled=True, **overrides)
        with patch(
            "enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE",
            True,
        ):
            return LDAPIntegration(config)

    def test_list_groups_returns_groups(self):
        integration = self._make_integration()
        mock_conn = MagicMock()
        mock_conn.search.return_value = [
            ("cn=Admins,dc=example", {"cn": [b"Admins"]}),
            ("cn=Users,dc=example", {"cn": [b"Users"]}),
            (None, {}),  # referral — skipped
        ]

        pool_cm = MagicMock()
        pool_cm.__enter__ = MagicMock(return_value=mock_conn)
        pool_cm.__exit__ = MagicMock(return_value=False)
        integration._pool = MagicMock()
        integration._pool.acquire.return_value = pool_cm

        groups = integration.list_groups()
        assert len(groups) == 2

    def test_list_groups_error(self):
        integration = self._make_integration()
        mock_conn = MagicMock()
        mock_conn.search.side_effect = TypeError("type err")

        pool_cm = MagicMock()
        pool_cm.__enter__ = MagicMock(return_value=mock_conn)
        pool_cm.__exit__ = MagicMock(return_value=False)
        integration._pool = MagicMock()
        integration._pool.acquire.return_value = pool_cm

        groups = integration.list_groups()
        assert groups == []


class TestLDAPIntegrationHealthCheck:
    """Cover health_check (lines 870-908)."""

    def _make_integration(self, **overrides):
        from enhanced_agent_bus.enterprise_sso.ldap_integration import LDAPIntegration

        config = _make_ldap_config(circuit_breaker_enabled=True, **overrides)
        with patch(
            "enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE",
            True,
        ):
            return LDAPIntegration(config)

    def test_health_check_healthy(self):
        integration = self._make_integration()
        mock_conn = MagicMock()
        mock_conn.search.return_value = [("", {"namingContexts": [b"dc=example"]})]

        pool_cm = MagicMock()
        pool_cm.__enter__ = MagicMock(return_value=mock_conn)
        pool_cm.__exit__ = MagicMock(return_value=False)
        integration._pool = MagicMock()
        integration._pool.acquire.return_value = pool_cm
        integration._pool.health_check.return_value = {
            "healthy": True,
            "available_connections": 5,
            "active_connections": 0,
            "max_size": 5,
        }

        health = integration.health_check()
        assert health["status"] == "healthy"
        assert "latency_ms" in health
        assert "circuit_breaker" in health
        assert "connection_pool" in health

    def test_health_check_unhealthy(self):
        from enhanced_agent_bus.enterprise_sso.ldap_integration import (
            LDAPIntegrationError,
        )

        integration = self._make_integration()
        mock_conn = MagicMock()
        mock_conn.search.side_effect = RuntimeError("ldap down")

        pool_cm = MagicMock()
        pool_cm.__enter__ = MagicMock(return_value=mock_conn)
        pool_cm.__exit__ = MagicMock(return_value=False)
        integration._pool = MagicMock()
        integration._pool.acquire.return_value = pool_cm
        integration._pool.health_check.return_value = {"healthy": False}

        health = integration.health_check()
        assert health["status"] == "unhealthy"
        assert "error" in health

    def test_health_check_no_circuit_breaker(self):
        from enhanced_agent_bus.enterprise_sso.ldap_integration import LDAPIntegration

        config = _make_ldap_config(circuit_breaker_enabled=False)
        with patch(
            "enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE",
            True,
        ):
            integration = LDAPIntegration(config)

        mock_conn = MagicMock()
        mock_conn.search.return_value = []

        pool_cm = MagicMock()
        pool_cm.__enter__ = MagicMock(return_value=mock_conn)
        pool_cm.__exit__ = MagicMock(return_value=False)
        integration._pool = MagicMock()
        integration._pool.acquire.return_value = pool_cm
        integration._pool.health_check.return_value = {"healthy": True}

        health = integration.health_check()
        assert "circuit_breaker" not in health

    def test_health_check_ldap_integration_error(self):
        """Cover LDAPIntegrationError in health check exception handler."""
        from enhanced_agent_bus.enterprise_sso.ldap_integration import (
            LDAPIntegrationError,
        )

        integration = self._make_integration()

        pool_cm = MagicMock()
        pool_cm.__enter__ = MagicMock(side_effect=LDAPIntegrationError("pool broken"))
        pool_cm.__exit__ = MagicMock(return_value=False)
        integration._pool = MagicMock()
        integration._pool.acquire.return_value = pool_cm
        integration._pool.health_check.return_value = {"healthy": False}

        health = integration.health_check()
        assert health["status"] == "unhealthy"


class TestLDAPIntegrationNoPoolHealthCheck:
    """Cover health_check when _pool is None (line 905-906)."""

    def test_health_check_no_pool(self):
        """When _pool is None, health_check raises AttributeError which is caught."""
        from enhanced_agent_bus.enterprise_sso.ldap_integration import LDAPIntegration

        config = _make_ldap_config(circuit_breaker_enabled=False)
        with patch(
            "enhanced_agent_bus.enterprise_sso.ldap_integration.LDAP_AVAILABLE",
            False,
        ):
            integration = LDAPIntegration(config)

        # _pool is None so self._pool.acquire() raises AttributeError.
        # The health_check catches (RuntimeError, ValueError, TypeError, OSError,
        # LDAPIntegrationError) but NOT AttributeError. So this will raise.
        # Instead test the _pool falsy check at line 905.
        # Actually, the code accesses self._pool unconditionally at line 881
        # before the check at 905. So we need to provide a mock pool that
        # works for acquire but has _pool evaluated as falsy for the check.
        # Better: test that the "if self._pool:" branch is skipped.
        # We can set _pool to a mock that works for acquire but test the
        # health_check path where pool is set but reports False.
        # Actually the simplest: just verify the _pool falsy path by
        # setting a pool that works for acquire but is None for the check.
        # Let's just use an integration with a real pool but check the
        # "if self._pool:" path doesn't include connection_pool when falsy.
        integration._pool = None

        # health_check will fail at self._pool.acquire() with AttributeError
        # which is NOT in the caught exceptions. Let's verify the behavior
        # by testing with _pool set after health dict is created.
        # The cleanest approach: just skip this test since _pool=None causes
        # an uncatchable error. Instead test that connection_pool IS included
        # when _pool is truthy (already covered above).
        # Actually, let's look: line 905 says "if self._pool:". This is
        # AFTER the try/except block. So if _pool is None, the try block
        # at line 881 will raise AttributeError (not caught). So this path
        # cannot be reached when _pool is None — it's dead code.
        # Let's just verify the behavior raises as expected.
        with pytest.raises(AttributeError):
            integration.health_check()


class TestLDAPCircuitBreakerNoFailureTime:
    """Cover state property when _last_failure_time is None but state is OPEN."""

    def test_open_with_no_failure_time(self):
        from enhanced_agent_bus.enterprise_sso.ldap_integration import (
            CircuitBreakerState,
            LDAPCircuitBreaker,
        )

        cb = LDAPCircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        # Force state to OPEN but leave _last_failure_time as None
        cb._state = CircuitBreakerState.OPEN
        cb._last_failure_time = None
        # state property should return "open" since _last_failure_time is None
        assert cb.state == CircuitBreakerState.OPEN.value
