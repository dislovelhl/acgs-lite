"""Tests for context/mamba_hybrid.py — Constitutional Mamba-2 Hybrid Processor.

Covers both the torch-available and torch-unavailable (stub) code paths.
"""

from __future__ import annotations

import pytest

from enhanced_agent_bus.context.mamba_hybrid import (
    TORCH_AVAILABLE,
    ConstitutionalContextProcessor,
    ConstitutionalMambaHybrid,
    Mamba2SSM,
    SharedAttentionLayer,
)

# ---------------------------------------------------------------------------
# Stub path tests (always run — stubs are always defined)
# ---------------------------------------------------------------------------


class TestStubsWhenTorchUnavailable:
    """When torch is NOT installed, the module exports lightweight stubs."""

    @pytest.mark.skipif(TORCH_AVAILABLE, reason="Stubs only exercised when torch missing")
    def test_constitutional_mamba_hybrid_stub_has_hash(self) -> None:
        model = ConstitutionalMambaHybrid()
        assert model.get_constitutional_hash() == "standalone" or isinstance(
            model.get_constitutional_hash(), str
        )

    @pytest.mark.skipif(TORCH_AVAILABLE, reason="Stubs only exercised when torch missing")
    def test_context_processor_stub_raises(self) -> None:
        with pytest.raises(RuntimeError, match="requires PyTorch"):
            ConstitutionalContextProcessor()


# ---------------------------------------------------------------------------
# Real implementation tests (require torch)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch required")
class TestMamba2SSM:
    def test_forward_shape(self) -> None:
        import torch

        model = Mamba2SSM(d_model=32, d_state=16, expand=2)
        x = torch.randn(2, 10, 32)
        out = model(x)
        assert out.shape == (2, 10, 32)

    def test_attributes(self) -> None:
        model = Mamba2SSM(d_model=64, d_state=32, expand=2)
        assert model.d_model == 64
        assert model.d_state == 32
        assert model.d_inner == 128


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch required")
class TestSharedAttentionLayer:
    def test_forward_shape_no_mask(self) -> None:
        import torch

        layer = SharedAttentionLayer(d_model=32, num_heads=4)
        x = torch.randn(1, 8, 32)
        out = layer(x)
        assert out.shape == (1, 8, 32)

    def test_forward_with_mask(self) -> None:
        import torch

        layer = SharedAttentionLayer(d_model=32, num_heads=4)
        x = torch.randn(1, 8, 32)
        mask = torch.ones(1, 1, 8, 8)
        out = layer(x, mask=mask)
        assert out.shape == (1, 8, 32)


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch required")
class TestConstitutionalMambaHybrid:
    def test_get_constitutional_hash(self) -> None:
        model = ConstitutionalMambaHybrid(d_model=32, d_state=16, num_mamba_layers=2)
        h = model.get_constitutional_hash()
        assert isinstance(h, str)
        assert len(h) > 0

    def test_forward_with_long_input(self) -> None:
        import torch

        model = ConstitutionalMambaHybrid(d_model=32, d_state=16, num_mamba_layers=3)
        x = torch.randint(0, 255, (1, 20))
        out = model(x)
        assert out.shape == (1, 20, 32)

    def test_forward_float_input(self) -> None:
        import torch

        model = ConstitutionalMambaHybrid(d_model=32, d_state=16, num_mamba_layers=2)
        x = torch.rand(1, 10)  # float 0-1
        out = model(x)
        assert out.shape == (1, 10, 32)

    def test_forward_3d_input(self) -> None:
        import torch

        model = ConstitutionalMambaHybrid(d_model=32, d_state=16, num_mamba_layers=2)
        x = torch.randn(1, 10, 32)  # already embedded
        out = model(x)
        assert out.shape == (1, 10, 32)

    def test_jrt_context_preparation_noop(self) -> None:
        import torch

        model = ConstitutionalMambaHybrid(d_model=32, d_state=16, num_mamba_layers=2)
        x = torch.randn(1, 5, 32)
        result = model._prepare_jrt_context(x, critical_positions=None)
        assert torch.equal(result, x)

    def test_jrt_context_preparation_empty_positions(self) -> None:
        import torch

        model = ConstitutionalMambaHybrid(d_model=32, d_state=16, num_mamba_layers=2)
        x = torch.randn(1, 5, 32)
        result = model._prepare_jrt_context(x, critical_positions=[])
        assert torch.equal(result, x)

    def test_quantize(self) -> None:
        model = ConstitutionalMambaHybrid(d_model=32, d_state=16, num_mamba_layers=2)
        # Should not raise
        model.quantize()

    def test_custom_hash(self) -> None:
        model = ConstitutionalMambaHybrid(
            d_model=32, d_state=16, num_mamba_layers=2, constitutional_hash="custom123"
        )
        assert model.get_constitutional_hash() == "custom123"


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch required")
class TestConstitutionalContextProcessor:
    def test_init_default(self) -> None:
        processor = ConstitutionalContextProcessor()
        assert processor.model is not None

    def test_tokenize(self) -> None:
        processor = ConstitutionalContextProcessor()
        tokens = processor._tokenize("ABC")
        assert len(tokens) == 3
        assert tokens[0] == ord("A") / 255.0

    def test_find_critical_positions_no_principles(self) -> None:
        processor = ConstitutionalContextProcessor()
        tokens = [0.1] * 200
        positions = processor._find_critical_positions(tokens, critical_principles=None)
        assert positions == list(range(100))

    def test_find_critical_positions_with_match(self) -> None:
        processor = ConstitutionalContextProcessor()
        text = "hello world"
        tokens = [ord(c) / 255.0 for c in text]
        positions = processor._find_critical_positions(tokens, critical_principles=["world"])
        assert len(positions) == 5  # len("world")

    def test_find_critical_positions_no_match(self) -> None:
        processor = ConstitutionalContextProcessor()
        tokens = [ord(c) / 255.0 for c in "hello"]
        positions = processor._find_critical_positions(tokens, critical_principles=["xyz"])
        assert positions == []

    def test_process_constitutional_context(self) -> None:
        processor = ConstitutionalContextProcessor()
        result = processor.process_constitutional_context("test input data")
        assert "embeddings" in result
        assert "context_length" in result
        assert "constitutional_hash" in result
        assert result["context_length"] == len("test input data")

    def test_validate_constitutional_compliance(self) -> None:
        processor = ConstitutionalContextProcessor()
        score = processor.validate_constitutional_compliance(
            "some governance decision context", ["governance"]
        )
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
