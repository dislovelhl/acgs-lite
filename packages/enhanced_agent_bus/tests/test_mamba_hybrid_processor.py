"""Tests for Constitutional Mamba-2 Hybrid Processor."""

import pytest

from enhanced_agent_bus.context.mamba_hybrid import (  # noqa: E402
    CONSTITUTIONAL_HASH,
    TORCH_AVAILABLE,
    ConstitutionalContextProcessor,
    ConstitutionalMambaHybrid,
    Mamba2SSM,
    SharedAttentionLayer,
)

if not TORCH_AVAILABLE:
    pytest.skip("torch-backed mamba hybrid unavailable", allow_module_level=True)

import torch  # noqa: E402


class TestMamba2SSM:
    # Constitutional Hash: cdd01ef066bc6cf2
    """Test Mamba-2 SSM layer."""

    def test_initialization(self):
        """Test SSM layer initialization."""
        d_model = 256
        d_state = 64
        ssm = Mamba2SSM(d_model=d_model, d_state=d_state)

        assert ssm.d_model == d_model
        assert ssm.d_state == d_state

    def test_forward_pass(self):
        """Test forward pass through SSM layer."""
        batch, seq_len, d_model = 2, 50, 256
        ssm = Mamba2SSM(d_model=d_model)

        x = torch.randn(batch, seq_len, d_model)
        output = ssm(x)

        assert output.shape == x.shape
        assert not torch.isnan(output).any()


class TestSharedAttentionLayer:
    """Test shared attention layer."""

    def test_initialization(self):
        """Test attention layer initialization."""
        d_model = 256
        num_heads = 8
        attn = SharedAttentionLayer(d_model=d_model, num_heads=num_heads)

        assert attn.d_model == d_model
        assert attn.num_heads == num_heads

    def test_forward_pass(self):
        """Test forward pass through attention layer."""
        batch, seq_len, d_model = 2, 50, 256
        attn = SharedAttentionLayer(d_model=d_model)

        x = torch.randn(batch, seq_len, d_model)
        output = attn(x)

        assert output.shape == x.shape
        assert not torch.isnan(output).any()


class TestConstitutionalMambaHybrid:
    """Test Constitutional Mamba Hybrid model."""

    def test_initialization(self):
        """Test model initialization."""
        d_model = 256
        num_layers = 3
        model = ConstitutionalMambaHybrid(d_model=d_model, num_mamba_layers=num_layers)

        assert model.d_model == d_model
        assert len(model.mamba_layers) == num_layers
        assert model.constitutional_hash == CONSTITUTIONAL_HASH

    def test_forward_pass(self):
        """Test full forward pass."""
        model = ConstitutionalMambaHybrid(d_model=256, num_mamba_layers=2)
        batch, seq_len, d_model = 1, 50, 256

        x = torch.randn(batch, seq_len, d_model)
        output = model(x)

        assert output.shape == x.shape
        assert not torch.isnan(output).any()

    def test_constitutional_hash(self):
        """Test constitutional hash retrieval."""
        model = ConstitutionalMambaHybrid()
        assert model.get_constitutional_hash() == CONSTITUTIONAL_HASH


class TestConstitutionalContextProcessor:
    """Test high-level context processor."""

    def test_initialization(self):
        """Test processor initialization."""
        processor = ConstitutionalContextProcessor()
        assert processor.model is not None
        assert processor.model.constitutional_hash == CONSTITUTIONAL_HASH

    def test_tokenize(self):
        """Test tokenization."""
        processor = ConstitutionalContextProcessor()
        text = "Hello World"

        tokens = processor._tokenize(text)
        assert len(tokens) == len(text)
        assert all(0 <= t <= 1 for t in tokens)

    def test_process_constitutional_context(self):
        """Test context processing."""
        processor = ConstitutionalContextProcessor()
        context = "This is a test constitutional context."
        critical_principles = ["constitutional"]

        result = processor.process_constitutional_context(context, critical_principles)

        assert "embeddings" in result
        assert "critical_positions" in result
        assert "context_length" in result
        assert "constitutional_hash" in result
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_validate_constitutional_compliance(self):
        """Test compliance validation."""
        processor = ConstitutionalContextProcessor()
        decision_context = "Approve this governance action"
        constitutional_principles = ["All actions must be constitutional"]

        score = processor.validate_constitutional_compliance(
            decision_context, constitutional_principles
        )

        assert 0.0 <= score <= 1.0


if __name__ == "__main__":
    pytest.main([__file__])
