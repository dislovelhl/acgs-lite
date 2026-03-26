"""
Tests for enhanced_agent_bus.deliberation_layer.tensorrt_optimizer

Covers TensorRTOptimizer initialization, status, inference paths,
fallback logic, validation, and module-level helper functions.
All external dependencies (torch, onnx, tensorrt, transformers, numpy)
are mocked so tests run without GPU or ML libraries installed.
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers to control module-level availability flags
# ---------------------------------------------------------------------------


def _patch_availability(**overrides):
    """Return a dict suitable for patching module-level flags."""
    defaults = {
        "NUMPY_AVAILABLE": True,
        "TORCH_AVAILABLE": False,
        "ONNX_AVAILABLE": False,
        "TENSORRT_AVAILABLE": False,
        "RUST_AVAILABLE": False,
    }
    defaults.update(overrides)
    return defaults


MOD = "enhanced_agent_bus.deliberation_layer.tensorrt_optimizer"


# ---------------------------------------------------------------------------
# Initialization & status
# ---------------------------------------------------------------------------


class TestTensorRTOptimizerInit:
    """Tests for __init__ and property accessors."""

    def test_default_init(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        assert opt.model_name == "distilbert-base-uncased"
        assert opt.max_seq_length == 128
        assert opt.use_fp16 is True
        assert opt.cache_dir == tmp_path

    def test_custom_init(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(
            model_name="bert-base-cased",
            max_seq_length=256,
            use_fp16=False,
            cache_dir=tmp_path,
        )
        assert opt.model_name == "bert-base-cased"
        assert opt.max_seq_length == 256
        assert opt.use_fp16 is False

    def test_model_id_sanitization(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(model_name="org/my-model", cache_dir=tmp_path)
        assert opt.model_id == "org_my_model"
        assert opt.onnx_path == tmp_path / "org_my_model.onnx"
        assert opt.trt_path == tmp_path / "org_my_model.trt"

    def test_cache_dir_created(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        sub = tmp_path / "nested" / "dir"
        assert not sub.exists()
        TensorRTOptimizer(cache_dir=sub)
        assert sub.exists()

    def test_status_property(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        status = opt.status
        assert "model_name" in status
        assert "max_seq_length" in status
        assert "use_fp16" in status
        assert "torch_available" in status
        assert "onnx_available" in status
        assert "tensorrt_available" in status
        assert status["active_backend"] == "none"

    def test_optimization_status_detects_existing_files(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        # Pre-create model files
        (tmp_path / "distilbert_base_uncased.onnx").touch()
        (tmp_path / "distilbert_base_uncased.trt").touch()

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        assert opt._optimization_status["onnx_exported"] is True
        assert opt._optimization_status["tensorrt_ready"] is True


# ---------------------------------------------------------------------------
# Fallback embeddings
# ---------------------------------------------------------------------------


class TestFallbackEmbeddings:
    """Tests for _generate_fallback_embeddings."""

    def test_fallback_shape(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        result = opt._generate_fallback_embeddings(3)
        assert result.shape == (3, 768)
        assert result.dtype == np.float32
        np.testing.assert_array_equal(result, np.zeros((3, 768), dtype=np.float32))

    def test_fallback_single(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        result = opt._generate_fallback_embeddings(1)
        assert result.shape == (1, 768)

    @patch(f"{MOD}.NUMPY_AVAILABLE", False)
    def test_fallback_without_numpy_raises(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with pytest.raises(ImportError, match="numpy"):
            opt._generate_fallback_embeddings(1)


# ---------------------------------------------------------------------------
# export_onnx
# ---------------------------------------------------------------------------


class TestExportOnnx:
    """Tests for ONNX export logic."""

    def test_export_returns_existing_path(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt.onnx_path.touch()

        result = opt.export_onnx(force=False)
        assert result == opt.onnx_path
        assert opt._optimization_status["onnx_exported"] is True

    @patch(f"{MOD}.TORCH_AVAILABLE", False)
    def test_export_raises_without_torch(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with pytest.raises(RuntimeError, match="PyTorch required"):
            opt.export_onnx(force=True)

    @patch(f"{MOD}.TORCH_AVAILABLE", False)
    def test_export_no_torch_even_without_force(self, tmp_path):
        """When file doesn't exist and torch unavailable, should raise."""
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with pytest.raises(RuntimeError, match="PyTorch required"):
            opt.export_onnx()


# ---------------------------------------------------------------------------
# convert_to_tensorrt
# ---------------------------------------------------------------------------


class TestConvertToTensorRT:
    """Tests for TensorRT conversion logic."""

    @patch(f"{MOD}.TENSORRT_AVAILABLE", False)
    def test_returns_none_without_tensorrt(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        assert opt.convert_to_tensorrt() is None

    @patch(f"{MOD}.TENSORRT_AVAILABLE", True)
    def test_returns_existing_trt_path(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt.trt_path.touch()

        result = opt.convert_to_tensorrt(force=False)
        assert result == opt.trt_path
        assert opt._optimization_status["tensorrt_ready"] is True


# ---------------------------------------------------------------------------
# load_tensorrt_engine
# ---------------------------------------------------------------------------


class TestLoadTensorRTEngine:
    """Tests for TensorRT engine loading."""

    @patch(f"{MOD}.TENSORRT_AVAILABLE", False)
    def test_returns_false_without_tensorrt(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        assert opt.load_tensorrt_engine() is False

    @patch(f"{MOD}.TENSORRT_AVAILABLE", True)
    def test_returns_false_missing_file(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        assert opt.load_tensorrt_engine() is False

    @patch(f"{MOD}.TENSORRT_AVAILABLE", True)
    def test_returns_false_validation_failure(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt.trt_path.touch()

        with patch.object(opt, "validate_engine", return_value=False):
            assert opt.load_tensorrt_engine() is False


# ---------------------------------------------------------------------------
# validate_engine
# ---------------------------------------------------------------------------


class TestValidateEngine:
    """Tests for engine validation."""

    def test_nonexistent_path(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        assert opt.validate_engine(tmp_path / "nonexistent.trt") is False

    @patch(f"{MOD}.TENSORRT_AVAILABLE", False)
    def test_returns_false_without_tensorrt(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        engine_file = tmp_path / "test.trt"
        engine_file.write_bytes(b"x" * (2 * 1024 * 1024))
        assert opt.validate_engine(engine_file) is False

    @patch(f"{MOD}.TENSORRT_AVAILABLE", True)
    def test_too_small_file(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        engine_file = tmp_path / "small.trt"
        engine_file.write_bytes(b"x" * 100)
        # File is < 1MB so should return False before reaching trt calls
        assert opt.validate_engine(engine_file) is False


# ---------------------------------------------------------------------------
# load_onnx_runtime
# ---------------------------------------------------------------------------


class TestLoadOnnxRuntime:
    """Tests for ONNX Runtime fallback loading."""

    @patch(f"{MOD}.ONNX_AVAILABLE", False)
    def test_returns_false_without_onnx(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        assert opt.load_onnx_runtime() is False

    @patch(f"{MOD}.ONNX_AVAILABLE", True)
    def test_returns_false_missing_model(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        assert opt.load_onnx_runtime() is False

    @patch(f"{MOD}.ONNX_AVAILABLE", True)
    @patch(f"{MOD}.ort")
    def test_loads_with_cpu_provider(self, mock_ort, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt.onnx_path.touch()

        mock_ort.get_available_providers.return_value = ["CPUExecutionProvider"]
        mock_session = MagicMock()
        mock_ort.InferenceSession.return_value = mock_session

        result = opt.load_onnx_runtime()
        assert result is True
        assert opt._optimization_status["active_backend"] == "onnxruntime"
        assert opt._onnx_session is mock_session

        # Verify providers list passed correctly (no CUDA)
        call_args = mock_ort.InferenceSession.call_args
        providers = call_args[1]["providers"]
        assert providers == ["CPUExecutionProvider"]

    @patch(f"{MOD}.ONNX_AVAILABLE", True)
    @patch(f"{MOD}.ort")
    def test_loads_with_cuda_provider(self, mock_ort, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt.onnx_path.touch()

        mock_ort.get_available_providers.return_value = [
            "CUDAExecutionProvider",
            "CPUExecutionProvider",
        ]
        mock_ort.InferenceSession.return_value = MagicMock()

        result = opt.load_onnx_runtime()
        assert result is True

        call_args = mock_ort.InferenceSession.call_args
        providers = call_args[1]["providers"]
        assert "CUDAExecutionProvider" in providers
        assert "CPUExecutionProvider" in providers


# ---------------------------------------------------------------------------
# infer / infer_batch
# ---------------------------------------------------------------------------


class TestInfer:
    """Tests for inference methods."""

    @patch(f"{MOD}.NUMPY_AVAILABLE", False)
    def test_infer_raises_without_numpy(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with pytest.raises(ImportError, match="numpy"):
            opt.infer("hello")

    @patch(f"{MOD}.NUMPY_AVAILABLE", False)
    def test_infer_batch_raises_without_numpy(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with pytest.raises(ImportError, match="numpy"):
            opt.infer_batch(["hello"])

    def test_infer_delegates_to_infer_batch(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        fake_result = np.array([[0.1, 0.2], [0.3, 0.4]])

        with patch.object(opt, "infer_batch", return_value=fake_result) as mock_batch:
            result = opt.infer("hello")
            mock_batch.assert_called_once_with(["hello"])
            np.testing.assert_array_equal(result, fake_result[0])

    def test_infer_batch_fallback_on_exception(self, tmp_path):
        """When _infer_torch raises, should return fallback embeddings."""
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt._trt_context = None
        opt._onnx_session = None

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.zeros((1, 128), dtype=np.int64),
            "attention_mask": np.ones((1, 128), dtype=np.int64),
        }

        with (
            patch.object(opt, "_load_tokenizer", return_value=mock_tokenizer),
            patch.object(opt, "_infer_torch", side_effect=RuntimeError("no model")),
        ):
            # Set a very high threshold so timeout check doesn't trigger
            opt._latency_threshold_ms = 100000.0
            result = opt.infer_batch(["test text"])

        assert result.shape == (1, 768)
        np.testing.assert_array_equal(result, np.zeros((1, 768), dtype=np.float32))

    def test_infer_batch_timeout_returns_fallback(self, tmp_path):
        """When latency threshold exceeded, should return fallback."""
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt._trt_context = None
        opt._onnx_session = None
        # Set impossibly low threshold so timeout triggers immediately
        opt._latency_threshold_ms = 0.0001

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.zeros((2, 128), dtype=np.int64),
            "attention_mask": np.ones((2, 128), dtype=np.int64),
        }

        with patch.object(opt, "_load_tokenizer", return_value=mock_tokenizer):
            result = opt.infer_batch(["text1", "text2"])

        assert result.shape == (2, 768)
        np.testing.assert_array_equal(result, np.zeros((2, 768), dtype=np.float32))

    def test_infer_batch_uses_onnx_session(self, tmp_path):
        """When _onnx_session is set, should use _infer_onnx."""
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt._trt_context = None
        opt._onnx_session = MagicMock()  # non-None triggers ONNX path
        opt._latency_threshold_ms = 100000.0

        expected = np.ones((1, 768), dtype=np.float32)

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.zeros((1, 128), dtype=np.int64),
            "attention_mask": np.ones((1, 128), dtype=np.int64),
        }

        with (
            patch.object(opt, "_load_tokenizer", return_value=mock_tokenizer),
            patch.object(opt, "_infer_onnx", return_value=expected) as mock_onnx,
        ):
            result = opt.infer_batch(["hello"])

        mock_onnx.assert_called_once()
        np.testing.assert_array_equal(result, expected)

    def test_infer_batch_uses_trt_context(self, tmp_path):
        """When _trt_context is set, should use _infer_tensorrt."""
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt._trt_context = MagicMock()  # non-None triggers TRT path
        opt._latency_threshold_ms = 100000.0

        expected = np.ones((1, 768), dtype=np.float32)

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.zeros((1, 128), dtype=np.int64),
            "attention_mask": np.ones((1, 128), dtype=np.int64),
        }

        with (
            patch.object(opt, "_load_tokenizer", return_value=mock_tokenizer),
            patch.object(opt, "_infer_tensorrt", return_value=expected) as mock_trt,
        ):
            result = opt.infer_batch(["hello"])

        mock_trt.assert_called_once()
        np.testing.assert_array_equal(result, expected)


# ---------------------------------------------------------------------------
# _infer_tensorrt
# ---------------------------------------------------------------------------


class TestInferTensorRT:
    """Tests for TensorRT inference stub."""

    def test_raises_not_implemented(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with pytest.raises(NotImplementedError, match="CUDA setup"):
            opt._infer_tensorrt({"input_ids": np.zeros((1, 128))})


# ---------------------------------------------------------------------------
# _infer_onnx
# ---------------------------------------------------------------------------


class TestInferOnnx:
    """Tests for ONNX inference path."""

    @patch(f"{MOD}.NUMPY_AVAILABLE", False)
    def test_raises_without_numpy(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with pytest.raises(ImportError, match="numpy"):
            opt._infer_onnx({})

    def test_raises_without_session(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt._onnx_session = None
        with pytest.raises(RuntimeError, match="ONNX session not loaded"):
            opt._infer_onnx({})


# ---------------------------------------------------------------------------
# _infer_torch
# ---------------------------------------------------------------------------


class TestInferTorch:
    """Tests for PyTorch fallback inference."""

    @patch(f"{MOD}.NUMPY_AVAILABLE", False)
    def test_raises_without_numpy(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with pytest.raises(ImportError, match="numpy"):
            opt._infer_torch({})

    @patch(f"{MOD}.TORCH_AVAILABLE", False)
    def test_raises_without_torch(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with pytest.raises(RuntimeError, match="PyTorch not available"):
            opt._infer_torch(
                {
                    "input_ids": np.zeros((1, 128), dtype=np.int64),
                    "attention_mask": np.ones((1, 128), dtype=np.int64),
                }
            )


# ---------------------------------------------------------------------------
# _load_tokenizer
# ---------------------------------------------------------------------------


class TestLoadTokenizer:
    """Tests for tokenizer loading with cache."""

    def test_caches_tokenizer(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        mock_tok = MagicMock()

        # Pre-populate cache so _load_tokenizer skips the import
        opt._tokenizer_cache["distilbert-base-uncased"] = mock_tok
        result = opt._load_tokenizer()
        assert result is mock_tok

    def test_cache_hit_returns_same_object(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        sentinel = object()
        opt._tokenizer_cache["distilbert-base-uncased"] = sentinel

        assert opt._load_tokenizer() is sentinel
        # Second call same result
        assert opt._load_tokenizer() is sentinel


# ---------------------------------------------------------------------------
# _load_torch_model
# ---------------------------------------------------------------------------


class TestLoadTorchModel:
    """Tests for torch model loading."""

    @patch(f"{MOD}.TORCH_AVAILABLE", False)
    def test_raises_without_torch(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with pytest.raises(RuntimeError, match="PyTorch not available"):
            opt._load_torch_model()

    def test_returns_cached_model(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        sentinel = object()
        opt._torch_model = sentinel

        assert opt._load_torch_model() is sentinel


# ---------------------------------------------------------------------------
# Module-level functions
# ---------------------------------------------------------------------------


class TestModuleFunctions:
    """Tests for get_optimization_status and optimize_distilbert."""

    def test_get_optimization_status(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            get_optimization_status,
        )

        with patch(
            f"{MOD}.TensorRTOptimizer.DEFAULT_MODEL_DIR",
            tmp_path,
        ):
            status = get_optimization_status()

        assert isinstance(status, dict)
        assert "model_name" in status
        assert status["model_name"] == "distilbert-base-uncased"

    @patch(f"{MOD}.TENSORRT_AVAILABLE", False)
    def test_optimize_distilbert_onnx_error(self, tmp_path):
        """When export_onnx fails, should return early with error."""
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            optimize_distilbert,
        )

        with patch(
            f"{MOD}.TensorRTOptimizer.DEFAULT_MODEL_DIR",
            tmp_path,
        ):
            with patch(
                f"{MOD}.TensorRTOptimizer.export_onnx",
                side_effect=RuntimeError("no torch"),
            ):
                result = optimize_distilbert()

        assert "onnx_error" in result
        assert "no torch" in result["onnx_error"]
        assert "onnx_export" not in result["steps_completed"]

    @patch(f"{MOD}.TENSORRT_AVAILABLE", False)
    def test_optimize_distilbert_skips_tensorrt(self, tmp_path):
        """When TensorRT unavailable, should note skip."""
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            optimize_distilbert,
        )

        mock_onnx_path = tmp_path / "test.onnx"

        with patch(
            f"{MOD}.TensorRTOptimizer.DEFAULT_MODEL_DIR",
            tmp_path,
        ):
            with patch(
                f"{MOD}.TensorRTOptimizer.export_onnx",
                return_value=mock_onnx_path,
            ):
                with patch(
                    f"{MOD}.TensorRTOptimizer.load_tensorrt_engine",
                    return_value=False,
                ):
                    with patch(
                        f"{MOD}.TensorRTOptimizer.load_onnx_runtime",
                        return_value=False,
                    ):
                        with patch(
                            f"{MOD}.TensorRTOptimizer.benchmark",
                            side_effect=RuntimeError("no backend"),
                        ):
                            result = optimize_distilbert()

        assert result["tensorrt_skipped"] == "TensorRT not available"
        assert "onnx_export" in result["steps_completed"]
        assert result["active_backend"] == "pytorch"
        assert "benchmark_error" in result

    @patch(f"{MOD}.TENSORRT_AVAILABLE", False)
    def test_optimize_distilbert_onnx_runtime_backend(self, tmp_path):
        """When ONNX Runtime loads, active_backend should be onnxruntime."""
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            optimize_distilbert,
        )

        mock_onnx_path = tmp_path / "test.onnx"
        mock_benchmark = {
            "backend": "onnxruntime",
            "num_samples": 50,
            "latency_p50_ms": 1.0,
            "latency_p95_ms": 2.0,
            "latency_p99_ms": 3.0,
            "latency_mean_ms": 1.5,
            "latency_min_ms": 0.5,
            "latency_max_ms": 5.0,
        }

        with patch(
            f"{MOD}.TensorRTOptimizer.DEFAULT_MODEL_DIR",
            tmp_path,
        ):
            with patch(
                f"{MOD}.TensorRTOptimizer.export_onnx",
                return_value=mock_onnx_path,
            ):
                with patch(
                    f"{MOD}.TensorRTOptimizer.load_tensorrt_engine",
                    return_value=False,
                ):
                    with patch(
                        f"{MOD}.TensorRTOptimizer.load_onnx_runtime",
                        return_value=True,
                    ):
                        with patch(
                            f"{MOD}.TensorRTOptimizer.benchmark",
                            return_value=mock_benchmark,
                        ):
                            result = optimize_distilbert()

        assert result["active_backend"] == "onnxruntime"
        assert "benchmark" in result
        assert "benchmark" in result["steps_completed"]


# ---------------------------------------------------------------------------
# benchmark
# ---------------------------------------------------------------------------


class TestBenchmark:
    """Tests for benchmark method."""

    def test_benchmark_returns_expected_keys(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        # Mock infer to return fast dummy results
        with patch.object(
            opt,
            "infer",
            return_value=np.zeros((768,), dtype=np.float32),
        ):
            result = opt.benchmark(num_samples=20)

        expected_keys = {
            "backend",
            "num_samples",
            "latency_p50_ms",
            "latency_p95_ms",
            "latency_p99_ms",
            "latency_mean_ms",
            "latency_min_ms",
            "latency_max_ms",
        }
        assert set(result.keys()) == expected_keys
        assert result["num_samples"] == 20
        assert result["backend"] == "none"
        assert result["latency_mean_ms"] >= 0
        assert result["latency_min_ms"] <= result["latency_max_ms"]

    def test_benchmark_warmup_runs(self, tmp_path):
        from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
            TensorRTOptimizer,
        )

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        call_count = 0

        def counting_infer(text):
            nonlocal call_count
            call_count += 1
            return np.zeros((768,), dtype=np.float32)

        with patch.object(opt, "infer", side_effect=counting_infer):
            opt.benchmark(num_samples=5)

        # 10 warmup + 5 benchmark = 15 total
        assert call_count == 15
