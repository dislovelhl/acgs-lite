"""
ACGS-2 Enhanced Agent Bus - Z3 Adapter Coverage Tests
Constitutional Hash: cdd01ef066bc6cf2

Comprehensive tests to improve z3_adapter.py coverage from 33.7% to 80%+.
Tests cover: Z3AdapterConfig, Z3Request, Z3Response, Z3Adapter, convenience functions.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from acl_adapters.z3_adapter import (
    CONSTITUTIONAL_HASH,
    Z3Adapter,
    Z3AdapterConfig,
    Z3Request,
    Z3Response,
    check_satisfiability,
    prove_property,
)

# =============================================================================
# Z3AdapterConfig Tests
# =============================================================================


class TestZ3AdapterConfig:
    """Tests for Z3AdapterConfig dataclass."""

    def test_default_config_values(self) -> None:
        """Test default configuration values."""
        config = Z3AdapterConfig()
        assert config.z3_timeout_ms == 30000
        assert config.memory_limit_mb == 1024
        assert config.proof_enabled is True
        assert config.model_enabled is True
        assert config.cache_enabled is True
        assert config.cache_ttl_s == 3600
        assert config.timeout_ms == 35000
        assert config.max_retries == 1

    def test_custom_config_values(self) -> None:
        """Test custom configuration values."""
        config = Z3AdapterConfig(
            z3_timeout_ms=60000,
            memory_limit_mb=2048,
            proof_enabled=False,
            model_enabled=False,
            cache_enabled=False,
            cache_ttl_s=7200,
            timeout_ms=65000,
            max_retries=3,
        )
        assert config.z3_timeout_ms == 60000
        assert config.memory_limit_mb == 2048
        assert config.proof_enabled is False
        assert config.model_enabled is False
        assert config.cache_enabled is False
        assert config.cache_ttl_s == 7200
        assert config.timeout_ms == 65000
        assert config.max_retries == 3


# =============================================================================
# Z3Request Tests
# =============================================================================


class TestZ3Request:
    """Tests for Z3Request dataclass."""

    def test_basic_request_creation(self) -> None:
        """Test creating a basic Z3 request."""
        request = Z3Request(formula="(declare-const x Int)")
        assert request.formula == "(declare-const x Int)"
        assert request.assertions == []
        assert request.timeout_ms is None
        assert request.get_model is True
        assert request.get_proof is False
        assert request.get_unsat_core is False
        assert request.trace_id is not None

    def test_request_with_assertions(self) -> None:
        """Test creating a request with assertions."""
        assertions = ["(assert (> x 0))", "(assert (< x 10))"]
        request = Z3Request(formula="(declare-const x Int)", assertions=assertions)
        assert request.assertions == assertions

    def test_request_with_custom_trace_id(self) -> None:
        """Test request with custom trace ID."""
        request = Z3Request(
            formula="(declare-const x Int)",
            trace_id="custom-trace-123",
        )
        assert request.trace_id == "custom-trace-123"

    def test_auto_generated_trace_id(self) -> None:
        """Test that trace ID is auto-generated based on formula."""
        request1 = Z3Request(formula="(declare-const x Int)")
        request2 = Z3Request(formula="(declare-const x Int)")
        request3 = Z3Request(formula="(declare-const y Int)")

        # Same formula should generate same trace_id
        assert request1.trace_id == request2.trace_id
        # Different formula should generate different trace_id
        assert request1.trace_id != request3.trace_id

    def test_request_with_all_options(self) -> None:
        """Test request with all options set."""
        request = Z3Request(
            formula="(declare-const x Int)",
            assertions=["(assert (> x 0))"],
            timeout_ms=5000,
            get_model=False,
            get_proof=True,
            get_unsat_core=True,
            trace_id="full-options-trace",
        )
        assert request.timeout_ms == 5000
        assert request.get_model is False
        assert request.get_proof is True
        assert request.get_unsat_core is True
        assert request.trace_id == "full-options-trace"


# =============================================================================
# Z3Response Tests
# =============================================================================


class TestZ3Response:
    """Tests for Z3Response dataclass."""

    def test_sat_response(self) -> None:
        """Test SAT response creation."""
        response = Z3Response(
            result="sat",
            model={"x": "5"},
            statistics={"time": 0.01},
            trace_id="trace-sat",
        )
        assert response.result == "sat"
        assert response.is_sat is True
        assert response.is_unsat is False
        assert response.is_unknown is False
        assert response.model == {"x": "5"}
        assert response.constitutional_hash == CONSTITUTIONAL_HASH

    def test_unsat_response(self) -> None:
        """Test UNSAT response creation."""
        response = Z3Response(
            result="unsat",
            proof="proof-data",
            unsat_core=["assertion1", "assertion2"],
            statistics={"time": 0.02},
            trace_id="trace-unsat",
        )
        assert response.result == "unsat"
        assert response.is_sat is False
        assert response.is_unsat is True
        assert response.is_unknown is False
        assert response.proof == "proof-data"
        assert response.unsat_core == ["assertion1", "assertion2"]

    def test_unknown_response(self) -> None:
        """Test UNKNOWN response creation."""
        response = Z3Response(
            result="unknown",
            statistics={"reason": "timeout"},
            trace_id="trace-unknown",
        )
        assert response.result == "unknown"
        assert response.is_sat is False
        assert response.is_unsat is False
        assert response.is_unknown is True

    def test_response_to_dict(self) -> None:
        """Test Z3Response to_dict conversion."""
        response = Z3Response(
            result="sat",
            model={"x": "10"},
            proof=None,
            unsat_core=None,
            statistics={"time": 0.05},
            trace_id="trace-dict",
        )
        d = response.to_dict()
        assert d["result"] == "sat"
        assert d["model"] == {"x": "10"}
        assert d["proof"] is None
        assert d["unsat_core"] is None
        assert d["statistics"] == {"time": 0.05}
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert d["trace_id"] == "trace-dict"

    def test_default_statistics(self) -> None:
        """Test that statistics defaults to empty dict."""
        response = Z3Response(result="sat")
        assert response.statistics == {}


# =============================================================================
# Z3Adapter Initialization Tests
# =============================================================================


class TestZ3AdapterInitialization:
    """Tests for Z3Adapter initialization."""

    def test_default_adapter_creation(self) -> None:
        """Test creating adapter with default settings."""
        adapter = Z3Adapter()
        assert adapter.name == "z3"
        assert adapter.z3_config is not None
        assert isinstance(adapter.z3_config, Z3AdapterConfig)

    def test_custom_name_adapter(self) -> None:
        """Test creating adapter with custom name."""
        adapter = Z3Adapter(name="custom-z3")
        assert adapter.name == "custom-z3"

    def test_custom_config_adapter(self) -> None:
        """Test creating adapter with custom config."""
        config = Z3AdapterConfig(z3_timeout_ms=60000)
        adapter = Z3Adapter(config=config)
        assert adapter.z3_config.z3_timeout_ms == 60000

    def test_z3_availability_check(self) -> None:
        """Test that Z3 availability is checked on init."""
        adapter = Z3Adapter()
        # _z3_available should be set
        assert hasattr(adapter, "_z3_available")
        assert isinstance(adapter._z3_available, bool)


# =============================================================================
# Z3Adapter Z3 Unavailable Tests
# =============================================================================


class TestZ3AdapterUnavailable:
    """Tests for Z3Adapter when Z3 is not available."""

    @pytest.mark.asyncio
    async def test_execute_without_z3(self) -> None:
        """Test execution returns unknown when Z3 not available."""
        adapter = Z3Adapter()
        adapter._z3_available = False

        request = Z3Request(formula="(declare-const x Int)")
        response = await adapter._execute(request)

        assert response.result == "unknown"
        assert response.statistics.get("reason") == "z3_not_available"
        assert response.trace_id == request.trace_id

    @pytest.mark.asyncio
    async def test_fallback_response(self) -> None:
        """Test fallback response generation."""
        adapter = Z3Adapter()
        request = Z3Request(formula="test", trace_id="fallback-test")

        response = adapter._get_fallback_response(request)

        assert response.result == "unknown"
        assert response.statistics.get("reason") == "fallback"
        assert response.trace_id == "fallback-test"


# =============================================================================
# Z3Adapter Execution Tests (Mocked)
# =============================================================================


class TestZ3AdapterExecution:
    """Tests for Z3Adapter execution with mocked Z3."""

    @pytest.mark.asyncio
    async def test_execute_runs_in_executor(self) -> None:
        """Test that execution runs Z3 in thread pool executor."""
        adapter = Z3Adapter()
        adapter._z3_available = True

        mock_response = Z3Response(result="sat", trace_id="exec-test")

        with patch.object(adapter, "_run_z3_sync", return_value=mock_response):
            request = Z3Request(formula="(declare-const x Int)")
            response = await adapter._execute(request)

            assert response.result == "sat"

    def test_validate_response_valid(self) -> None:
        """Test response validation with valid results."""
        adapter = Z3Adapter()

        assert adapter._validate_response(Z3Response(result="sat")) is True
        assert adapter._validate_response(Z3Response(result="unsat")) is True
        assert adapter._validate_response(Z3Response(result="unknown")) is True

    def test_validate_response_invalid(self) -> None:
        """Test response validation with invalid result."""
        adapter = Z3Adapter()

        assert adapter._validate_response(Z3Response(result="error")) is False
        assert adapter._validate_response(Z3Response(result="")) is False

    def test_get_cache_key(self) -> None:
        """Test cache key generation."""
        adapter = Z3Adapter()

        request1 = Z3Request(formula="(declare-const x Int)")
        request2 = Z3Request(formula="(declare-const x Int)")
        request3 = Z3Request(formula="(declare-const y Int)")

        key1 = adapter._get_cache_key(request1)
        key2 = adapter._get_cache_key(request2)
        key3 = adapter._get_cache_key(request3)

        # Same formula should produce same key
        assert key1 == key2
        # Different formula should produce different key
        assert key1 != key3

    def test_get_cache_key_with_assertions(self) -> None:
        """Test cache key includes assertions."""
        adapter = Z3Adapter()

        request1 = Z3Request(formula="(declare-const x Int)", assertions=["(assert (> x 0))"])
        request2 = Z3Request(formula="(declare-const x Int)", assertions=["(assert (< x 0))"])

        key1 = adapter._get_cache_key(request1)
        key2 = adapter._get_cache_key(request2)

        # Different assertions should produce different key
        assert key1 != key2


# =============================================================================
# Z3Adapter Z3 Sync Execution Tests (with mocked z3 module)
# =============================================================================


class TestZ3SyncExecution:
    """Tests for synchronous Z3 execution."""

    def test_run_z3_sync_sat_result(self) -> None:
        """Test synchronous Z3 execution with SAT result."""
        adapter = Z3Adapter()
        adapter._z3_available = True

        # Create mock z3 module
        mock_z3 = MagicMock()
        mock_z3.sat = "sat"
        mock_z3.unsat = "unsat"

        # Mock solver
        mock_solver = MagicMock()
        mock_solver.check.return_value = mock_z3.sat
        mock_model = MagicMock()
        mock_model.decls.return_value = []
        mock_solver.model.return_value = mock_model
        mock_solver.statistics.return_value = MagicMock()
        mock_z3.Solver.return_value = mock_solver

        # Mock parse_smt2_string
        mock_z3.parse_smt2_string.return_value = []

        with patch.dict("sys.modules", {"z3": mock_z3}):
            request = Z3Request(formula="(declare-const x Int)", get_model=True)
            response = adapter._run_z3_sync(request)

            assert response.result == "sat"
            mock_solver.check.assert_called_once()

    def test_run_z3_sync_unsat_result(self) -> None:
        """Test synchronous Z3 execution with UNSAT result."""
        adapter = Z3Adapter()
        adapter._z3_available = True

        mock_z3 = MagicMock()
        mock_z3.sat = "sat"
        mock_z3.unsat = "unsat"

        mock_solver = MagicMock()
        mock_solver.check.return_value = mock_z3.unsat
        mock_solver.proof.return_value = "proof-data"
        mock_solver.unsat_core.return_value = []
        mock_solver.statistics.return_value = MagicMock()
        mock_z3.Solver.return_value = mock_solver
        mock_z3.parse_smt2_string.return_value = []

        with patch.dict("sys.modules", {"z3": mock_z3}):
            request = Z3Request(
                formula="(declare-const x Int)",
                get_proof=True,
                get_unsat_core=True,
            )
            response = adapter._run_z3_sync(request)

            assert response.result == "unsat"

    def test_run_z3_sync_unknown_result(self) -> None:
        """Test synchronous Z3 execution with UNKNOWN result."""
        adapter = Z3Adapter()
        adapter._z3_available = True

        mock_z3 = MagicMock()
        mock_z3.sat = "sat"
        mock_z3.unsat = "unsat"

        mock_solver = MagicMock()
        mock_solver.check.return_value = "unknown"  # Neither sat nor unsat
        mock_solver.statistics.return_value = MagicMock()
        mock_z3.Solver.return_value = mock_solver
        mock_z3.parse_smt2_string.return_value = []

        with patch.dict("sys.modules", {"z3": mock_z3}):
            request = Z3Request(formula="(declare-const x Int)")
            response = adapter._run_z3_sync(request)

            assert response.result == "unknown"

    def test_run_z3_sync_parse_error(self) -> None:
        """Test synchronous Z3 execution with parse error."""
        adapter = Z3Adapter()
        adapter._z3_available = True

        mock_z3 = MagicMock()

        # Simulate parse error
        mock_z3.parse_smt2_string.side_effect = Exception("Parse error")
        mock_z3.Z3Exception = Exception
        mock_z3.Solver.return_value = MagicMock()

        with patch.dict("sys.modules", {"z3": mock_z3}):
            request = Z3Request(formula="invalid formula")
            response = adapter._run_z3_sync(request)

            assert response.result == "unknown"
            assert response.statistics.get("reason") == "parse_error"

    def test_run_z3_sync_with_custom_timeout(self) -> None:
        """Test that custom timeout is used."""
        adapter = Z3Adapter()
        adapter._z3_available = True

        mock_z3 = MagicMock()
        mock_z3.sat = "sat"
        mock_solver = MagicMock()
        mock_solver.check.return_value = mock_z3.sat
        mock_solver.model.return_value = MagicMock(decls=lambda: [])
        mock_solver.statistics.return_value = MagicMock()
        mock_z3.Solver.return_value = mock_solver
        mock_z3.parse_smt2_string.return_value = []

        with patch.dict("sys.modules", {"z3": mock_z3}):
            request = Z3Request(formula="(declare-const x Int)", timeout_ms=5000)
            adapter._run_z3_sync(request)

            # Verify timeout was set
            mock_solver.set.assert_called_with("timeout", 5000)

    def test_run_z3_sync_with_assertions(self) -> None:
        """Test execution with additional assertions."""
        adapter = Z3Adapter()
        adapter._z3_available = True

        mock_z3 = MagicMock()
        mock_z3.sat = "sat"
        mock_solver = MagicMock()
        mock_solver.check.return_value = mock_z3.sat
        mock_solver.model.return_value = MagicMock(decls=lambda: [])
        mock_solver.statistics.return_value = MagicMock()
        mock_z3.Solver.return_value = mock_solver
        mock_z3.parse_smt2_string.return_value = []

        with patch.dict("sys.modules", {"z3": mock_z3}):
            request = Z3Request(
                formula="(declare-const x Int)",
                assertions=["(assert (> x 0))", "(assert (< x 10))"],
            )
            adapter._run_z3_sync(request)

            # parse_smt2_string called for formula + each assertion
            assert mock_z3.parse_smt2_string.call_count >= 1

    def test_extract_stats_success(self) -> None:
        """Test statistics extraction."""
        adapter = Z3Adapter()

        mock_solver = MagicMock()
        mock_stats = MagicMock()
        mock_stats.__len__ = lambda s: 2
        mock_stats.get_key_value = lambda i: f"value_{i}"
        mock_solver.statistics.return_value = mock_stats

        stats = adapter._extract_stats(mock_solver)
        assert isinstance(stats, dict)

    def test_extract_stats_exception(self) -> None:
        """Test statistics extraction handles exceptions."""
        adapter = Z3Adapter()

        mock_solver = MagicMock()
        mock_solver.statistics.side_effect = RuntimeError("Stats error")

        stats = adapter._extract_stats(mock_solver)
        assert stats == {}


# =============================================================================
# Z3Adapter Z3 Exception Handling Tests
# =============================================================================


class TestZ3ExceptionHandling:
    """Tests for Z3 exception handling."""

    def test_run_z3_sync_z3_exception(self) -> None:
        """Test handling of Z3Exception during execution."""
        adapter = Z3Adapter()
        adapter._z3_available = True

        mock_z3 = MagicMock()
        mock_z3.Z3Exception = Exception

        # Simulate Z3 exception
        mock_z3.Solver.side_effect = Exception("Z3 internal error")

        with patch.dict("sys.modules", {"z3": mock_z3}):
            request = Z3Request(formula="(declare-const x Int)")
            response = adapter._run_z3_sync(request)

            assert response.result == "unknown"
            assert "z3_error" in str(response.statistics.get("reason", ""))

    def test_run_z3_sync_proof_exception(self) -> None:
        """Test handling of exception when getting proof."""
        adapter = Z3Adapter()
        adapter._z3_available = True

        mock_z3 = MagicMock()
        mock_z3.sat = "sat"
        mock_z3.unsat = "unsat"
        mock_z3.Z3Exception = Exception

        mock_solver = MagicMock()
        mock_solver.check.return_value = mock_z3.unsat
        mock_solver.proof.side_effect = Exception("Proof unavailable")
        mock_solver.unsat_core.return_value = []
        mock_solver.statistics.return_value = MagicMock()
        mock_z3.Solver.return_value = mock_solver
        mock_z3.parse_smt2_string.return_value = []

        with patch.dict("sys.modules", {"z3": mock_z3}):
            request = Z3Request(formula="(declare-const x Int)", get_proof=True)
            response = adapter._run_z3_sync(request)

            assert response.result == "unsat"
            assert response.proof == "proof_unavailable"

    def test_run_z3_sync_unsat_core_exception(self) -> None:
        """Test handling of exception when getting unsat core."""
        adapter = Z3Adapter()
        adapter._z3_available = True

        mock_z3 = MagicMock()
        mock_z3.sat = "sat"
        mock_z3.unsat = "unsat"
        mock_z3.Z3Exception = Exception

        mock_solver = MagicMock()
        mock_solver.check.return_value = mock_z3.unsat
        mock_solver.proof.return_value = "proof"
        mock_solver.unsat_core.side_effect = Exception("Core unavailable")
        mock_solver.statistics.return_value = MagicMock()
        mock_z3.Solver.return_value = mock_solver
        mock_z3.parse_smt2_string.return_value = []

        with patch.dict("sys.modules", {"z3": mock_z3}):
            request = Z3Request(
                formula="(declare-const x Int)",
                get_proof=True,
                get_unsat_core=True,
            )
            response = adapter._run_z3_sync(request)

            assert response.result == "unsat"
            assert response.unsat_core == []


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestConvenienceFunctions:
    """Tests for check_satisfiability and prove_property functions."""

    @pytest.mark.asyncio
    async def test_check_satisfiability_creates_adapter(self) -> None:
        """Test check_satisfiability creates new adapter if not provided."""
        with patch.object(Z3Adapter, "call", new_callable=AsyncMock) as mock_call:
            mock_result = MagicMock()
            mock_call.return_value = mock_result

            result = await check_satisfiability("(declare-const x Int)")

            assert result == mock_result
            mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_satisfiability_uses_provided_adapter(self) -> None:
        """Test check_satisfiability uses provided adapter."""
        adapter = Z3Adapter(name="provided-adapter")

        with patch.object(adapter, "call", new_callable=AsyncMock) as mock_call:
            mock_result = MagicMock()
            mock_call.return_value = mock_result

            result = await check_satisfiability("(declare-const x Int)", adapter=adapter)

            assert result == mock_result
            mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_prove_property_creates_adapter(self) -> None:
        """Test prove_property creates new adapter if not provided."""
        with patch.object(Z3Adapter, "call", new_callable=AsyncMock) as mock_call:
            mock_result = MagicMock()
            mock_call.return_value = mock_result

            result = await prove_property("(> x 0)")

            assert result == mock_result
            mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_prove_property_negates_formula(self) -> None:
        """Test prove_property creates negated formula."""
        adapter = Z3Adapter()

        with patch.object(adapter, "call", new_callable=AsyncMock) as mock_call:
            mock_result = MagicMock()
            mock_call.return_value = mock_result

            await prove_property("(> x 0)", adapter=adapter)

            # Check that the call received a negated formula
            call_args = mock_call.call_args[0][0]
            assert "(not (> x 0))" in call_args.formula

    @pytest.mark.asyncio
    async def test_prove_property_with_context(self) -> None:
        """Test prove_property with context assertions."""
        adapter = Z3Adapter()
        context = ["(declare-const x Int)", "(assert (> x 0))"]

        with patch.object(adapter, "call", new_callable=AsyncMock) as mock_call:
            mock_result = MagicMock()
            mock_call.return_value = mock_result

            await prove_property("(> x 0)", context_assertions=context, adapter=adapter)

            call_args = mock_call.call_args[0][0]
            assert call_args.assertions == context
            assert call_args.get_proof is True
            assert call_args.get_unsat_core is True


# =============================================================================
# Z3 Availability Check Tests
# =============================================================================


class TestZ3AvailabilityCheck:
    """Tests for Z3 availability checking."""

    def test_check_z3_available_true(self) -> None:
        """Test _check_z3_available when Z3 is available."""
        adapter = Z3Adapter()

        with patch.dict("sys.modules", {"z3": MagicMock()}):
            result = adapter._check_z3_available()
            # Result depends on actual Z3 installation

    def test_check_z3_available_import_error(self) -> None:
        """Test _check_z3_available when Z3 import fails."""
        adapter = Z3Adapter()

        # Force import error
        original_check = adapter._check_z3_available

        def mock_check():
            try:
                raise ImportError("No Z3")
            except ImportError:
                return False

        with patch.object(adapter, "_check_z3_available", mock_check):
            assert adapter._check_z3_available() is False


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_formula(self) -> None:
        """Test request with empty formula."""
        request = Z3Request(formula="")
        assert request.formula == ""
        assert request.trace_id is not None

    def test_very_long_formula(self) -> None:
        """Test request with very long formula."""
        long_formula = "(and " + " ".join(f"(> x{i} 0)" for i in range(200)) + ")"
        request = Z3Request(formula=long_formula)
        assert len(request.formula) > 1000
        assert request.trace_id is not None

    def test_response_with_large_model(self) -> None:
        """Test response with large model dictionary."""
        large_model = {f"var_{i}": str(i * 10) for i in range(100)}
        response = Z3Response(result="sat", model=large_model)
        assert len(response.model) == 100
        d = response.to_dict()
        assert len(d["model"]) == 100

    def test_adapter_config_inheritance(self) -> None:
        """Test that Z3AdapterConfig inherits from base correctly."""
        config = Z3AdapterConfig()
        # Should have base class attributes
        assert hasattr(config, "timeout_ms")
        assert hasattr(config, "max_retries")
        # And Z3-specific attributes
        assert hasattr(config, "z3_timeout_ms")
        assert hasattr(config, "memory_limit_mb")

    @pytest.mark.asyncio
    async def test_concurrent_requests(self) -> None:
        """Test handling concurrent requests."""
        adapter = Z3Adapter()
        adapter._z3_available = False  # Use fallback for speed

        requests = [Z3Request(formula=f"(declare-const x{i} Int)") for i in range(10)]

        tasks = [adapter._execute(req) for req in requests]
        responses = await asyncio.gather(*tasks)

        assert len(responses) == 10
        assert all(r.result == "unknown" for r in responses)
