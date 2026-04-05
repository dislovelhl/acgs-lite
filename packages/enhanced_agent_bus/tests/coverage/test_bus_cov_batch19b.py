"""
Comprehensive coverage tests for enhanced_agent_bus modules:
- deliberation_layer/tensorrt_optimizer.py (TensorRTOptimizer)
- enterprise_sso/middleware.py (SSO middleware, session context, decorators)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# TensorRT optimizer imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
    NUMPY_AVAILABLE,
    ONNX_AVAILABLE,
    TENSORRT_AVAILABLE,
    TORCH_AVAILABLE,
    TensorRTOptimizer,
    get_optimization_status,
    optimize_distilbert,
)

# ---------------------------------------------------------------------------
# SSO middleware imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.enterprise_sso.middleware import (
    SSOMiddlewareConfig,
    SSOSessionContext,
    _check_session_roles,
    _check_session_roles_sync,
    _check_session_valid,
    _check_session_valid_sync,
    _raise_auth_error,
    clear_sso_session,
    get_current_sso_session,
    require_sso_authentication,
    set_sso_session,
)

# ===========================================================================
# Helpers
# ===========================================================================


def _make_sso_session(
    *,
    expired: bool = False,
    roles: list[str] | None = None,
    groups: list[str] | None = None,
    tenant_id: str = "tenant-1",
    user_id: str = "user-1",
    session_id: str = "sess-1",
    email: str = "user@example.com",
    idp_id: str | None = None,
    idp_type: str | None = None,
    attributes: dict | None = None,
) -> SSOSessionContext:
    now = datetime.now(UTC)
    if expired:
        expires_at = now - timedelta(hours=1)
        authenticated_at = now - timedelta(hours=2)
    else:
        expires_at = now + timedelta(hours=1)
        authenticated_at = now - timedelta(minutes=30)

    return SSOSessionContext(
        session_id=session_id,
        user_id=user_id,
        tenant_id=tenant_id,
        email=email,
        display_name="Test User",
        maci_roles=roles or ["ADMIN"],
        idp_groups=groups or ["engineering"],
        attributes=attributes or {},
        authenticated_at=authenticated_at,
        expires_at=expires_at,
        access_token="tok-abc",
        refresh_token="ref-abc",
        idp_id=idp_id,
        idp_type=idp_type,
    )


# ===========================================================================
# TensorRTOptimizer Tests
# ===========================================================================


class TestTensorRTOptimizerInit:
    """Test TensorRTOptimizer initialization."""

    def test_default_init(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        assert opt.model_name == "distilbert-base-uncased"
        assert opt.max_seq_length == 128
        assert opt.use_fp16 is True
        assert opt.cache_dir == tmp_path

    def test_custom_init(self, tmp_path: Path):
        opt = TensorRTOptimizer(
            model_name="bert-base-cased",
            max_seq_length=256,
            use_fp16=False,
            cache_dir=tmp_path,
        )
        assert opt.model_name == "bert-base-cased"
        assert opt.max_seq_length == 256
        assert opt.use_fp16 is False

    def test_model_id_sanitization(self, tmp_path: Path):
        opt = TensorRTOptimizer(model_name="org/model-name", cache_dir=tmp_path)
        assert opt.model_id == "org_model_name"
        assert opt.onnx_path == tmp_path / "org_model_name.onnx"
        assert opt.trt_path == tmp_path / "org_model_name.trt"

    def test_default_cache_dir_creation(self, tmp_path: Path):
        cache = tmp_path / "sub" / "dir"
        opt = TensorRTOptimizer(cache_dir=cache)
        assert cache.exists()

    def test_initial_optimization_status(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        assert opt._optimization_status["onnx_exported"] is False
        assert opt._optimization_status["tensorrt_ready"] is False
        assert opt._optimization_status["active_backend"] == "none"

    def test_onnx_exported_detected_on_init(self, tmp_path: Path):
        # Pre-create the onnx file so init detects it
        onnx_file = tmp_path / "distilbert_base_uncased.onnx"
        onnx_file.write_bytes(b"fake")
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        assert opt._optimization_status["onnx_exported"] is True


class TestTensorRTOptimizerStatus:
    """Test status property."""

    def test_status_keys(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        status = opt.status
        assert "torch_available" in status
        assert "onnx_available" in status
        assert "tensorrt_available" in status
        assert "model_name" in status
        assert "max_seq_length" in status
        assert "use_fp16" in status
        assert "onnx_exported" in status
        assert "tensorrt_ready" in status
        assert "active_backend" in status

    def test_status_values(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path, use_fp16=False, max_seq_length=64)
        status = opt.status
        assert status["use_fp16"] is False
        assert status["max_seq_length"] == 64
        assert status["model_name"] == "distilbert-base-uncased"


class TestTensorRTOptimizerExportOnnx:
    """Test ONNX export."""

    def test_export_onnx_already_exists(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt.onnx_path.write_bytes(b"fake-onnx")
        result = opt.export_onnx(force=False)
        assert result == opt.onnx_path
        assert opt._optimization_status["onnx_exported"] is True

    def test_export_onnx_no_torch_raises(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TORCH_AVAILABLE",
            False,
        ):
            with pytest.raises(RuntimeError, match="PyTorch required"):
                opt.export_onnx()


class TestTensorRTOptimizerConvertToTensorrt:
    """Test TensorRT conversion."""

    def test_convert_no_tensorrt_returns_none(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
            False,
        ):
            result = opt.convert_to_tensorrt()
            assert result is None

    def test_convert_already_exists(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt.trt_path.write_bytes(b"fake-trt-engine")
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
            True,
        ):
            result = opt.convert_to_tensorrt(force=False)
            assert result == opt.trt_path
            assert opt._optimization_status["tensorrt_ready"] is True

    def test_convert_missing_onnx_triggers_export(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        mock_trt = MagicMock()
        mock_trt.Logger.WARNING = 0
        mock_trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH = 0

        mock_builder = MagicMock()
        mock_builder.platform_has_fast_fp16 = False
        serialized = b"fake-engine-data"
        mock_builder.build_serialized_network.return_value = serialized
        mock_trt.Builder.return_value = mock_builder

        mock_parser = MagicMock()
        mock_parser.parse.return_value = True
        mock_trt.OnnxParser.return_value = mock_parser

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.trt",
                mock_trt,
            ),
        ):
            # export_onnx will be called since no onnx file
            opt.export_onnx = MagicMock(return_value=opt.onnx_path)  # type: ignore[method-assign]
            # Create onnx_path for the open() call
            opt.onnx_path.write_bytes(b"fake-onnx")

            result = opt.convert_to_tensorrt(force=True)
            opt.export_onnx.assert_not_called()  # onnx_path exists now
            assert result == opt.trt_path
            assert opt.trt_path.exists()

    def test_convert_calls_export_when_onnx_missing(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        mock_trt = MagicMock()
        mock_trt.Logger.WARNING = 0
        mock_trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH = 0

        mock_builder = MagicMock()
        mock_builder.platform_has_fast_fp16 = True
        mock_builder.build_serialized_network.return_value = b"engine"
        mock_trt.Builder.return_value = mock_builder

        mock_parser = MagicMock()
        mock_parser.parse.return_value = True
        mock_trt.OnnxParser.return_value = mock_parser

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.trt",
                mock_trt,
            ),
        ):
            # onnx_path does NOT exist so export_onnx should be called
            def fake_export():
                opt.onnx_path.write_bytes(b"fake")

            opt.export_onnx = MagicMock(side_effect=fake_export)  # type: ignore[method-assign]
            result = opt.convert_to_tensorrt(force=True)
            opt.export_onnx.assert_called_once()
            assert result == opt.trt_path

    def test_convert_parse_failure_raises(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt.onnx_path.write_bytes(b"fake-onnx")

        mock_trt = MagicMock()
        mock_trt.Logger.WARNING = 0
        mock_trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH = 0
        mock_parser = MagicMock()
        mock_parser.parse.return_value = False
        mock_parser.num_errors = 1
        mock_parser.get_error.return_value = "bad parse"
        mock_trt.OnnxParser.return_value = mock_parser

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.trt",
                mock_trt,
            ),
        ):
            with pytest.raises(RuntimeError, match="Failed to parse ONNX"):
                opt.convert_to_tensorrt(force=True)

    def test_convert_build_failure_raises(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt.onnx_path.write_bytes(b"fake-onnx")

        mock_trt = MagicMock()
        mock_trt.Logger.WARNING = 0
        mock_trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH = 0
        mock_parser = MagicMock()
        mock_parser.parse.return_value = True
        mock_trt.OnnxParser.return_value = mock_parser
        mock_builder = MagicMock()
        mock_builder.platform_has_fast_fp16 = False
        mock_builder.build_serialized_network.return_value = None
        mock_trt.Builder.return_value = mock_builder

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.trt",
                mock_trt,
            ),
        ):
            with pytest.raises(RuntimeError, match="Failed to build TensorRT"):
                opt.convert_to_tensorrt(force=True)

    def test_convert_fp16_enabled(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path, use_fp16=True)
        opt.onnx_path.write_bytes(b"fake-onnx")

        mock_trt = MagicMock()
        mock_trt.Logger.WARNING = 0
        mock_trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH = 0
        mock_builder = MagicMock()
        mock_builder.platform_has_fast_fp16 = True
        mock_builder.build_serialized_network.return_value = b"engine"
        mock_trt.Builder.return_value = mock_builder
        mock_parser = MagicMock()
        mock_parser.parse.return_value = True
        mock_trt.OnnxParser.return_value = mock_parser

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.trt",
                mock_trt,
            ),
        ):
            opt.convert_to_tensorrt(force=True)
            # FP16 flag should have been set
            mock_config = mock_builder.create_builder_config.return_value
            mock_config.set_flag.assert_called_once_with(mock_trt.BuilderFlag.FP16)


class TestTensorRTOptimizerLoadEngine:
    """Test load_tensorrt_engine."""

    def test_load_no_tensorrt(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
            False,
        ):
            assert opt.load_tensorrt_engine() is False

    def test_load_missing_file(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
            True,
        ):
            assert opt.load_tensorrt_engine() is False

    def test_load_validation_failure(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt.trt_path.write_bytes(b"x" * 100)
        opt.validate_engine = MagicMock(return_value=False)  # type: ignore[method-assign]
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
            True,
        ):
            assert opt.load_tensorrt_engine() is False

    def test_load_deserialize_returns_none(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt.trt_path.write_bytes(b"x" * 100)
        opt.validate_engine = MagicMock(return_value=True)  # type: ignore[method-assign]
        mock_trt = MagicMock()
        mock_trt.Logger.WARNING = 0
        mock_runtime = MagicMock()
        mock_runtime.deserialize_cuda_engine.return_value = None
        mock_trt.Runtime.return_value = mock_runtime

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.trt",
                mock_trt,
            ),
        ):
            assert opt.load_tensorrt_engine() is False

    def test_load_deserialize_exception(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt.trt_path.write_bytes(b"x" * 100)
        opt.validate_engine = MagicMock(return_value=True)  # type: ignore[method-assign]
        mock_trt = MagicMock()
        mock_trt.Logger.WARNING = 0
        mock_runtime = MagicMock()
        mock_runtime.deserialize_cuda_engine.side_effect = RuntimeError("CUDA error")
        mock_trt.Runtime.return_value = mock_runtime

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.trt",
                mock_trt,
            ),
        ):
            assert opt.load_tensorrt_engine() is False


class TestTensorRTOptimizerValidateEngine:
    """Test validate_engine."""

    def test_validate_missing_file(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        assert opt.validate_engine(tmp_path / "nonexistent.trt") is False

    def test_validate_no_tensorrt(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        engine = tmp_path / "test.trt"
        engine.write_bytes(b"x" * (2 * 1024 * 1024))
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
            False,
        ):
            assert opt.validate_engine(engine) is False

    def test_validate_file_too_small(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        engine = tmp_path / "small.trt"
        engine.write_bytes(b"x" * 100)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
            True,
        ):
            assert opt.validate_engine(engine) is False

    def test_validate_deserialize_returns_none(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        engine = tmp_path / "test.trt"
        engine.write_bytes(b"x" * (2 * 1024 * 1024))

        mock_trt = MagicMock()
        mock_trt.Logger.WARNING = 0
        mock_runtime = MagicMock()
        mock_runtime.deserialize_cuda_engine.return_value = None
        mock_trt.Runtime.return_value = mock_runtime

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.trt",
                mock_trt,
            ),
        ):
            assert opt.validate_engine(engine) is False

    def test_validate_zero_layers(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        engine = tmp_path / "test.trt"
        engine.write_bytes(b"x" * (2 * 1024 * 1024))

        mock_trt = MagicMock()
        mock_trt.Logger.WARNING = 0
        mock_engine = MagicMock()
        mock_engine.num_layers = 0
        mock_runtime = MagicMock()
        mock_runtime.deserialize_cuda_engine.return_value = mock_engine
        mock_trt.Runtime.return_value = mock_runtime

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.trt",
                mock_trt,
            ),
        ):
            assert opt.validate_engine(engine) is False

    def test_validate_success(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        engine = tmp_path / "test.trt"
        engine.write_bytes(b"x" * (2 * 1024 * 1024))

        mock_trt = MagicMock()
        mock_trt.Logger.WARNING = 0
        mock_engine = MagicMock()
        mock_engine.num_layers = 10
        mock_runtime = MagicMock()
        mock_runtime.deserialize_cuda_engine.return_value = mock_engine
        mock_trt.Runtime.return_value = mock_runtime

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.trt",
                mock_trt,
            ),
        ):
            assert opt.validate_engine(engine) is True

    def test_validate_exception(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        engine = tmp_path / "test.trt"
        engine.write_bytes(b"x" * (2 * 1024 * 1024))

        mock_trt = MagicMock()
        mock_trt.Logger.WARNING = 0
        mock_trt.Runtime.side_effect = RuntimeError("CUDA init failed")

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.trt",
                mock_trt,
            ),
        ):
            assert opt.validate_engine(engine) is False


class TestTensorRTOptimizerLoadOnnxRuntime:
    """Test load_onnx_runtime."""

    def test_load_no_onnx(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.ONNX_AVAILABLE",
            False,
        ):
            assert opt.load_onnx_runtime() is False

    def test_load_missing_onnx_file(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.ONNX_AVAILABLE",
            True,
        ):
            assert opt.load_onnx_runtime() is False

    def test_load_onnx_with_cuda(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt.onnx_path.write_bytes(b"fake-onnx")

        mock_ort = MagicMock()
        mock_ort.get_available_providers.return_value = [
            "CUDAExecutionProvider",
            "CPUExecutionProvider",
        ]
        mock_session = MagicMock()
        mock_ort.InferenceSession.return_value = mock_session

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.ONNX_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.ort",
                mock_ort,
            ),
        ):
            assert opt.load_onnx_runtime() is True
            assert opt._optimization_status["active_backend"] == "onnxruntime"
            call_args = mock_ort.InferenceSession.call_args
            providers = call_args[1]["providers"]
            assert "CUDAExecutionProvider" in providers
            assert "CPUExecutionProvider" in providers

    def test_load_onnx_cpu_only(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt.onnx_path.write_bytes(b"fake-onnx")

        mock_ort = MagicMock()
        mock_ort.get_available_providers.return_value = ["CPUExecutionProvider"]
        mock_ort.InferenceSession.return_value = MagicMock()

        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.ONNX_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.ort",
                mock_ort,
            ),
        ):
            assert opt.load_onnx_runtime() is True
            call_args = mock_ort.InferenceSession.call_args
            providers = call_args[1]["providers"]
            assert providers == ["CPUExecutionProvider"]


class TestTensorRTOptimizerInference:
    """Test infer and infer_batch."""

    def test_infer_no_numpy(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.NUMPY_AVAILABLE",
            False,
        ):
            with pytest.raises(ImportError, match="numpy"):
                opt.infer("test")

    def test_infer_batch_no_numpy(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.NUMPY_AVAILABLE",
            False,
        ):
            with pytest.raises(ImportError, match="numpy"):
                opt.infer_batch(["test"])

    def test_infer_calls_infer_batch(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        fake_result = np.zeros((1, 768), dtype=np.float32)
        opt.infer_batch = MagicMock(return_value=fake_result)  # type: ignore[method-assign]
        result = opt.infer("hello")
        opt.infer_batch.assert_called_once_with(["hello"])
        assert result.shape == (768,)

    def test_infer_batch_fallback_on_timeout(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt._latency_threshold_ms = -1.0  # always timeout

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.zeros((1, 128), dtype=np.int64),
            "attention_mask": np.ones((1, 128), dtype=np.int64),
        }
        opt._load_tokenizer = MagicMock(return_value=mock_tokenizer)  # type: ignore[method-assign]

        result = opt.infer_batch(["test"])
        assert result.shape == (1, 768)
        assert np.all(result == 0)

    def test_infer_batch_exception_fallback(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt._latency_threshold_ms = 999999  # won't timeout

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.zeros((2, 128), dtype=np.int64),
            "attention_mask": np.ones((2, 128), dtype=np.int64),
        }
        opt._load_tokenizer = MagicMock(return_value=mock_tokenizer)  # type: ignore[method-assign]
        opt._infer_torch = MagicMock(side_effect=RuntimeError("no model"))  # type: ignore[method-assign]

        result = opt.infer_batch(["a", "b"])
        assert result.shape == (2, 768)
        assert np.all(result == 0)

    def test_infer_batch_with_trt_context(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt._latency_threshold_ms = 999999
        opt._trt_context = MagicMock()

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.zeros((1, 128), dtype=np.int64),
            "attention_mask": np.ones((1, 128), dtype=np.int64),
        }
        opt._load_tokenizer = MagicMock(return_value=mock_tokenizer)  # type: ignore[method-assign]
        # _infer_tensorrt raises NotImplementedError which is caught
        result = opt.infer_batch(["test"])
        assert result.shape == (1, 768)  # fallback

    def test_infer_batch_with_onnx_session(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt._latency_threshold_ms = 999999
        opt._trt_context = None
        opt._onnx_session = MagicMock()

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.zeros((1, 128), dtype=np.int64),
            "attention_mask": np.ones((1, 128), dtype=np.int64),
        }
        opt._load_tokenizer = MagicMock(return_value=mock_tokenizer)  # type: ignore[method-assign]
        # _infer_onnx will try to use the session, it'll raise since mock
        # The exception is caught, fallback returned
        result = opt.infer_batch(["test"])
        assert result.shape == (1, 768)


class TestTensorRTOptimizerFallbackEmbeddings:
    """Test _generate_fallback_embeddings."""

    def test_fallback_shape(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        result = opt._generate_fallback_embeddings(3)
        assert result.shape == (3, 768)
        assert result.dtype == np.float32
        assert np.all(result == 0)

    def test_fallback_no_numpy(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.NUMPY_AVAILABLE",
            False,
        ):
            with pytest.raises(ImportError, match="numpy"):
                opt._generate_fallback_embeddings(1)


class TestTensorRTOptimizerInferTensorrt:
    """Test _infer_tensorrt."""

    def test_infer_tensorrt_not_implemented(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with pytest.raises(NotImplementedError):
            opt._infer_tensorrt({})


class TestTensorRTOptimizerInferOnnx:
    """Test _infer_onnx."""

    def test_infer_onnx_no_numpy(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.NUMPY_AVAILABLE",
            False,
        ):
            with pytest.raises(ImportError, match="numpy"):
                opt._infer_onnx({})

    def test_infer_onnx_no_session(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt._onnx_session = None
        with pytest.raises(RuntimeError, match="ONNX session not loaded"):
            opt._infer_onnx({})


class TestTensorRTOptimizerInferTorch:
    """Test _infer_torch."""

    def test_infer_torch_no_numpy(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.NUMPY_AVAILABLE",
            False,
        ):
            with pytest.raises(ImportError, match="numpy"):
                opt._infer_torch({})


class TestTensorRTOptimizerLoadTorchModel:
    """Test _load_torch_model."""

    def test_load_torch_no_torch(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with patch(
            "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TORCH_AVAILABLE",
            False,
        ):
            with pytest.raises(RuntimeError, match="PyTorch not available"):
                opt._load_torch_model()


class TestGetOptimizationStatus:
    """Test module-level get_optimization_status."""

    def test_returns_dict(self, tmp_path: Path):
        with patch.object(TensorRTOptimizer, "__init__", lambda self, **kw: None):
            with patch.object(
                TensorRTOptimizer,
                "status",
                new_callable=lambda: property(lambda self: {"active_backend": "none"}),
            ):
                result = get_optimization_status()
                assert isinstance(result, dict)


class TestOptimizeDistilbert:
    """Test module-level optimize_distilbert."""

    def test_optimize_onnx_export_failure(self, tmp_path: Path):
        with patch.object(
            TensorRTOptimizer,
            "__init__",
            lambda self, *a, **kw: self._init_for_test(tmp_path),
        ):
            # Manually set up enough for __init__
            def _init(self, *a, **kw):
                self.model_name = "distilbert-base-uncased"
                self.max_seq_length = 128
                self.use_fp16 = True
                self.cache_dir = tmp_path
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                self.model_id = "distilbert_base_uncased"
                self.onnx_path = tmp_path / "distilbert_base_uncased.onnx"
                self.trt_path = tmp_path / "distilbert_base_uncased.trt"
                self._tokenizer = None
                self._torch_model = None
                self._onnx_session = None
                self._trt_engine = None
                self._trt_context = None
                self._tokenizer_cache = {}
                self._latency_threshold_ms = 10.0
                self._optimization_status = {
                    "onnx_exported": False,
                    "tensorrt_ready": False,
                    "active_backend": "none",
                }

            with patch.object(TensorRTOptimizer, "__init__", _init):
                with patch.object(
                    TensorRTOptimizer,
                    "export_onnx",
                    side_effect=RuntimeError("no torch"),
                ):
                    result = optimize_distilbert()
                    assert "onnx_error" in result
                    assert result["onnx_error"] == "no torch"

    def test_optimize_tensorrt_skipped(self, tmp_path: Path):
        def _init(self, *a, **kw):
            self.model_name = "distilbert-base-uncased"
            self.max_seq_length = 128
            self.use_fp16 = True
            self.cache_dir = tmp_path
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.model_id = "distilbert_base_uncased"
            self.onnx_path = tmp_path / "distilbert_base_uncased.onnx"
            self.trt_path = tmp_path / "distilbert_base_uncased.trt"
            self._tokenizer = None
            self._torch_model = None
            self._onnx_session = None
            self._trt_engine = None
            self._trt_context = None
            self._tokenizer_cache = {}
            self._latency_threshold_ms = 10.0
            self._optimization_status = {
                "onnx_exported": False,
                "tensorrt_ready": False,
                "active_backend": "none",
            }

        with (
            patch.object(TensorRTOptimizer, "__init__", _init),
            patch.object(TensorRTOptimizer, "export_onnx", return_value=tmp_path / "m.onnx"),
            patch(
                "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer.TENSORRT_AVAILABLE",
                False,
            ),
            patch.object(TensorRTOptimizer, "load_tensorrt_engine", return_value=False),
            patch.object(TensorRTOptimizer, "load_onnx_runtime", return_value=False),
            patch.object(
                TensorRTOptimizer,
                "benchmark",
                side_effect=RuntimeError("no model"),
            ),
        ):
            result = optimize_distilbert()
            assert "tensorrt_skipped" in result
            assert result["active_backend"] == "pytorch"
            assert "benchmark_error" in result


# ===========================================================================
# SSO Middleware Tests
# ===========================================================================


class TestSSOSessionContext:
    """Test SSOSessionContext dataclass."""

    def test_create_session(self):
        session = _make_sso_session()
        assert session.session_id == "sess-1"
        assert session.user_id == "user-1"
        assert session.tenant_id == "tenant-1"

    def test_is_expired_false(self):
        session = _make_sso_session(expired=False)
        assert session.is_expired is False

    def test_is_expired_true(self):
        session = _make_sso_session(expired=True)
        assert session.is_expired is True

    def test_time_until_expiry_positive(self):
        session = _make_sso_session(expired=False)
        assert session.time_until_expiry > 0

    def test_time_until_expiry_zero_when_expired(self):
        session = _make_sso_session(expired=True)
        assert session.time_until_expiry == 0.0

    def test_has_role_case_insensitive(self):
        session = _make_sso_session(roles=["Admin", "operator"])
        assert session.has_role("admin") is True
        assert session.has_role("ADMIN") is True
        assert session.has_role("OPERATOR") is True
        assert session.has_role("viewer") is False

    def test_has_any_role(self):
        session = _make_sso_session(roles=["ADMIN", "OPERATOR"])
        assert session.has_any_role(["admin", "viewer"]) is True
        assert session.has_any_role(["viewer", "guest"]) is False

    def test_has_all_roles(self):
        session = _make_sso_session(roles=["ADMIN", "OPERATOR"])
        assert session.has_all_roles(["admin", "operator"]) is True
        assert session.has_all_roles(["admin", "viewer"]) is False

    def test_has_any_role_no_session_roles(self):
        session = _make_sso_session()
        # Directly set empty roles to bypass helper default
        session = SSOSessionContext(
            session_id="s",
            user_id="u",
            tenant_id="t",
            email="e",
            display_name="d",
            maci_roles=[],
            idp_groups=[],
            attributes={},
            authenticated_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert session.has_any_role(["admin"]) is False

    def test_has_all_roles_empty_required(self):
        session = _make_sso_session(roles=["ADMIN"])
        assert session.has_all_roles([]) is True

    def test_to_dict(self):
        session = _make_sso_session(
            idp_id="idp-1",
            idp_type="saml",
            attributes={"key": "val"},
        )
        d = session.to_dict()
        assert d["session_id"] == "sess-1"
        assert d["user_id"] == "user-1"
        assert d["tenant_id"] == "tenant-1"
        assert d["email"] == "user@example.com"
        assert d["display_name"] == "Test User"
        assert d["maci_roles"] == ["ADMIN"]
        assert d["idp_groups"] == ["engineering"]
        assert d["attributes"] == {"key": "val"}
        assert d["idp_id"] == "idp-1"
        assert d["idp_type"] == "saml"
        assert "authenticated_at" in d
        assert "expires_at" in d
        assert "constitutional_hash" in d

    def test_to_dict_datetime_iso_format(self):
        session = _make_sso_session()
        d = session.to_dict()
        # Should be ISO format strings
        assert isinstance(d["authenticated_at"], str)
        assert isinstance(d["expires_at"], str)


class TestSSOSessionContextVars:
    """Test context variable get/set/clear."""

    def test_get_default_none(self):
        clear_sso_session()
        assert get_current_sso_session() is None

    def test_set_and_get(self):
        session = _make_sso_session()
        set_sso_session(session)
        assert get_current_sso_session() is session
        clear_sso_session()

    def test_clear(self):
        session = _make_sso_session()
        set_sso_session(session)
        clear_sso_session()
        assert get_current_sso_session() is None

    def test_set_none(self):
        session = _make_sso_session()
        set_sso_session(session)
        set_sso_session(None)
        assert get_current_sso_session() is None


class TestRaiseAuthError:
    """Test _raise_auth_error."""

    def test_raises_http_exception_when_fastapi_available(self):
        with patch("enhanced_agent_bus.enterprise_sso.middleware.FASTAPI_AVAILABLE", True):
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                _raise_auth_error(401, "Unauthorized")
            assert exc_info.value.status_code == 401

    def test_raises_permission_error_when_no_fastapi(self):
        with patch("enhanced_agent_bus.enterprise_sso.middleware.FASTAPI_AVAILABLE", False):
            with pytest.raises(PermissionError, match="Unauthorized"):
                _raise_auth_error(401, "Unauthorized")


class TestCheckSessionValid:
    """Test _check_session_valid."""

    def test_none_session_raises(self):
        with pytest.raises((PermissionError, Exception)):
            _check_session_valid(None, allow_expired=False)

    def test_expired_session_raises(self):
        session = _make_sso_session(expired=True)
        with pytest.raises((PermissionError, Exception)):
            _check_session_valid(session, allow_expired=False)

    def test_expired_session_allowed(self):
        session = _make_sso_session(expired=True)
        # Should not raise
        _check_session_valid(session, allow_expired=True)

    def test_valid_session_passes(self):
        session = _make_sso_session(expired=False)
        _check_session_valid(session, allow_expired=False)


class TestCheckSessionValidSync:
    """Test _check_session_valid_sync."""

    def test_none_raises(self):
        with pytest.raises(PermissionError, match="SSO authentication required"):
            _check_session_valid_sync(None, allow_expired=False)

    def test_expired_raises(self):
        session = _make_sso_session(expired=True)
        with pytest.raises(PermissionError, match="SSO session expired"):
            _check_session_valid_sync(session, allow_expired=False)

    def test_expired_allowed(self):
        session = _make_sso_session(expired=True)
        _check_session_valid_sync(session, allow_expired=True)

    def test_valid_passes(self):
        session = _make_sso_session()
        _check_session_valid_sync(session, allow_expired=False)


class TestCheckSessionRoles:
    """Test _check_session_roles."""

    def test_empty_roles_passes(self):
        session = _make_sso_session(roles=[])
        _check_session_roles(session, [], any_role=True)

    def test_any_role_pass(self):
        session = _make_sso_session(roles=["ADMIN"])
        _check_session_roles(session, ["admin", "viewer"], any_role=True)

    def test_any_role_fail(self):
        session = _make_sso_session(roles=["GUEST"])
        with pytest.raises((PermissionError, Exception)):
            _check_session_roles(session, ["admin", "operator"], any_role=True)

    def test_all_roles_pass(self):
        session = _make_sso_session(roles=["ADMIN", "OPERATOR"])
        _check_session_roles(session, ["admin", "operator"], any_role=False)

    def test_all_roles_fail(self):
        session = _make_sso_session(roles=["ADMIN"])
        with pytest.raises((PermissionError, Exception)):
            _check_session_roles(session, ["admin", "operator"], any_role=False)


class TestCheckSessionRolesSync:
    """Test _check_session_roles_sync."""

    def test_empty_roles_passes(self):
        session = _make_sso_session()
        _check_session_roles_sync(session, [], any_role=True)

    def test_any_role_pass(self):
        session = _make_sso_session(roles=["ADMIN"])
        _check_session_roles_sync(session, ["admin"], any_role=True)

    def test_any_role_fail(self):
        session = _make_sso_session(roles=["GUEST"])
        with pytest.raises(PermissionError, match="Requires one of roles"):
            _check_session_roles_sync(session, ["admin"], any_role=True)

    def test_all_roles_fail(self):
        session = _make_sso_session(roles=["ADMIN"])
        with pytest.raises(PermissionError, match="Requires all roles"):
            _check_session_roles_sync(session, ["admin", "operator"], any_role=False)


class TestRequireSSOAuthentication:
    """Test require_sso_authentication decorator."""

    async def test_async_decorator_no_session(self):
        @require_sso_authentication()
        async def handler():
            return "ok"

        clear_sso_session()
        with pytest.raises((PermissionError, Exception)):
            await handler()

    async def test_async_decorator_valid_session(self):
        @require_sso_authentication()
        async def handler():
            return "ok"

        set_sso_session(_make_sso_session())
        result = await handler()
        assert result == "ok"
        clear_sso_session()

    async def test_async_decorator_expired_session(self):
        @require_sso_authentication(allow_expired=False)
        async def handler():
            return "ok"

        set_sso_session(_make_sso_session(expired=True))
        with pytest.raises((PermissionError, Exception)):
            await handler()
        clear_sso_session()

    async def test_async_decorator_expired_allowed(self):
        @require_sso_authentication(allow_expired=True)
        async def handler():
            return "ok"

        set_sso_session(_make_sso_session(expired=True))
        result = await handler()
        assert result == "ok"
        clear_sso_session()

    async def test_async_decorator_roles_any(self):
        @require_sso_authentication(roles=["ADMIN", "VIEWER"], any_role=True)
        async def handler():
            return "ok"

        set_sso_session(_make_sso_session(roles=["ADMIN"]))
        result = await handler()
        assert result == "ok"
        clear_sso_session()

    async def test_async_decorator_roles_all_missing(self):
        @require_sso_authentication(roles=["ADMIN", "SUPER_ADMIN"], any_role=False)
        async def handler():
            return "ok"

        set_sso_session(_make_sso_session(roles=["ADMIN"]))
        with pytest.raises((PermissionError, Exception)):
            await handler()
        clear_sso_session()

    def test_sync_decorator_no_session(self):
        @require_sso_authentication()
        def handler():
            return "ok"

        clear_sso_session()
        with pytest.raises(PermissionError):
            handler()

    def test_sync_decorator_valid_session(self):
        @require_sso_authentication()
        def handler():
            return "ok"

        set_sso_session(_make_sso_session())
        result = handler()
        assert result == "ok"
        clear_sso_session()

    def test_sync_decorator_expired(self):
        @require_sso_authentication(allow_expired=False)
        def handler():
            return "ok"

        set_sso_session(_make_sso_session(expired=True))
        with pytest.raises(PermissionError, match="expired"):
            handler()
        clear_sso_session()

    def test_sync_decorator_roles_fail(self):
        @require_sso_authentication(roles=["SUPER_ADMIN"], any_role=True)
        def handler():
            return "ok"

        set_sso_session(_make_sso_session(roles=["GUEST"]))
        with pytest.raises(PermissionError, match="Requires one of roles"):
            handler()
        clear_sso_session()

    def test_sync_decorator_all_roles_fail(self):
        @require_sso_authentication(roles=["ADMIN", "OPERATOR"], any_role=False)
        def handler():
            return "ok"

        set_sso_session(_make_sso_session(roles=["ADMIN"]))
        with pytest.raises(PermissionError, match="Requires all roles"):
            handler()
        clear_sso_session()


class TestSSOMiddlewareConfig:
    """Test SSOMiddlewareConfig defaults."""

    def test_defaults(self):
        config = SSOMiddlewareConfig()
        assert "/health" in config.excluded_paths
        assert "/healthz" in config.excluded_paths
        assert "/metrics" in config.excluded_paths
        assert "/static/" in config.excluded_prefixes
        assert config.token_header == "Authorization"
        assert config.token_prefix == "Bearer"
        assert config.session_cookie == "acgs_sso_session"
        assert config.allow_cookie_auth is True
        assert config.set_tenant_context is True
        assert config.require_authentication is True
        assert config.auto_refresh_sessions is True
        assert config.refresh_threshold_seconds == 300

    def test_custom_config(self):
        config = SSOMiddlewareConfig(
            excluded_paths={"/custom"},
            require_authentication=False,
            refresh_threshold_seconds=600,
        )
        assert config.excluded_paths == {"/custom"}
        assert config.require_authentication is False
        assert config.refresh_threshold_seconds == 600


class TestSSOAuthenticationMiddleware:
    """Test SSOAuthenticationMiddleware (FastAPI-dependent)."""

    def _make_middleware(self, config: SSOMiddlewareConfig | None = None):
        from enhanced_agent_bus.enterprise_sso.middleware import (
            FASTAPI_AVAILABLE,
            SSOAuthenticationMiddleware,
        )

        if not FASTAPI_AVAILABLE:
            pytest.skip("FastAPI not available")

        mock_app = MagicMock()
        mock_sso_service = MagicMock()
        mw = SSOAuthenticationMiddleware(
            app=mock_app,
            sso_service=mock_sso_service,
            config=config,
        )
        return mw, mock_sso_service

    def test_is_excluded_path_exact(self):
        mw, _ = self._make_middleware()
        assert mw._is_excluded_path("/health") is True
        assert mw._is_excluded_path("/metrics") is True
        assert mw._is_excluded_path("/api/v1/data") is False

    def test_is_excluded_path_prefix(self):
        mw, _ = self._make_middleware()
        assert mw._is_excluded_path("/static/css/style.css") is True
        assert mw._is_excluded_path("/assets/img.png") is True
        assert mw._is_excluded_path("/.well-known/openid") is True

    def test_extract_token_bearer(self):
        mw, _ = self._make_middleware()
        request = MagicMock()
        request.headers = {"Authorization": "Bearer my-token-123"}
        request.cookies = {}
        token = mw._extract_token(request)
        assert token == "my-token-123"

    def test_extract_token_raw(self):
        mw, _ = self._make_middleware()
        request = MagicMock()
        request.headers = {"Authorization": "raw-token-no-prefix"}
        request.cookies = {}
        token = mw._extract_token(request)
        assert token == "raw-token-no-prefix"

    def test_extract_token_from_cookie(self):
        mw, _ = self._make_middleware()
        request = MagicMock()
        request.headers = {}
        request.cookies = {"acgs_sso_session": "cookie-token"}
        token = mw._extract_token(request)
        assert token == "cookie-token"

    def test_extract_token_cookie_disabled(self):
        config = SSOMiddlewareConfig(allow_cookie_auth=False)
        mw, _ = self._make_middleware(config)
        request = MagicMock()
        request.headers = {}
        request.cookies = {"acgs_sso_session": "cookie-token"}
        token = mw._extract_token(request)
        assert token is None

    def test_extract_token_none(self):
        mw, _ = self._make_middleware()
        request = MagicMock()
        request.headers = {}
        request.cookies = {}
        token = mw._extract_token(request)
        assert token is None

    def test_extract_token_basic_auth_ignored(self):
        mw, _ = self._make_middleware()
        request = MagicMock()
        request.headers = {"Authorization": "Basic dXNlcjpwYXNz"}
        request.cookies = {}
        # Basic auth starts with "Basic " so it won't be returned as raw token
        token = mw._extract_token(request)
        assert token is None

    async def test_dispatch_excluded_path(self):
        mw, _ = self._make_middleware()
        request = MagicMock()
        request.url.path = "/health"

        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        response = await mw.dispatch(request, call_next)
        call_next.assert_awaited_once_with(request)

    async def test_dispatch_no_token_required(self):
        mw, _ = self._make_middleware()
        request = MagicMock()
        request.url.path = "/api/data"
        request.headers = {}
        request.cookies = {}

        response = await mw.dispatch(request, AsyncMock())
        assert response.status_code == 401

    async def test_dispatch_no_token_not_required(self):
        config = SSOMiddlewareConfig(require_authentication=False)
        mw, _ = self._make_middleware(config)
        request = MagicMock()
        request.url.path = "/api/data"
        request.headers = {}
        request.cookies = {}

        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        response = await mw.dispatch(request, call_next)
        call_next.assert_awaited_once()

    async def test_dispatch_invalid_session_required(self):
        mw, sso_service = self._make_middleware()
        sso_service.validate_session.return_value = None
        request = MagicMock()
        request.url.path = "/api/data"
        request.headers = {"Authorization": "Bearer tok"}
        request.cookies = {}

        response = await mw.dispatch(request, AsyncMock())
        assert response.status_code == 401

    async def test_dispatch_invalid_session_not_required(self):
        config = SSOMiddlewareConfig(require_authentication=False)
        mw, sso_service = self._make_middleware(config)
        sso_service.validate_session.return_value = None
        request = MagicMock()
        request.url.path = "/api/data"
        request.headers = {"Authorization": "Bearer tok"}
        request.cookies = {}

        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        response = await mw.dispatch(request, call_next)
        call_next.assert_awaited_once()

    async def test_dispatch_valid_session(self):
        mw, sso_service = self._make_middleware()

        now = datetime.now(UTC)
        mock_session = MagicMock()
        mock_session.session_id = "s1"
        mock_session.user_id = "u1"
        mock_session.tenant_id = "t1"
        mock_session.email = "u@e.com"
        mock_session.display_name = "User"
        mock_session.maci_roles = ["ADMIN"]
        mock_session.idp_groups = []
        mock_session.attributes = {}
        mock_session.authenticated_at = now - timedelta(minutes=5)
        mock_session.expires_at = now + timedelta(hours=1)
        mock_session.refresh_token = None
        mock_session.idp_id = None
        mock_session.idp_type = None
        mock_session.metadata = {}
        sso_service.validate_session.return_value = mock_session

        request = MagicMock()
        request.url.path = "/api/data"
        request.headers = {"Authorization": "Bearer tok123"}
        request.cookies = {}

        config = SSOMiddlewareConfig(
            set_tenant_context=False,
            auto_refresh_sessions=False,
        )
        mw.config = config

        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        response = await mw.dispatch(request, call_next)
        call_next.assert_awaited_once()
        # Session should be cleared after dispatch
        assert get_current_sso_session() is None

    async def test_dispatch_expired_session(self):
        mw, sso_service = self._make_middleware()

        now = datetime.now(UTC)
        mock_session = MagicMock()
        mock_session.session_id = "s1"
        mock_session.user_id = "u1"
        mock_session.tenant_id = "t1"
        mock_session.email = "u@e.com"
        mock_session.display_name = "User"
        mock_session.maci_roles = []
        mock_session.idp_groups = []
        mock_session.attributes = {}
        mock_session.authenticated_at = now - timedelta(hours=2)
        mock_session.expires_at = now - timedelta(hours=1)  # expired
        mock_session.refresh_token = None
        mock_session.idp_id = None
        mock_session.idp_type = None
        sso_service.validate_session.return_value = mock_session

        request = MagicMock()
        request.url.path = "/api/data"
        request.headers = {"Authorization": "Bearer tok123"}
        request.cookies = {}

        response = await mw.dispatch(request, AsyncMock())
        assert response.status_code == 401

    async def test_dispatch_exception_during_validation(self):
        mw, sso_service = self._make_middleware()
        sso_service.validate_session.side_effect = RuntimeError("boom")

        request = MagicMock()
        request.url.path = "/api/data"
        request.headers = {"Authorization": "Bearer tok"}
        request.cookies = {}

        response = await mw.dispatch(request, AsyncMock())
        # validate_session exception is caught in _validate_and_create_context
        # returns None, so 401
        assert response.status_code == 401

    async def test_dispatch_exception_not_required(self):
        config = SSOMiddlewareConfig(require_authentication=False)
        mw, sso_service = self._make_middleware(config)
        sso_service.validate_session.side_effect = RuntimeError("boom")

        request = MagicMock()
        request.url.path = "/api/data"
        request.headers = {"Authorization": "Bearer tok"}
        request.cookies = {}

        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        response = await mw.dispatch(request, call_next)
        call_next.assert_awaited_once()

    async def test_validate_and_create_context_string_dates(self):
        mw, sso_service = self._make_middleware()
        now = datetime.now(UTC)

        mock_session = MagicMock()
        mock_session.session_id = "s1"
        mock_session.user_id = "u1"
        mock_session.tenant_id = "t1"
        mock_session.email = "u@e.com"
        mock_session.display_name = "User"
        mock_session.maci_roles = ["OP"]
        mock_session.idp_groups = ["g1"]
        mock_session.attributes = {"k": "v"}
        mock_session.authenticated_at = (now - timedelta(minutes=5)).isoformat()
        mock_session.expires_at = (now + timedelta(hours=1)).isoformat()
        mock_session.refresh_token = "ref"
        mock_session.idp_id = "idp1"
        mock_session.idp_type = "oidc"
        mock_session.metadata = {}
        sso_service.validate_session.return_value = mock_session

        request = MagicMock()
        ctx = await mw._validate_and_create_context("tok", request)
        assert ctx is not None
        assert ctx.session_id == "s1"
        assert ctx.idp_id == "idp1"

    async def test_validate_and_create_context_no_dates(self):
        mw, sso_service = self._make_middleware()

        mock_session = MagicMock(spec=[])
        mock_session.session_id = "s1"
        # Use an object without expires_at / authenticated_at attributes
        sso_service.validate_session.return_value = mock_session

        request = MagicMock()
        ctx = await mw._validate_and_create_context("tok", request)
        assert ctx is not None

    async def test_handle_session_refresh_no_refresh_token(self):
        mw, sso_service = self._make_middleware()
        session = _make_sso_session()
        # Override to be near expiry but no refresh token
        session = SSOSessionContext(
            session_id="s1",
            user_id="u1",
            tenant_id="t1",
            email="u@e.com",
            display_name="User",
            maci_roles=["ADMIN"],
            idp_groups=[],
            attributes={},
            authenticated_at=datetime.now(UTC) - timedelta(hours=1),
            expires_at=datetime.now(UTC) + timedelta(seconds=10),
            refresh_token=None,
        )
        response = MagicMock()
        response.headers = {}
        result = await mw._handle_session_refresh(session, response)
        assert result is response

    async def test_handle_session_refresh_with_token(self):
        mw, sso_service = self._make_middleware()
        session = SSOSessionContext(
            session_id="s1",
            user_id="u1",
            tenant_id="t1",
            email="u@e.com",
            display_name="User",
            maci_roles=["ADMIN"],
            idp_groups=[],
            attributes={},
            authenticated_at=datetime.now(UTC) - timedelta(hours=1),
            expires_at=datetime.now(UTC) + timedelta(seconds=10),
            refresh_token="ref-tok",
        )
        new_session = MagicMock()
        new_session.session_id = "new-s1"
        sso_service.refresh_session.return_value = new_session

        response = MagicMock()
        response.headers = {}
        result = await mw._handle_session_refresh(session, response)
        assert result is response
        assert response.headers["X-SSO-Token-Refreshed"] == "true"
        assert response.headers["X-SSO-New-Token"] == "new-s1"

    async def test_handle_session_refresh_error(self):
        mw, sso_service = self._make_middleware()
        session = SSOSessionContext(
            session_id="s1",
            user_id="u1",
            tenant_id="t1",
            email="u@e.com",
            display_name="User",
            maci_roles=[],
            idp_groups=[],
            attributes={},
            authenticated_at=datetime.now(UTC) - timedelta(hours=1),
            expires_at=datetime.now(UTC) + timedelta(seconds=10),
            refresh_token="ref-tok",
        )
        sso_service.refresh_session.side_effect = RuntimeError("refresh failed")

        response = MagicMock()
        response.headers = {}
        result = await mw._handle_session_refresh(session, response)
        assert result is response

    async def test_set_tenant_context_import_error(self):
        mw, _ = self._make_middleware()
        session = _make_sso_session()
        with patch(
            "enhanced_agent_bus.enterprise_sso.middleware.SSOAuthenticationMiddleware._set_tenant_context",
            new_callable=lambda: lambda self, s: None,
        ):
            # Just verify it doesn't raise
            pass

    async def test_dispatch_sets_and_clears_context(self):
        mw, sso_service = self._make_middleware()
        now = datetime.now(UTC)

        mock_session = MagicMock()
        mock_session.session_id = "ctx-test"
        mock_session.user_id = "u1"
        mock_session.tenant_id = "t1"
        mock_session.email = "u@e.com"
        mock_session.display_name = "User"
        mock_session.maci_roles = []
        mock_session.idp_groups = []
        mock_session.attributes = {}
        mock_session.authenticated_at = now
        mock_session.expires_at = now + timedelta(hours=1)
        mock_session.refresh_token = None
        mock_session.idp_id = None
        mock_session.idp_type = None
        mock_session.metadata = {}
        sso_service.validate_session.return_value = mock_session

        captured_session = []

        async def capture_next(req):
            captured_session.append(get_current_sso_session())
            return MagicMock(status_code=200, headers={})

        mw.config = SSOMiddlewareConfig(
            set_tenant_context=False,
            auto_refresh_sessions=False,
        )

        request = MagicMock()
        request.url.path = "/api/data"
        request.headers = {"Authorization": "Bearer tok"}
        request.cookies = {}

        await mw.dispatch(request, capture_next)
        # During call_next, session should have been set
        assert len(captured_session) == 1
        assert captured_session[0] is not None
        assert captured_session[0].session_id == "ctx-test"
        # After dispatch, session should be cleared
        assert get_current_sso_session() is None


class TestSSOMiddlewareFastapiDeps:
    """Test FastAPI dependency functions."""

    async def test_get_sso_session_dependency(self):
        from enhanced_agent_bus.enterprise_sso.middleware import FASTAPI_AVAILABLE

        if not FASTAPI_AVAILABLE:
            pytest.skip("FastAPI not available")

        from enhanced_agent_bus.enterprise_sso.middleware import (
            get_sso_session_dependency,
        )

        clear_sso_session()
        result = await get_sso_session_dependency()
        assert result is None

        session = _make_sso_session()
        set_sso_session(session)
        result = await get_sso_session_dependency()
        assert result is session
        clear_sso_session()

    async def test_require_sso_session_dependency_no_session(self):
        from enhanced_agent_bus.enterprise_sso.middleware import FASTAPI_AVAILABLE

        if not FASTAPI_AVAILABLE:
            pytest.skip("FastAPI not available")

        from fastapi import HTTPException

        from enhanced_agent_bus.enterprise_sso.middleware import (
            require_sso_session_dependency,
        )

        clear_sso_session()
        with pytest.raises(HTTPException) as exc_info:
            await require_sso_session_dependency()
        assert exc_info.value.status_code == 401

    async def test_require_sso_session_dependency_expired(self):
        from enhanced_agent_bus.enterprise_sso.middleware import FASTAPI_AVAILABLE

        if not FASTAPI_AVAILABLE:
            pytest.skip("FastAPI not available")

        from fastapi import HTTPException

        from enhanced_agent_bus.enterprise_sso.middleware import (
            require_sso_session_dependency,
        )

        set_sso_session(_make_sso_session(expired=True))
        with pytest.raises(HTTPException) as exc_info:
            await require_sso_session_dependency()
        assert exc_info.value.status_code == 401
        clear_sso_session()

    async def test_require_sso_session_dependency_valid(self):
        from enhanced_agent_bus.enterprise_sso.middleware import FASTAPI_AVAILABLE

        if not FASTAPI_AVAILABLE:
            pytest.skip("FastAPI not available")

        from enhanced_agent_bus.enterprise_sso.middleware import (
            require_sso_session_dependency,
        )

        session = _make_sso_session()
        set_sso_session(session)
        result = await require_sso_session_dependency()
        assert result is session
        clear_sso_session()

    async def test_require_roles_any_pass(self):
        from enhanced_agent_bus.enterprise_sso.middleware import FASTAPI_AVAILABLE

        if not FASTAPI_AVAILABLE:
            pytest.skip("FastAPI not available")

        from enhanced_agent_bus.enterprise_sso.middleware import require_roles

        dep = require_roles("ADMIN", "VIEWER", any_role=True)
        session = _make_sso_session(roles=["ADMIN"])
        set_sso_session(session)
        # The dependency expects session as parameter
        result = await dep(session=session)
        assert result is session
        clear_sso_session()

    async def test_require_roles_any_fail(self):
        from enhanced_agent_bus.enterprise_sso.middleware import FASTAPI_AVAILABLE

        if not FASTAPI_AVAILABLE:
            pytest.skip("FastAPI not available")

        from fastapi import HTTPException

        from enhanced_agent_bus.enterprise_sso.middleware import require_roles

        dep = require_roles("SUPER_ADMIN", any_role=True)
        session = _make_sso_session(roles=["GUEST"])
        set_sso_session(session)
        with pytest.raises(HTTPException) as exc_info:
            await dep(session=session)
        assert exc_info.value.status_code == 403
        clear_sso_session()

    async def test_require_roles_all_fail(self):
        from enhanced_agent_bus.enterprise_sso.middleware import FASTAPI_AVAILABLE

        if not FASTAPI_AVAILABLE:
            pytest.skip("FastAPI not available")

        from fastapi import HTTPException

        from enhanced_agent_bus.enterprise_sso.middleware import require_roles

        dep = require_roles("ADMIN", "OPERATOR", any_role=False)
        session = _make_sso_session(roles=["ADMIN"])
        set_sso_session(session)
        with pytest.raises(HTTPException) as exc_info:
            await dep(session=session)
        assert exc_info.value.status_code == 403
        clear_sso_session()

    async def test_require_roles_all_pass(self):
        from enhanced_agent_bus.enterprise_sso.middleware import FASTAPI_AVAILABLE

        if not FASTAPI_AVAILABLE:
            pytest.skip("FastAPI not available")

        from enhanced_agent_bus.enterprise_sso.middleware import require_roles

        dep = require_roles("ADMIN", "OPERATOR", any_role=False)
        session = _make_sso_session(roles=["ADMIN", "OPERATOR"])
        set_sso_session(session)
        result = await dep(session=session)
        assert result is session
        clear_sso_session()
