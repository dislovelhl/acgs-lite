"""
Coverage tests for:
  - deliberation_layer/tensorrt_optimizer.py
  - multi_tenancy/db_repository_optimized.py

asyncio_mode = "auto" -- no @pytest.mark.asyncio needed.
"""

from __future__ import annotations

import hashlib
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Module path constants
# ---------------------------------------------------------------------------
MOD_TRT = "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer"
MOD_DB = "enhanced_agent_bus.multi_tenancy.db_repository_optimized"


def _get_trt_mod():
    """Get the tensorrt_optimizer module object after first from-import."""
    from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
        TensorRTOptimizer,
    )

    return sys.modules[MOD_TRT]


def _trt_optimizer(tmp_path, **kwargs):
    """Create a TensorRTOptimizer with tmp_path cache dir."""
    from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
        TensorRTOptimizer,
    )

    return TensorRTOptimizer(cache_dir=tmp_path, **kwargs)


# ---------------------------------------------------------------------------
# TensorRT Optimizer Tests
# ---------------------------------------------------------------------------


class TestTensorRTOptimizerInit:
    """Test TensorRTOptimizer __init__ and property methods."""

    def test_init_defaults(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        assert opt.model_name == "distilbert-base-uncased"
        assert opt.max_seq_length == 128
        assert opt.use_fp16 is True
        assert opt.cache_dir == tmp_path
        assert opt._tokenizer is None
        assert opt._torch_model is None

    def test_init_custom_params(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(
            model_name="custom/model",
            max_seq_length=256,
            use_fp16=False,
            cache_dir=tmp_path,
        )
        assert opt.model_name == "custom/model"
        assert opt.max_seq_length == 256
        assert opt.use_fp16 is False
        assert opt.model_id == "custom_model"

    def test_model_paths(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        assert opt.onnx_path == tmp_path / "distilbert_base_uncased.onnx"
        assert opt.trt_path == tmp_path / "distilbert_base_uncased.trt"

    def test_status_property(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        status = opt.status
        assert "torch_available" in status
        assert "onnx_available" in status
        assert "tensorrt_available" in status
        assert status["model_name"] == "distilbert-base-uncased"
        assert status["max_seq_length"] == 128
        assert status["use_fp16"] is True
        assert status["active_backend"] == "none"


class TestTensorRTOptimizerLoadTokenizer:
    """Test _load_tokenizer with caching."""

    def test_load_tokenizer_caches(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        mock_tokenizer = MagicMock()
        mock_cls = MagicMock()
        mock_cls.from_pretrained.return_value = mock_tokenizer

        with patch.dict("sys.modules", {"transformers": MagicMock(AutoTokenizer=mock_cls)}):
            result1 = opt._load_tokenizer()
            result2 = opt._load_tokenizer()
            mock_cls.from_pretrained.assert_called_once()
            assert result1 is result2


class TestTensorRTOptimizerLoadTorchModel:
    """Test _load_torch_model."""

    @patch(f"{MOD_TRT}.TORCH_AVAILABLE", False)
    def test_load_torch_model_no_torch(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        with pytest.raises(RuntimeError, match="PyTorch not available"):
            opt._load_torch_model()

    def test_load_torch_model_with_torch_cpu(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path)

        mock_model = MagicMock()
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False

        saved_torch = mod.torch
        saved_avail = mod.TORCH_AVAILABLE
        try:
            mod.TORCH_AVAILABLE = True
            mod.torch = mock_torch

            with patch.dict(
                "sys.modules",
                {
                    "transformers": MagicMock(
                        AutoModel=MagicMock(from_pretrained=MagicMock(return_value=mock_model))
                    ),
                    "accelerate": MagicMock(),
                },
            ):
                result = opt._load_torch_model()
                assert result is mock_model
                mock_model.eval.assert_called_once()
        finally:
            mod.torch = saved_torch
            mod.TORCH_AVAILABLE = saved_avail

    def test_load_torch_model_with_gpu(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path)

        mock_model = MagicMock()
        mock_model.cuda.return_value = mock_model
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True

        saved_torch = mod.torch
        saved_avail = mod.TORCH_AVAILABLE
        try:
            mod.TORCH_AVAILABLE = True
            mod.torch = mock_torch

            with patch.dict(
                "sys.modules",
                {
                    "transformers": MagicMock(
                        AutoModel=MagicMock(from_pretrained=MagicMock(return_value=mock_model))
                    ),
                    "accelerate": MagicMock(),
                },
            ):
                opt._load_torch_model()
                mock_model.cuda.assert_called_once()
        finally:
            mod.torch = saved_torch
            mod.TORCH_AVAILABLE = saved_avail

    def test_load_torch_model_caches(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        sentinel = MagicMock()
        opt._torch_model = sentinel
        result = opt._load_torch_model()
        assert result is sentinel


class TestExportOnnx:
    """Test export_onnx method."""

    def test_export_onnx_already_exists(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        opt.onnx_path.write_text("fake")

        result = opt.export_onnx(force=False)
        assert result == opt.onnx_path
        assert opt._optimization_status["onnx_exported"] is True

    @patch(f"{MOD_TRT}.TORCH_AVAILABLE", False)
    def test_export_onnx_no_torch(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        with pytest.raises(RuntimeError, match="PyTorch required"):
            opt.export_onnx(force=True)

    def test_export_onnx_full_flow(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path)

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": MagicMock(),
            "attention_mask": MagicMock(),
        }
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False

        saved_torch = mod.torch
        saved_avail = mod.TORCH_AVAILABLE
        saved_onnx_avail = mod.ONNX_AVAILABLE
        try:
            mod.TORCH_AVAILABLE = True
            mod.ONNX_AVAILABLE = False
            mod.torch = mock_torch

            opt._load_tokenizer = MagicMock(return_value=mock_tokenizer)
            opt._load_torch_model = MagicMock(return_value=MagicMock())

            result = opt.export_onnx(force=True)
            assert result == opt.onnx_path
            mock_torch.onnx.export.assert_called_once()
            assert opt._optimization_status["onnx_exported"] is True
        finally:
            mod.torch = saved_torch
            mod.TORCH_AVAILABLE = saved_avail
            mod.ONNX_AVAILABLE = saved_onnx_avail

    def test_export_onnx_with_onnx_validation(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path)

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_onnx_mod = MagicMock()

        saved_torch = mod.torch
        saved_avail = mod.TORCH_AVAILABLE
        saved_onnx_avail = mod.ONNX_AVAILABLE
        try:
            mod.TORCH_AVAILABLE = True
            mod.ONNX_AVAILABLE = True
            mod.torch = mock_torch

            opt._load_tokenizer = MagicMock(
                return_value=MagicMock(
                    return_value={
                        "input_ids": MagicMock(),
                        "attention_mask": MagicMock(),
                    }
                )
            )
            opt._load_torch_model = MagicMock(return_value=MagicMock())

            with patch.dict("sys.modules", {"onnx": mock_onnx_mod}):
                opt.export_onnx(force=True)
                assert opt._optimization_status["onnx_exported"] is True
        finally:
            mod.torch = saved_torch
            mod.TORCH_AVAILABLE = saved_avail
            mod.ONNX_AVAILABLE = saved_onnx_avail

    def test_export_onnx_with_gpu(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path)

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {"input_ids": MagicMock(), "attention_mask": MagicMock()}
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True

        saved_torch = mod.torch
        saved_avail = mod.TORCH_AVAILABLE
        saved_onnx_avail = mod.ONNX_AVAILABLE
        try:
            mod.TORCH_AVAILABLE = True
            mod.ONNX_AVAILABLE = False
            mod.torch = mock_torch

            opt._load_tokenizer = MagicMock(return_value=mock_tokenizer)
            opt._load_torch_model = MagicMock(return_value=MagicMock())

            result = opt.export_onnx(force=True)
            assert result == opt.onnx_path
        finally:
            mod.torch = saved_torch
            mod.TORCH_AVAILABLE = saved_avail
            mod.ONNX_AVAILABLE = saved_onnx_avail


class TestConvertToTensorrt:
    """Test convert_to_tensorrt method."""

    @patch(f"{MOD_TRT}.TENSORRT_AVAILABLE", False)
    def test_no_tensorrt(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        result = opt.convert_to_tensorrt()
        assert result is None

    def test_trt_already_exists(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path)
        opt.trt_path.write_text("fake")

        saved = mod.TENSORRT_AVAILABLE
        try:
            mod.TENSORRT_AVAILABLE = True
            result = opt.convert_to_tensorrt(force=False)
            assert result == opt.trt_path
            assert opt._optimization_status["tensorrt_ready"] is True
        finally:
            mod.TENSORRT_AVAILABLE = saved

    def test_convert_onnx_not_found(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path)

        mock_trt = MagicMock()
        mock_trt.Logger.return_value = MagicMock()
        mock_trt.Logger.WARNING = 2
        mock_trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH = 0
        mock_parser = MagicMock()
        mock_parser.parse.return_value = True
        mock_trt.OnnxParser.return_value = mock_parser
        mock_builder = MagicMock()
        mock_builder.platform_has_fast_fp16 = False
        mock_builder.build_serialized_network.return_value = b"engine_data"
        mock_trt.Builder.return_value = mock_builder

        saved_trt = mod.trt
        saved_avail = mod.TENSORRT_AVAILABLE
        try:
            mod.TENSORRT_AVAILABLE = True
            mod.trt = mock_trt

            def fake_export():
                opt.onnx_path.write_bytes(b"fake_onnx")
                return opt.onnx_path

            opt.export_onnx = fake_export

            result = opt.convert_to_tensorrt(force=True)
            assert result == opt.trt_path
        finally:
            mod.trt = saved_trt
            mod.TENSORRT_AVAILABLE = saved_avail

    def test_convert_parse_failure(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path)
        opt.onnx_path.write_bytes(b"fake")

        mock_trt = MagicMock()
        mock_trt.Logger.return_value = MagicMock()
        mock_trt.Logger.WARNING = 2
        mock_trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH = 0
        mock_parser = MagicMock()
        mock_parser.parse.return_value = False
        mock_parser.num_errors = 1
        mock_parser.get_error.return_value = "parse error"
        mock_trt.OnnxParser.return_value = mock_parser
        mock_trt.Builder.return_value = MagicMock()

        saved_trt = mod.trt
        saved_avail = mod.TENSORRT_AVAILABLE
        try:
            mod.TENSORRT_AVAILABLE = True
            mod.trt = mock_trt

            with pytest.raises(RuntimeError, match="Failed to parse ONNX"):
                opt.convert_to_tensorrt(force=True)
        finally:
            mod.trt = saved_trt
            mod.TENSORRT_AVAILABLE = saved_avail

    def test_convert_build_failure(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path)
        opt.onnx_path.write_bytes(b"fake")

        mock_trt = MagicMock()
        mock_trt.Logger.return_value = MagicMock()
        mock_trt.Logger.WARNING = 2
        mock_trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH = 0
        mock_parser = MagicMock()
        mock_parser.parse.return_value = True
        mock_trt.OnnxParser.return_value = mock_parser
        mock_builder = MagicMock()
        mock_builder.platform_has_fast_fp16 = True
        mock_builder.build_serialized_network.return_value = None
        mock_trt.Builder.return_value = mock_builder

        saved_trt = mod.trt
        saved_avail = mod.TENSORRT_AVAILABLE
        try:
            mod.TENSORRT_AVAILABLE = True
            mod.trt = mock_trt

            with pytest.raises(RuntimeError, match="Failed to build TensorRT"):
                opt.convert_to_tensorrt(force=True)
        finally:
            mod.trt = saved_trt
            mod.TENSORRT_AVAILABLE = saved_avail

    def test_convert_fp16_enabled(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path, use_fp16=True)
        opt.onnx_path.write_bytes(b"fake")

        mock_trt = MagicMock()
        mock_trt.Logger.return_value = MagicMock()
        mock_trt.Logger.WARNING = 2
        mock_trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH = 0
        mock_parser = MagicMock()
        mock_parser.parse.return_value = True
        mock_trt.OnnxParser.return_value = mock_parser
        mock_builder = MagicMock()
        mock_builder.platform_has_fast_fp16 = True
        mock_builder.build_serialized_network.return_value = b"engine"
        mock_trt.Builder.return_value = mock_builder
        mock_config = MagicMock()
        mock_builder.create_builder_config.return_value = mock_config

        saved_trt = mod.trt
        saved_avail = mod.TENSORRT_AVAILABLE
        try:
            mod.TENSORRT_AVAILABLE = True
            mod.trt = mock_trt

            result = opt.convert_to_tensorrt(force=True)
            assert result == opt.trt_path
            mock_config.set_flag.assert_called_once()
        finally:
            mod.trt = saved_trt
            mod.TENSORRT_AVAILABLE = saved_avail


class TestLoadTensorrtEngine:
    """Test load_tensorrt_engine method."""

    @patch(f"{MOD_TRT}.TENSORRT_AVAILABLE", False)
    def test_no_tensorrt(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        assert opt.load_tensorrt_engine() is False

    def test_no_trt_file(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path)
        saved = mod.TENSORRT_AVAILABLE
        try:
            mod.TENSORRT_AVAILABLE = True
            assert opt.load_tensorrt_engine() is False
        finally:
            mod.TENSORRT_AVAILABLE = saved

    def test_validation_fails(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path)
        opt.trt_path.write_bytes(b"x" * 100)

        saved = mod.TENSORRT_AVAILABLE
        try:
            mod.TENSORRT_AVAILABLE = True
            opt.validate_engine = MagicMock(return_value=False)
            assert opt.load_tensorrt_engine() is False
        finally:
            mod.TENSORRT_AVAILABLE = saved

    def test_deserialize_returns_none(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path)
        opt.trt_path.write_bytes(b"x" * 100)

        mock_trt = MagicMock()
        mock_trt.Logger.return_value = MagicMock()
        mock_trt.Logger.WARNING = 2
        mock_runtime = MagicMock()
        mock_runtime.deserialize_cuda_engine.return_value = None
        mock_trt.Runtime.return_value = mock_runtime

        saved_trt = mod.trt
        saved_avail = mod.TENSORRT_AVAILABLE
        try:
            mod.TENSORRT_AVAILABLE = True
            mod.trt = mock_trt
            opt.validate_engine = MagicMock(return_value=True)

            assert opt.load_tensorrt_engine() is False
        finally:
            mod.trt = saved_trt
            mod.TENSORRT_AVAILABLE = saved_avail

    def test_deserialize_exception(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path)
        opt.trt_path.write_bytes(b"x" * 100)

        mock_trt = MagicMock()
        mock_trt.Logger.return_value = MagicMock()
        mock_trt.Logger.WARNING = 2
        mock_runtime = MagicMock()
        mock_runtime.deserialize_cuda_engine.side_effect = RuntimeError("fail")
        mock_trt.Runtime.return_value = mock_runtime

        saved_trt = mod.trt
        saved_avail = mod.TENSORRT_AVAILABLE
        try:
            mod.TENSORRT_AVAILABLE = True
            mod.trt = mock_trt
            opt.validate_engine = MagicMock(return_value=True)

            assert opt.load_tensorrt_engine() is False
        finally:
            mod.trt = saved_trt
            mod.TENSORRT_AVAILABLE = saved_avail

    def test_successful_load(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path)
        opt.trt_path.write_bytes(b"x" * 100)

        mock_trt = MagicMock()
        mock_trt.Logger.return_value = MagicMock()
        mock_trt.Logger.WARNING = 2
        mock_engine = MagicMock()
        mock_context = MagicMock()
        mock_engine.create_execution_context.return_value = mock_context
        mock_runtime = MagicMock()
        mock_runtime.deserialize_cuda_engine.return_value = mock_engine
        mock_trt.Runtime.return_value = mock_runtime

        saved_trt = mod.trt
        saved_avail = mod.TENSORRT_AVAILABLE
        try:
            mod.TENSORRT_AVAILABLE = True
            mod.trt = mock_trt
            opt.validate_engine = MagicMock(return_value=True)

            assert opt.load_tensorrt_engine() is True
            assert opt._optimization_status["active_backend"] == "tensorrt"
        finally:
            mod.trt = saved_trt
            mod.TENSORRT_AVAILABLE = saved_avail


class TestValidateEngine:
    """Test validate_engine method."""

    def test_file_not_exists(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        assert opt.validate_engine(tmp_path / "nonexistent.trt") is False

    def test_no_tensorrt_available(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path)
        fake_file = tmp_path / "test.trt"
        fake_file.write_bytes(b"x" * (2 * 1024 * 1024))

        saved = mod.TENSORRT_AVAILABLE
        try:
            mod.TENSORRT_AVAILABLE = False
            assert opt.validate_engine(fake_file) is False
        finally:
            mod.TENSORRT_AVAILABLE = saved

    @patch(f"{MOD_TRT}.TENSORRT_AVAILABLE", True)
    def test_file_too_small(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        fake_file = tmp_path / "test.trt"
        fake_file.write_bytes(b"x" * 100)
        assert opt.validate_engine(fake_file) is False

    def test_deserialize_returns_none(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path)
        fake_file = tmp_path / "test.trt"
        fake_file.write_bytes(b"x" * (2 * 1024 * 1024))

        mock_trt = MagicMock()
        mock_trt.Logger.return_value = MagicMock()
        mock_trt.Logger.WARNING = 2
        mock_runtime = MagicMock()
        mock_runtime.deserialize_cuda_engine.return_value = None
        mock_trt.Runtime.return_value = mock_runtime

        saved_trt = mod.trt
        saved_avail = mod.TENSORRT_AVAILABLE
        try:
            mod.TENSORRT_AVAILABLE = True
            mod.trt = mock_trt
            assert opt.validate_engine(fake_file) is False
        finally:
            mod.trt = saved_trt
            mod.TENSORRT_AVAILABLE = saved_avail

    def test_zero_layers(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path)
        fake_file = tmp_path / "test.trt"
        fake_file.write_bytes(b"x" * (2 * 1024 * 1024))

        mock_trt = MagicMock()
        mock_trt.Logger.return_value = MagicMock()
        mock_trt.Logger.WARNING = 2
        mock_engine = MagicMock()
        mock_engine.num_layers = 0
        mock_runtime = MagicMock()
        mock_runtime.deserialize_cuda_engine.return_value = mock_engine
        mock_trt.Runtime.return_value = mock_runtime

        saved_trt = mod.trt
        saved_avail = mod.TENSORRT_AVAILABLE
        try:
            mod.TENSORRT_AVAILABLE = True
            mod.trt = mock_trt
            assert opt.validate_engine(fake_file) is False
        finally:
            mod.trt = saved_trt
            mod.TENSORRT_AVAILABLE = saved_avail

    def test_valid_engine(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path)
        fake_file = tmp_path / "test.trt"
        fake_file.write_bytes(b"x" * (2 * 1024 * 1024))

        mock_trt = MagicMock()
        mock_trt.Logger.return_value = MagicMock()
        mock_trt.Logger.WARNING = 2
        mock_engine = MagicMock()
        mock_engine.num_layers = 10
        mock_runtime = MagicMock()
        mock_runtime.deserialize_cuda_engine.return_value = mock_engine
        mock_trt.Runtime.return_value = mock_runtime

        saved_trt = mod.trt
        saved_avail = mod.TENSORRT_AVAILABLE
        try:
            mod.TENSORRT_AVAILABLE = True
            mod.trt = mock_trt
            assert opt.validate_engine(fake_file) is True
        finally:
            mod.trt = saved_trt
            mod.TENSORRT_AVAILABLE = saved_avail

    def test_exception_during_validation(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path)
        fake_file = tmp_path / "test.trt"
        fake_file.write_bytes(b"x" * (2 * 1024 * 1024))

        mock_trt = MagicMock()
        mock_trt.Logger.return_value = MagicMock()
        mock_trt.Logger.WARNING = 2
        mock_runtime = MagicMock()
        mock_runtime.deserialize_cuda_engine.side_effect = OSError("fail")
        mock_trt.Runtime.return_value = mock_runtime

        saved_trt = mod.trt
        saved_avail = mod.TENSORRT_AVAILABLE
        try:
            mod.TENSORRT_AVAILABLE = True
            mod.trt = mock_trt
            assert opt.validate_engine(fake_file) is False
        finally:
            mod.trt = saved_trt
            mod.TENSORRT_AVAILABLE = saved_avail


class TestLoadOnnxRuntime:
    """Test load_onnx_runtime method."""

    @patch(f"{MOD_TRT}.ONNX_AVAILABLE", False)
    def test_no_onnx(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        assert opt.load_onnx_runtime() is False

    def test_no_onnx_file(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path)
        saved = mod.ONNX_AVAILABLE
        try:
            mod.ONNX_AVAILABLE = True
            assert opt.load_onnx_runtime() is False
        finally:
            mod.ONNX_AVAILABLE = saved

    def test_load_with_cuda(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path)
        opt.onnx_path.write_text("fake")

        mock_ort = MagicMock()
        mock_ort.get_available_providers.return_value = [
            "CUDAExecutionProvider",
            "CPUExecutionProvider",
        ]
        mock_ort.InferenceSession.return_value = MagicMock()

        saved_ort = mod.ort
        saved_avail = mod.ONNX_AVAILABLE
        try:
            mod.ONNX_AVAILABLE = True
            mod.ort = mock_ort
            assert opt.load_onnx_runtime() is True
            assert opt._optimization_status["active_backend"] == "onnxruntime"
            providers = mock_ort.InferenceSession.call_args[1]["providers"]
            assert "CUDAExecutionProvider" in providers
        finally:
            mod.ort = saved_ort
            mod.ONNX_AVAILABLE = saved_avail

    def test_load_cpu_only(self, tmp_path):
        mod = _get_trt_mod()
        opt = _trt_optimizer(tmp_path)
        opt.onnx_path.write_text("fake")

        mock_ort = MagicMock()
        mock_ort.get_available_providers.return_value = ["CPUExecutionProvider"]
        mock_ort.InferenceSession.return_value = MagicMock()

        saved_ort = mod.ort
        saved_avail = mod.ONNX_AVAILABLE
        try:
            mod.ONNX_AVAILABLE = True
            mod.ort = mock_ort
            assert opt.load_onnx_runtime() is True
            providers = mock_ort.InferenceSession.call_args[1]["providers"]
            assert "CUDAExecutionProvider" not in providers
        finally:
            mod.ort = saved_ort
            mod.ONNX_AVAILABLE = saved_avail


class TestInference:
    """Test infer and infer_batch methods."""

    @patch(f"{MOD_TRT}.NUMPY_AVAILABLE", False)
    def test_infer_no_numpy(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        with pytest.raises(ImportError, match="numpy"):
            opt.infer("test")

    @patch(f"{MOD_TRT}.NUMPY_AVAILABLE", False)
    def test_infer_batch_no_numpy(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        with pytest.raises(ImportError, match="numpy"):
            opt.infer_batch(["test"])

    def test_infer_delegates_to_batch(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        mock_result = np.zeros((1, 768), dtype=np.float32)
        opt.infer_batch = MagicMock(return_value=mock_result)

        result = opt.infer("test")
        opt.infer_batch.assert_called_once_with(["test"])
        assert np.array_equal(result, mock_result[0])

    def test_infer_batch_torch_fallback(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        opt._trt_context = None
        opt._onnx_session = None
        opt._latency_threshold_ms = 999999

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.zeros((1, 128), dtype=np.int64),
            "attention_mask": np.ones((1, 128), dtype=np.int64),
        }
        opt._load_tokenizer = MagicMock(return_value=mock_tokenizer)

        expected = np.zeros((1, 768), dtype=np.float32)
        opt._infer_torch = MagicMock(return_value=expected)

        result = opt.infer_batch(["test"])
        assert np.array_equal(result, expected)

    def test_infer_batch_onnx_backend(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        opt._trt_context = None
        opt._onnx_session = MagicMock()
        opt._latency_threshold_ms = 999999

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.zeros((1, 128), dtype=np.int64),
            "attention_mask": np.ones((1, 128), dtype=np.int64),
        }
        opt._load_tokenizer = MagicMock(return_value=mock_tokenizer)

        expected = np.zeros((1, 768), dtype=np.float32)
        opt._infer_onnx = MagicMock(return_value=expected)

        result = opt.infer_batch(["test"])
        opt._infer_onnx.assert_called_once()

    def test_infer_batch_trt_backend(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        opt._trt_context = MagicMock()
        opt._latency_threshold_ms = 999999

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.zeros((1, 128), dtype=np.int64),
            "attention_mask": np.ones((1, 128), dtype=np.int64),
        }
        opt._load_tokenizer = MagicMock(return_value=mock_tokenizer)

        expected = np.zeros((1, 768), dtype=np.float32)
        opt._infer_tensorrt = MagicMock(return_value=expected)

        result = opt.infer_batch(["test"])
        opt._infer_tensorrt.assert_called_once()

    def test_infer_batch_timeout_before_torch(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        opt._trt_context = None
        opt._onnx_session = None
        opt._latency_threshold_ms = 0.0  # Always timeout

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.zeros((1, 128), dtype=np.int64),
            "attention_mask": np.ones((1, 128), dtype=np.int64),
        }
        opt._load_tokenizer = MagicMock(return_value=mock_tokenizer)

        result = opt.infer_batch(["test"])
        assert result.shape == (1, 768)
        assert np.all(result == 0)

    def test_infer_batch_timeout_after_inference(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        opt._trt_context = None
        opt._onnx_session = None
        opt._latency_threshold_ms = 999999

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.zeros((1, 128), dtype=np.int64),
            "attention_mask": np.ones((1, 128), dtype=np.int64),
        }
        opt._load_tokenizer = MagicMock(return_value=mock_tokenizer)

        def slow_torch(inputs):
            opt._latency_threshold_ms = 0.0
            return np.ones((1, 768), dtype=np.float32)

        opt._infer_torch = slow_torch

        result = opt.infer_batch(["test"])
        # Should return fallback zeros due to post-inference timeout
        assert np.all(result == 0)

    def test_infer_batch_exception_fallback(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        opt._trt_context = None
        opt._onnx_session = None
        opt._latency_threshold_ms = 999999

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.zeros((2, 128), dtype=np.int64),
            "attention_mask": np.ones((2, 128), dtype=np.int64),
        }
        opt._load_tokenizer = MagicMock(return_value=mock_tokenizer)
        opt._infer_torch = MagicMock(side_effect=RuntimeError("CUDA OOM"))

        result = opt.infer_batch(["hello", "world"])
        assert result.shape == (2, 768)
        assert np.all(result == 0)


class TestGenerateFallbackEmbeddings:
    """Test _generate_fallback_embeddings."""

    def test_generates_zeros(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        result = opt._generate_fallback_embeddings(3)
        assert result.shape == (3, 768)
        assert result.dtype == np.float32
        assert np.all(result == 0)

    @patch(f"{MOD_TRT}.NUMPY_AVAILABLE", False)
    def test_no_numpy(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        with pytest.raises(ImportError, match="numpy"):
            opt._generate_fallback_embeddings(1)


class TestInferTensorrt:
    """Test _infer_tensorrt."""

    def test_raises_not_implemented(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        with pytest.raises(NotImplementedError):
            opt._infer_tensorrt({"input_ids": np.zeros((1, 128))})


class TestInferOnnx:
    """Test _infer_onnx."""

    @patch(f"{MOD_TRT}.NUMPY_AVAILABLE", False)
    def test_no_numpy(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        with pytest.raises(ImportError, match="numpy"):
            opt._infer_onnx({})

    def test_no_session(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        opt._onnx_session = None
        with pytest.raises(RuntimeError, match="ONNX session not loaded"):
            opt._infer_onnx({})


class TestInferTorch:
    """Test _infer_torch."""

    @patch(f"{MOD_TRT}.NUMPY_AVAILABLE", False)
    def test_no_numpy(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        with pytest.raises(ImportError, match="numpy"):
            opt._infer_torch({})


class TestBenchmark:
    """Test benchmark method."""

    def test_benchmark_runs(self, tmp_path):
        opt = _trt_optimizer(tmp_path)
        opt.infer = MagicMock(return_value=np.zeros(768))

        result = opt.benchmark(num_samples=20)
        assert "backend" in result
        assert "latency_p50_ms" in result
        assert "latency_p95_ms" in result
        assert "latency_p99_ms" in result
        assert "latency_mean_ms" in result
        assert result["num_samples"] == 20
        # 10 warmup + 20 benchmark = 30 calls
        assert opt.infer.call_count == 30


class TestModuleFunctions:
    """Test module-level functions."""

    def test_get_optimization_status(self):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
            get_optimization_status,
        )

        with patch.object(TensorRTOptimizer, "__init__", return_value=None):
            with patch.object(TensorRTOptimizer, "status", new_callable=PropertyMock) as ms:
                ms.return_value = {"active_backend": "none"}
                result = get_optimization_status()
                assert result == {"active_backend": "none"}

    def test_optimize_distilbert_onnx_error(self):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
            optimize_distilbert,
        )

        with patch.object(TensorRTOptimizer, "__init__", return_value=None):
            with patch.object(
                TensorRTOptimizer, "status", new_callable=PropertyMock, return_value={"a": 1}
            ):
                with patch.object(
                    TensorRTOptimizer, "export_onnx", side_effect=RuntimeError("no torch")
                ):
                    result = optimize_distilbert(force=True)
                    assert "onnx_error" in result
                    assert result["onnx_error"] == "no torch"

    @patch(f"{MOD_TRT}.TENSORRT_AVAILABLE", False)
    def test_optimize_distilbert_no_tensorrt(self):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
            optimize_distilbert,
        )

        with patch.object(TensorRTOptimizer, "__init__", return_value=None):
            with patch.object(
                TensorRTOptimizer, "status", new_callable=PropertyMock, return_value={"a": 1}
            ):
                with patch.object(
                    TensorRTOptimizer, "export_onnx", return_value=Path("/fake.onnx")
                ):
                    with patch.object(
                        TensorRTOptimizer, "load_tensorrt_engine", return_value=False
                    ):
                        with patch.object(
                            TensorRTOptimizer, "load_onnx_runtime", return_value=False
                        ):
                            with patch.object(
                                TensorRTOptimizer, "benchmark", side_effect=RuntimeError("no")
                            ):
                                result = optimize_distilbert()
                                assert "tensorrt_skipped" in result
                                assert result["active_backend"] == "pytorch"
                                assert "benchmark_error" in result

    def test_optimize_distilbert_with_tensorrt(self):
        mod = _get_trt_mod()
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
            optimize_distilbert,
        )

        saved = mod.TENSORRT_AVAILABLE
        try:
            mod.TENSORRT_AVAILABLE = True

            with patch.object(TensorRTOptimizer, "__init__", return_value=None):
                with patch.object(
                    TensorRTOptimizer, "status", new_callable=PropertyMock, return_value={"a": 1}
                ):
                    with patch.object(
                        TensorRTOptimizer, "export_onnx", return_value=Path("/f.onnx")
                    ):
                        with patch.object(
                            TensorRTOptimizer, "convert_to_tensorrt", return_value=Path("/f.trt")
                        ):
                            with patch.object(
                                TensorRTOptimizer, "load_tensorrt_engine", return_value=True
                            ):
                                with patch.object(
                                    TensorRTOptimizer, "benchmark", return_value={"p99": 1.0}
                                ):
                                    result = optimize_distilbert()
                                    assert "tensorrt_convert" in result["steps_completed"]
                                    assert result["active_backend"] == "tensorrt"
        finally:
            mod.TENSORRT_AVAILABLE = saved

    def test_optimize_distilbert_onnxruntime_fallback(self):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
            optimize_distilbert,
        )

        with patch(f"{MOD_TRT}.TENSORRT_AVAILABLE", False):
            with patch.object(TensorRTOptimizer, "__init__", return_value=None):
                with patch.object(
                    TensorRTOptimizer, "status", new_callable=PropertyMock, return_value={"a": 1}
                ):
                    with patch.object(
                        TensorRTOptimizer, "export_onnx", return_value=Path("/f.onnx")
                    ):
                        with patch.object(
                            TensorRTOptimizer, "load_tensorrt_engine", return_value=False
                        ):
                            with patch.object(
                                TensorRTOptimizer, "load_onnx_runtime", return_value=True
                            ):
                                with patch.object(
                                    TensorRTOptimizer, "benchmark", return_value={"p99": 5.0}
                                ):
                                    result = optimize_distilbert()
                                    assert result["active_backend"] == "onnxruntime"

    def test_optimize_trt_convert_error(self):
        mod = _get_trt_mod()
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
            optimize_distilbert,
        )

        saved = mod.TENSORRT_AVAILABLE
        try:
            mod.TENSORRT_AVAILABLE = True

            with patch.object(TensorRTOptimizer, "__init__", return_value=None):
                with patch.object(
                    TensorRTOptimizer, "status", new_callable=PropertyMock, return_value={"a": 1}
                ):
                    with patch.object(
                        TensorRTOptimizer, "export_onnx", return_value=Path("/f.onnx")
                    ):
                        with patch.object(
                            TensorRTOptimizer,
                            "convert_to_tensorrt",
                            side_effect=RuntimeError("fail"),
                        ):
                            with patch.object(
                                TensorRTOptimizer, "load_tensorrt_engine", return_value=False
                            ):
                                with patch.object(
                                    TensorRTOptimizer, "load_onnx_runtime", return_value=False
                                ):
                                    with patch.object(
                                        TensorRTOptimizer, "benchmark", return_value={"p99": 5.0}
                                    ):
                                        result = optimize_distilbert()
                                        assert "tensorrt_error" in result
        finally:
            mod.TENSORRT_AVAILABLE = saved

    def test_optimize_trt_convert_returns_none(self):
        mod = _get_trt_mod()
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
            optimize_distilbert,
        )

        saved = mod.TENSORRT_AVAILABLE
        try:
            mod.TENSORRT_AVAILABLE = True

            with patch.object(TensorRTOptimizer, "__init__", return_value=None):
                with patch.object(
                    TensorRTOptimizer, "status", new_callable=PropertyMock, return_value={"a": 1}
                ):
                    with patch.object(
                        TensorRTOptimizer, "export_onnx", return_value=Path("/f.onnx")
                    ):
                        with patch.object(
                            TensorRTOptimizer, "convert_to_tensorrt", return_value=None
                        ):
                            with patch.object(
                                TensorRTOptimizer, "load_tensorrt_engine", return_value=False
                            ):
                                with patch.object(
                                    TensorRTOptimizer, "load_onnx_runtime", return_value=False
                                ):
                                    with patch.object(
                                        TensorRTOptimizer, "benchmark", return_value={"p99": 5.0}
                                    ):
                                        result = optimize_distilbert()
                                        assert "tensorrt_convert" not in result["steps_completed"]
        finally:
            mod.TENSORRT_AVAILABLE = saved


# ---------------------------------------------------------------------------
# Database Repository Optimized Tests
# ---------------------------------------------------------------------------


def _make_mock_session():
    """Create a mock AsyncSession."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    return session


def _make_mock_orm(
    tenant_id="tid-1",
    name="Test Tenant",
    slug="test-tenant",
    status="active",
    config=None,
    quota=None,
    metadata_=None,
    parent_tenant_id=None,
    created_at=None,
    updated_at=None,
    activated_at=None,
    suspended_at=None,
):
    """Create a mock TenantORM."""
    orm = MagicMock()
    orm.tenant_id = tenant_id
    orm.name = name
    orm.slug = slug
    orm.status = status
    orm.config = config or {}
    orm.quota = quota or {}
    orm.metadata_ = metadata_ or {}
    orm.parent_tenant_id = parent_tenant_id
    orm.created_at = created_at or datetime.now(UTC)
    orm.updated_at = updated_at or datetime.now(UTC)
    orm.activated_at = activated_at
    orm.suspended_at = suspended_at
    return orm


def _make_repo(session=None, enable_caching=False):
    """Create a DatabaseTenantRepository with mocked cache."""
    from enhanced_agent_bus.multi_tenancy.db_repository_optimized import (
        DatabaseTenantRepository,
    )

    if session is None:
        session = _make_mock_session()
    return DatabaseTenantRepository(session, enable_caching=enable_caching)


class TestDatabaseTenantRepositoryInit:
    """Test repository initialization."""

    def test_init_with_caching(self):
        session = _make_mock_session()
        with patch(f"{MOD_DB}.TieredCacheManager") as mock_cache_cls:
            from enhanced_agent_bus.multi_tenancy.db_repository_optimized import (
                DatabaseTenantRepository,
            )

            repo = DatabaseTenantRepository(session, enable_caching=True)
            assert repo.session is session
            assert repo._enable_caching is True
            assert repo._tenant_cache is not None

    def test_init_without_caching(self):
        session = _make_mock_session()
        repo = _make_repo(session)
        assert repo._tenant_cache is None


class TestDatabaseTenantRepositoryHelpers:
    """Test helper methods."""

    def test_generate_tenant_cache_key(self):
        from enhanced_agent_bus.multi_tenancy.db_repository_optimized import (
            CONSTITUTIONAL_HASH,
        )

        repo = _make_repo()
        key = repo._generate_tenant_cache_key("tid-1")
        expected_hash = hashlib.sha256(f"tenant:tid-1:{CONSTITUTIONAL_HASH}".encode()).hexdigest()
        assert key == f"tenant:id:{expected_hash}"

    def test_generate_slug_cache_key(self):
        from enhanced_agent_bus.multi_tenancy.db_repository_optimized import (
            CONSTITUTIONAL_HASH,
        )

        repo = _make_repo()
        key = repo._generate_slug_cache_key("test-slug")
        expected_hash = hashlib.sha256(f"slug:test-slug:{CONSTITUTIONAL_HASH}".encode()).hexdigest()
        assert key == f"tenant:slug:{expected_hash}"

    def test_status_to_orm(self):
        from enhanced_agent_bus.multi_tenancy.models import TenantStatus
        from enhanced_agent_bus.multi_tenancy.orm_models import TenantStatusEnum

        repo = _make_repo()
        assert repo._status_to_orm(TenantStatus.ACTIVE) == TenantStatusEnum.ACTIVE
        assert repo._status_to_orm(TenantStatus.SUSPENDED) == TenantStatusEnum.SUSPENDED
        assert repo._status_to_orm(None) == TenantStatusEnum.PENDING
        assert repo._status_to_orm("unknown") == TenantStatusEnum.PENDING

    def test_dump_config_none(self):
        repo = _make_repo()
        assert repo._dump_config(None) == {}

    def test_dump_config_dict(self):
        repo = _make_repo()
        assert repo._dump_config({"key": "val"}) == {"key": "val"}

    def test_dump_config_pydantic(self):
        from enhanced_agent_bus.multi_tenancy.models import TenantConfig

        repo = _make_repo()
        config = TenantConfig()
        result = repo._dump_config(config)
        assert isinstance(result, dict)

    def test_dump_quota_none(self):
        repo = _make_repo()
        assert repo._dump_quota(None) == {}

    def test_dump_quota_dict(self):
        repo = _make_repo()
        assert repo._dump_quota({"max_agents": 50}) == {"max_agents": 50}

    def test_dump_quota_with_model_dump(self):
        repo = _make_repo()
        obj = MagicMock()
        obj.model_dump.return_value = {"max_agents": 100}
        result = repo._dump_quota(obj)
        assert result == {"max_agents": 100}

    def test_dump_quota_no_model_dump(self):
        repo = _make_repo()

        class NoModelDump:
            pass

        result = repo._dump_quota(NoModelDump())
        assert result == {}

    def test_normalize_metadata(self):
        repo = _make_repo()
        assert repo._normalize_metadata(None) == {}
        assert repo._normalize_metadata({"key": "val"}) == {"key": "val"}


class TestOrmConversions:
    """Test ORM to Pydantic and back conversions."""

    def test_orm_to_pydantic_basic(self):
        repo = _make_repo()
        now = datetime.now(UTC)
        orm = _make_mock_orm(created_at=now, updated_at=now)
        tenant = repo._orm_to_pydantic(orm)
        assert tenant.tenant_id == "tid-1"
        assert tenant.name == "Test Tenant"
        assert tenant.slug == "test-tenant"

    def test_orm_to_pydantic_no_status(self):
        from enhanced_agent_bus.multi_tenancy.models import TenantStatus

        repo = _make_repo()
        orm = _make_mock_orm(status=None)
        tenant = repo._orm_to_pydantic(orm)
        assert tenant.status == TenantStatus.PENDING

    def test_orm_to_pydantic_unknown_status(self):
        from enhanced_agent_bus.multi_tenancy.models import TenantStatus

        repo = _make_repo()
        orm = _make_mock_orm(status="unknown_status")
        tenant = repo._orm_to_pydantic(orm)
        assert tenant.status == TenantStatus.PENDING

    def test_orm_to_pydantic_no_timestamps(self):
        repo = _make_repo()
        orm = _make_mock_orm(created_at="not-a-datetime", updated_at="not-a-datetime")
        tenant = repo._orm_to_pydantic(orm)
        assert isinstance(tenant.created_at, datetime)
        assert isinstance(tenant.updated_at, datetime)

    def test_orm_to_pydantic_with_parent(self):
        repo = _make_repo()
        orm = _make_mock_orm(parent_tenant_id="parent-1")
        tenant = repo._orm_to_pydantic(orm)
        assert tenant.parent_tenant_id == "parent-1"

    def test_orm_to_pydantic_no_parent(self):
        repo = _make_repo()
        orm = _make_mock_orm(parent_tenant_id=None)
        tenant = repo._orm_to_pydantic(orm)
        assert tenant.parent_tenant_id == ""

    def test_orm_to_pydantic_activated_at(self):
        repo = _make_repo()
        now = datetime.now(UTC)
        orm = _make_mock_orm(activated_at=now, suspended_at=now)
        tenant = repo._orm_to_pydantic(orm)
        assert tenant.activated_at == now
        assert tenant.suspended_at == now

    def test_orm_to_pydantic_activated_at_not_datetime(self):
        repo = _make_repo()
        orm = _make_mock_orm(activated_at="not-a-datetime", suspended_at="not-a-datetime")
        tenant = repo._orm_to_pydantic(orm)
        assert tenant.activated_at is None
        assert tenant.suspended_at is None

    def test_pydantic_to_orm(self):
        from enhanced_agent_bus.multi_tenancy.models import Tenant, TenantConfig, TenantStatus

        repo = _make_repo()
        now = datetime.now(UTC)
        tenant = Tenant(
            tenant_id="tid-1",
            name="Test",
            slug="test",
            status=TenantStatus.ACTIVE,
            config=TenantConfig(),
            quota={},
            metadata={},
            parent_tenant_id="",
            created_at=now,
            updated_at=now,
        )

        with patch(f"{MOD_DB}.TenantORM") as mock_orm_cls:
            mock_orm_cls.return_value = MagicMock()
            result = repo._pydantic_to_orm(tenant)
            mock_orm_cls.assert_called_once()


class TestInitializeAndClose:
    """Test initialize and close methods."""

    async def test_initialize_with_cache(self):
        repo = _make_repo()
        mock_cache = AsyncMock()
        mock_cache.initialize = AsyncMock(return_value=True)
        repo._tenant_cache = mock_cache

        result = await repo.initialize()
        assert result is True
        mock_cache.initialize.assert_awaited_once()

    async def test_initialize_no_cache(self):
        repo = _make_repo()
        result = await repo.initialize()
        assert result is True

    async def test_close_with_cache(self):
        repo = _make_repo()
        mock_cache = AsyncMock()
        repo._tenant_cache = mock_cache

        await repo.close()
        mock_cache.close.assert_awaited_once()

    async def test_close_no_cache(self):
        repo = _make_repo()
        await repo.close()


class TestInvalidateTenantCache:
    """Test cache invalidation."""

    async def test_invalidate_no_cache(self):
        repo = _make_repo()
        await repo._invalidate_tenant_cache("tid-1")

    async def test_invalidate_with_cache_and_slug(self):
        repo = _make_repo()
        mock_cache = AsyncMock()
        repo._tenant_cache = mock_cache

        await repo._invalidate_tenant_cache("tid-1", slug="test-slug")
        assert mock_cache.delete.await_count == 2

    async def test_invalidate_with_cache_no_slug(self):
        repo = _make_repo()
        mock_cache = AsyncMock()
        repo._tenant_cache = mock_cache

        await repo._invalidate_tenant_cache("tid-1")
        assert mock_cache.delete.await_count == 1


class TestCreateTenant:
    """Test create_tenant."""

    async def test_create_duplicate_slug(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()
        session.execute.return_value = mock_result

        repo = _make_repo(session)
        with pytest.raises(ValueError, match="already exists"):
            await repo.create_tenant(name="Test", slug="existing-slug")

    async def test_create_success_no_cache(self):
        session = _make_mock_session()
        mock_check = MagicMock()
        mock_check.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_check

        orm_result = _make_mock_orm()

        from enhanced_agent_bus.multi_tenancy.db_repository_optimized import (
            DatabaseTenantRepository,
        )

        repo = DatabaseTenantRepository(session, enable_caching=False)

        with patch(f"{MOD_DB}.TenantORM", return_value=orm_result):
            with patch(f"{MOD_DB}.select") as mock_select:
                # Make select() return a mock that chains properly
                mock_select.return_value.where.return_value = MagicMock()
                # Override session.execute to handle both the select check and commit
                session.execute.return_value = mock_check
                tenant = await repo.create_tenant(name="Test", slug="test-slug")
                assert tenant.name == "Test Tenant"

    async def test_create_success_with_cache(self):
        session = _make_mock_session()
        mock_check = MagicMock()
        mock_check.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_check

        orm_result = _make_mock_orm()

        from enhanced_agent_bus.multi_tenancy.db_repository_optimized import (
            DatabaseTenantRepository,
        )

        repo = DatabaseTenantRepository(session, enable_caching=False)
        mock_cache = AsyncMock()
        repo._tenant_cache = mock_cache

        with patch(f"{MOD_DB}.TenantORM", return_value=orm_result):
            with patch(f"{MOD_DB}.select") as mock_select:
                mock_select.return_value.where.return_value = MagicMock()
                session.execute.return_value = mock_check
                tenant = await repo.create_tenant(name="Test", slug="test-slug")
                assert mock_cache.set.await_count == 2


class TestBulkOperations:
    """Test bulk create, update, delete."""

    async def test_create_bulk_optimized(self):
        session = _make_mock_session()
        mock_fetch_result = MagicMock()
        mock_fetch_result.scalars.return_value.all.return_value = [_make_mock_orm()]
        session.execute.return_value = mock_fetch_result

        repo = _make_repo(session)

        with patch(f"{MOD_DB}.BulkOperations.bulk_insert", new_callable=AsyncMock):
            tenants = await repo.create_tenants_bulk_optimized([{"name": "A", "slug": "a"}])
            assert len(tenants) == 1

    async def test_create_bulk_with_cache(self):
        session = _make_mock_session()
        mock_fetch_result = MagicMock()
        mock_fetch_result.scalars.return_value.all.return_value = [_make_mock_orm()]
        session.execute.return_value = mock_fetch_result

        repo = _make_repo(session)
        mock_cache = AsyncMock()
        repo._tenant_cache = mock_cache

        with patch(f"{MOD_DB}.BulkOperations.bulk_insert", new_callable=AsyncMock):
            tenants = await repo.create_tenants_bulk_optimized([{"name": "A", "slug": "a"}])
            assert mock_cache.set.await_count == 2

    async def test_update_bulk(self):
        session = _make_mock_session()
        repo = _make_repo(session)

        with patch(f"{MOD_DB}.BulkOperations.bulk_update", new_callable=AsyncMock, return_value=3):
            count = await repo.update_tenants_bulk(
                [{"tenant_id": "t1"}, {"tenant_id": "t2"}, {"tenant_id": "t3"}]
            )
            assert count == 3

    async def test_update_bulk_with_cache(self):
        session = _make_mock_session()
        repo = _make_repo(session)
        mock_cache = AsyncMock()
        repo._tenant_cache = mock_cache

        with patch(f"{MOD_DB}.BulkOperations.bulk_update", new_callable=AsyncMock, return_value=2):
            count = await repo.update_tenants_bulk([{"tenant_id": "t1"}, {"tenant_id": "t2"}])
            assert count == 2
            assert mock_cache.delete.await_count >= 2

    async def test_delete_bulk(self):
        session = _make_mock_session()
        repo = _make_repo(session)

        with patch(f"{MOD_DB}.BulkOperations.bulk_delete", new_callable=AsyncMock, return_value=2):
            count = await repo.delete_tenants_bulk(["t1", "t2"])
            assert count == 2

    async def test_delete_bulk_with_cache(self):
        session = _make_mock_session()
        repo = _make_repo(session)
        mock_cache = AsyncMock()
        repo._tenant_cache = mock_cache

        with patch(f"{MOD_DB}.BulkOperations.bulk_delete", new_callable=AsyncMock, return_value=2):
            count = await repo.delete_tenants_bulk(["t1", "t2"])
            assert count == 2
            assert mock_cache.delete.await_count >= 2


class TestGetTenant:
    """Test get_tenant and get_tenant_by_slug."""

    async def test_get_tenant_cache_hit(self):
        session = _make_mock_session()
        repo = _make_repo(session)
        mock_cache = AsyncMock()
        now = datetime.now(UTC)
        cached_data = {
            "tenant_id": "tid-1",
            "name": "Cached",
            "slug": "cached",
            "status": "active",
            "config": {},
            "quota": {},
            "metadata": {},
            "parent_tenant_id": "",
            "created_at": now,
            "updated_at": now,
            "activated_at": None,
            "suspended_at": None,
        }
        mock_cache.get_async = AsyncMock(return_value=cached_data)
        repo._tenant_cache = mock_cache

        tenant = await repo.get_tenant("tid-1")
        assert tenant is not None
        assert tenant.name == "Cached"
        session.execute.assert_not_awaited()

    async def test_get_tenant_cache_miss(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _make_mock_orm()
        session.execute.return_value = mock_result

        repo = _make_repo(session)
        mock_cache = AsyncMock()
        mock_cache.get_async = AsyncMock(return_value=None)
        repo._tenant_cache = mock_cache

        tenant = await repo.get_tenant("tid-1")
        assert tenant is not None
        mock_cache.set.assert_awaited_once()

    async def test_get_tenant_not_found(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        repo = _make_repo(session)
        tenant = await repo.get_tenant("nonexistent")
        assert tenant is None

    async def test_get_tenant_no_cache(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _make_mock_orm()
        session.execute.return_value = mock_result

        repo = _make_repo(session)
        tenant = await repo.get_tenant("tid-1")
        assert tenant is not None

    async def test_get_by_slug_cache_hit(self):
        session = _make_mock_session()
        repo = _make_repo(session)
        mock_cache = AsyncMock()
        now = datetime.now(UTC)
        cached_data = {
            "tenant_id": "tid-1",
            "name": "Cached",
            "slug": "cached",
            "status": "active",
            "config": {},
            "quota": {},
            "metadata": {},
            "parent_tenant_id": "",
            "created_at": now,
            "updated_at": now,
            "activated_at": None,
            "suspended_at": None,
        }
        mock_cache.get_async = AsyncMock(return_value=cached_data)
        repo._tenant_cache = mock_cache

        tenant = await repo.get_tenant_by_slug("cached")
        assert tenant is not None
        assert tenant.name == "Cached"

    async def test_get_by_slug_cache_miss(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _make_mock_orm()
        session.execute.return_value = mock_result

        repo = _make_repo(session)
        mock_cache = AsyncMock()
        mock_cache.get_async = AsyncMock(return_value=None)
        repo._tenant_cache = mock_cache

        tenant = await repo.get_tenant_by_slug("test-slug")
        assert tenant is not None
        assert mock_cache.set.await_count == 2

    async def test_get_by_slug_not_found(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        repo = _make_repo(session)
        tenant = await repo.get_tenant_by_slug("nonexistent")
        assert tenant is None

    async def test_get_by_slug_no_cache(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = _make_mock_orm()
        session.execute.return_value = mock_result

        repo = _make_repo(session)
        tenant = await repo.get_tenant_by_slug("test-slug")
        assert tenant is not None


class TestListTenants:
    """Test list_tenants."""

    async def test_list_no_filter(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_make_mock_orm()]
        session.execute.return_value = mock_result

        repo = _make_repo(session)
        tenants = await repo.list_tenants()
        assert len(tenants) == 1

    async def test_list_with_status_filter(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_make_mock_orm()]
        session.execute.return_value = mock_result

        from enhanced_agent_bus.multi_tenancy.models import TenantStatus

        repo = _make_repo(session)
        tenants = await repo.list_tenants(status=TenantStatus.ACTIVE)
        assert len(tenants) == 1

    async def test_list_with_offset(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        repo = _make_repo(session)
        tenants = await repo.list_tenants(offset=10, limit=5)
        assert len(tenants) == 0


class TestListTenantsPaginated:
    """Test list_tenants_paginated."""

    async def test_paginated_no_filter(self):
        session = _make_mock_session()
        from enhanced_agent_bus._compat.database.utils import Page, Pageable

        repo = _make_repo(session)
        mock_page = Page(content=[_make_mock_orm()], total_elements=1, page_number=0, page_size=20)

        with patch(f"{MOD_DB}.paginate", new_callable=AsyncMock, return_value=mock_page):
            pageable = Pageable(page=0, size=20)
            result = await repo.list_tenants_paginated(pageable)
            assert result.total_elements == 1
            assert len(result.content) == 1

    async def test_paginated_with_status(self):
        session = _make_mock_session()
        from enhanced_agent_bus._compat.database.utils import Page, Pageable
        from enhanced_agent_bus.multi_tenancy.models import TenantStatus

        repo = _make_repo(session)
        mock_page = Page(content=[], total_elements=0, page_number=0, page_size=20)

        with patch(f"{MOD_DB}.paginate", new_callable=AsyncMock, return_value=mock_page):
            pageable = Pageable(page=0, size=20)
            result = await repo.list_tenants_paginated(pageable, status=TenantStatus.ACTIVE)
            assert result.total_elements == 0


class TestListTenantSummaries:
    """Test list_tenant_summaries."""

    async def test_summaries_no_filter(self):
        session = _make_mock_session()
        now = datetime.now(UTC)

        mock_row = MagicMock()
        mock_row.tenant_id = "tid-1"
        mock_row.name = "Test"
        mock_row.slug = "test"
        mock_row.status = "active"
        mock_row.created_at = now

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        mock_data_result = MagicMock()
        mock_data_result.all.return_value = [mock_row]

        session.execute.side_effect = [mock_count_result, mock_data_result]

        from enhanced_agent_bus._compat.database.utils import Pageable

        repo = _make_repo(session)
        pageable = Pageable(page=0, size=20, sort=[("created_at", "desc")])
        result = await repo.list_tenant_summaries(pageable)
        assert result.total_elements == 1
        assert len(result.content) == 1
        assert result.content[0].tenant_id == "tid-1"

    async def test_summaries_with_status(self):
        session = _make_mock_session()

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0
        mock_data_result = MagicMock()
        mock_data_result.all.return_value = []

        session.execute.side_effect = [mock_count_result, mock_data_result]

        from enhanced_agent_bus._compat.database.utils import Pageable
        from enhanced_agent_bus.multi_tenancy.models import TenantStatus

        repo = _make_repo(session)
        pageable = Pageable(page=0, size=20, sort=[("name", "asc")])
        result = await repo.list_tenant_summaries(pageable, status=TenantStatus.ACTIVE)
        assert result.total_elements == 0

    async def test_summaries_sorting_invalid_column(self):
        session = _make_mock_session()

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0
        mock_data_result = MagicMock()
        mock_data_result.all.return_value = []

        session.execute.side_effect = [mock_count_result, mock_data_result]

        from enhanced_agent_bus._compat.database.utils import Pageable

        repo = _make_repo(session)
        pageable = Pageable(page=0, size=20, sort=[("nonexistent_col", "asc")])
        result = await repo.list_tenant_summaries(pageable)
        assert result.total_elements == 0


class TestGetTenantHierarchy:
    """Test get_tenant_hierarchy."""

    async def test_hierarchy_root(self):
        session = _make_mock_session()
        now = datetime.now(UTC)

        mock_row = MagicMock()
        mock_row.tenant_id = "tid-1"
        mock_row.name = "Root"
        mock_row.slug = "root"
        mock_row.status = "active"
        mock_row.parent_tenant_id = None
        mock_row.child_count = 2
        mock_row.created_at = now

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        session.execute.return_value = mock_result

        repo = _make_repo(session)
        nodes = await repo.get_tenant_hierarchy(parent_tenant_id=None)
        assert len(nodes) == 1
        assert nodes[0].tenant_id == "tid-1"
        assert nodes[0].child_count == 2
        assert nodes[0].parent_tenant_id is None

    async def test_hierarchy_with_parent(self):
        session = _make_mock_session()
        now = datetime.now(UTC)

        mock_row = MagicMock()
        mock_row.tenant_id = "tid-2"
        mock_row.name = "Child"
        mock_row.slug = "child"
        mock_row.status = "active"
        mock_row.parent_tenant_id = "tid-1"
        mock_row.child_count = 0
        mock_row.created_at = now

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        session.execute.return_value = mock_result

        repo = _make_repo(session)
        nodes = await repo.get_tenant_hierarchy(parent_tenant_id="tid-1")
        assert len(nodes) == 1
        assert nodes[0].parent_tenant_id == "tid-1"


class TestLifecycleOperations:
    """Test activate, suspend, delete."""

    async def test_activate_not_found(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        repo = _make_repo(session)
        result = await repo.activate_tenant("nonexistent")
        assert result is None

    async def test_activate_success(self):
        session = _make_mock_session()
        orm = _make_mock_orm()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = orm
        session.execute.return_value = mock_result

        repo = _make_repo(session)
        tenant = await repo.activate_tenant("tid-1")
        assert tenant is not None
        session.commit.assert_awaited_once()

    async def test_suspend_not_found(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        repo = _make_repo(session)
        result = await repo.suspend_tenant("nonexistent")
        assert result is None

    async def test_suspend_success(self):
        session = _make_mock_session()
        orm = _make_mock_orm()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = orm
        session.execute.return_value = mock_result

        repo = _make_repo(session)
        tenant = await repo.suspend_tenant("tid-1", reason="policy violation")
        assert tenant is not None

    async def test_delete_not_found(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        repo = _make_repo(session)
        result = await repo.delete_tenant("nonexistent")
        assert result is False

    async def test_delete_success(self):
        session = _make_mock_session()
        orm = _make_mock_orm()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = orm
        session.execute.return_value = mock_result

        repo = _make_repo(session)
        result = await repo.delete_tenant("tid-1")
        assert result is True
        session.delete.assert_awaited_once()
        session.commit.assert_awaited_once()

    async def test_delete_with_cache(self):
        session = _make_mock_session()
        orm = _make_mock_orm()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = orm
        session.execute.return_value = mock_result

        repo = _make_repo(session)
        mock_cache = AsyncMock()
        repo._tenant_cache = mock_cache

        result = await repo.delete_tenant("tid-1")
        assert result is True
        assert mock_cache.delete.await_count >= 1


class TestCountTenants:
    """Test count_tenants and count_tenants_by_parent."""

    async def test_count_no_filter(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 5
        session.execute.return_value = mock_result

        repo = _make_repo(session)
        count = await repo.count_tenants()
        assert count == 5

    async def test_count_with_status(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 3
        session.execute.return_value = mock_result

        from enhanced_agent_bus.multi_tenancy.models import TenantStatus

        repo = _make_repo(session)
        count = await repo.count_tenants(status=TenantStatus.ACTIVE)
        assert count == 3

    async def test_count_returns_zero_on_none(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        session.execute.return_value = mock_result

        repo = _make_repo(session)
        count = await repo.count_tenants()
        assert count == 0

    async def test_count_by_parent(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 2
        session.execute.return_value = mock_result

        repo = _make_repo(session)
        count = await repo.count_tenants_by_parent(parent_tenant_id="tid-1")
        assert count == 2

    async def test_count_by_parent_none(self):
        session = _make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 10
        session.execute.return_value = mock_result

        repo = _make_repo(session)
        count = await repo.count_tenants_by_parent(parent_tenant_id=None)
        assert count == 10


class TestProjectionDTOs:
    """Test TenantSummary and TenantHierarchyNode dataclasses."""

    def test_tenant_summary(self):
        from enhanced_agent_bus.multi_tenancy.db_repository_optimized import (
            TenantSummary,
        )

        now = datetime.now(UTC)
        s = TenantSummary(tenant_id="t1", name="Test", slug="test", status="active", created_at=now)
        assert s.tenant_id == "t1"
        assert s.name == "Test"

    def test_tenant_hierarchy_node(self):
        from enhanced_agent_bus.multi_tenancy.db_repository_optimized import (
            TenantHierarchyNode,
        )

        now = datetime.now(UTC)
        n = TenantHierarchyNode(
            tenant_id="t1",
            name="Parent",
            slug="parent",
            status="active",
            parent_tenant_id=None,
            child_count=3,
            created_at=now,
        )
        assert n.child_count == 3
        assert n.parent_tenant_id is None
