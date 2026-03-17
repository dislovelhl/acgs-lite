"""
Tests for Constitutional Mamba-2 Hybrid Processor
Constitutional Hash: cdd01ef066bc6cf2

Tests the breakthrough Mamba-2 hybrid architecture for 4M+ token context processing.
"""

import os
import sys

import pytest
import torch

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mamba_hybrid_processor import (
    CONSTITUTIONAL_HASH,
    ConstitutionalMambaHybrid,
    MambaConfig,
    MambaHybridManager,
    MambaSSM,
    SharedAttentionLayer,
    get_mamba_hybrid_processor,
    initialize_mamba_processor,
)


class TestMambaConfig:
    """Test Mamba configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = MambaConfig()

        assert config.d_model == 512
        assert config.d_state == 128
        assert config.num_mamba_layers == 6
        assert config.max_context_length == 4_000_000
        assert config.use_shared_attention
        assert config.jrt_enabled
        assert config.critical_sections_repeat == 3
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_config(self):
        """Test custom configuration."""
        config = MambaConfig(
            d_model=256,
            num_mamba_layers=4,
            max_context_length=1_000_000,
            use_shared_attention=False,
        )

        assert config.d_model == 256
        assert config.num_mamba_layers == 4
        assert config.max_context_length == 1_000_000
        assert not config.use_shared_attention


class TestMambaSSM:
    """Test Mamba SSM layer."""

    @pytest.fixture
    def config(self):
        return MambaConfig(d_model=64, d_state=32, device="cpu", dtype=torch.float32)

    @pytest.fixture
    def ssm_layer(self, config):
        return MambaSSM(config)

    def test_initialization(self, ssm_layer, config):
        """Test SSM layer initialization."""
        assert ssm_layer.d_model == config.d_model
        assert ssm_layer.d_state == config.d_state
        assert ssm_layer.expand == config.expand
        assert ssm_layer.d_inner == config.expand * config.d_model

    def test_forward_pass(self, ssm_layer):
        """Test forward pass through SSM layer."""
        batch_size, seq_len, d_model = 2, 10, 64
        x = torch.randn(batch_size, seq_len, d_model)

        output = ssm_layer(x)

        assert output.shape == (batch_size, seq_len, d_model)
        assert not torch.isnan(output).any()
        assert not torch.isinf(output).any()


class TestSharedAttentionLayer:
    """Test shared attention layer."""

    @pytest.fixture
    def config(self):
        return MambaConfig(d_model=64, device="cpu", dtype=torch.float32)

    @pytest.fixture
    def attention_layer(self, config):
        return SharedAttentionLayer(config)

    def test_initialization(self, attention_layer, config):
        """Test attention layer initialization."""
        assert attention_layer.d_model == config.d_model
        assert attention_layer.num_heads == 8
        assert attention_layer.head_dim == config.d_model // 8

    def test_forward_pass(self, attention_layer):
        """Test forward pass through attention layer."""
        batch_size, seq_len, d_model = 2, 10, 64
        x = torch.randn(batch_size, seq_len, d_model)

        output = attention_layer(x)

        assert output.shape == (batch_size, seq_len, d_model)
        assert not torch.isnan(output).any()
        assert not torch.isinf(output).any()


class TestConstitutionalMambaHybrid:
    """Test the main hybrid processor."""

    @pytest.fixture
    def config(self):
        return MambaConfig(
            d_model=64,
            num_mamba_layers=2,  # Reduced for testing
            device="cpu",
            dtype=torch.float32,
        )

    @pytest.fixture
    def processor(self, config):
        return ConstitutionalMambaHybrid(config)

    def test_initialization(self, processor, config):
        """Test processor initialization."""
        assert len(processor.mamba_layers) == config.num_mamba_layers
        assert processor.shared_attention is not None
        assert processor.jrt_enabled == config.jrt_enabled
        assert processor.constitutional_hash == CONSTITUTIONAL_HASH

    def test_forward_pass_basic(self, processor):
        """Test basic forward pass."""
        batch_size, seq_len, d_model = 1, 20, 64
        x = torch.randn(batch_size, seq_len, d_model)

        output = processor(x)

        assert output.shape == (batch_size, seq_len, d_model)
        assert not torch.isnan(output).any()

    def test_jrt_context_preparation(self, processor):
        """Test JRT context preparation."""
        batch_size, seq_len, d_model = 1, 10, 64
        x = torch.randn(batch_size, seq_len, d_model)
        critical_positions = [2, 5, 8]

        prepared = processor._prepare_jrt_context(x, critical_positions)

        # Should have more tokens due to repetition
        assert prepared.shape[1] > seq_len

    def test_critical_position_identification(self, processor):
        """Test critical position identification."""
        batch_size, seq_len = 1, 100
        input_ids = torch.randint(0, 1000, (batch_size, seq_len))

        positions = processor._identify_critical_positions(input_ids)

        assert isinstance(positions, list)
        assert len(positions) > 0
        assert all(isinstance(p, int) for p in positions)

    def test_memory_usage_reporting(self, processor):
        """Test memory usage reporting."""
        usage = processor.get_memory_usage()

        assert "model_memory_mb" in usage
        assert "max_context_tokens" in usage
        assert "constitutional_hash" in usage
        assert usage["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert usage["max_context_tokens"] == 4_000_000

    def test_long_context_handling(self, processor):
        """Test handling of long contexts."""
        batch_size, seq_len, d_model = 1, 1000, 64
        x = torch.randn(batch_size, seq_len, d_model)

        output = processor(x)

        assert output.shape == (batch_size, seq_len, d_model)


class TestMambaHybridManager:
    """Test the processor manager."""

    @pytest.fixture
    def config(self):
        return MambaConfig(
            d_model=32,  # Very small for testing
            num_mamba_layers=1,
            device="cpu",
            dtype=torch.float32,
        )

    @pytest.fixture
    def manager(self, config):
        return MambaHybridManager(config)

    def test_initialization(self, manager, config):
        """Test manager initialization."""
        assert not manager.is_loaded
        assert manager.model is None
        assert manager.config == config

    def test_model_loading(self, manager):
        """Test model loading."""
        success = manager.load_model()

        assert success
        assert manager.is_loaded
        assert manager.model is not None
        assert isinstance(manager.model, ConstitutionalMambaHybrid)

    def test_context_processing(self, manager):
        """Test context processing through manager."""
        manager.load_model()

        batch_size, seq_len, d_model = 1, 10, 32
        input_tensor = torch.randn(batch_size, seq_len, d_model)

        output = manager.process_context(input_tensor)

        assert output.shape == (batch_size, seq_len, d_model)

    def test_model_info(self, manager):
        """Test model information retrieval."""
        info = manager.get_model_info()

        assert info["status"] == "not_loaded"

        manager.load_model()
        info = manager.get_model_info()

        assert info["status"] == "loaded"
        assert info["architecture"] == "Constitutional Mamba Hybrid"
        assert info["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "capabilities" in info
        assert "memory_usage" in info

    def test_model_unloading(self, manager):
        """Test model unloading."""
        manager.load_model()
        assert manager.is_loaded

        manager.unload_model()
        assert not manager.is_loaded
        assert manager.model is None


class TestGlobalFunctions:
    """Test global utility functions."""

    def test_get_mamba_hybrid_processor(self):
        """Test global processor getter."""
        processor = get_mamba_hybrid_processor()
        assert isinstance(processor, MambaHybridManager)

    def test_initialize_mamba_processor(self):
        """Test global initialization function."""
        config = MambaConfig(d_model=32, num_mamba_layers=1, device="cpu", dtype=torch.float32)
        success = initialize_mamba_processor(config)

        assert success

        # Check global instance was updated
        global_processor = get_mamba_hybrid_processor()
        assert global_processor.is_loaded


class TestIntegration:
    """Integration tests for the full system."""

    def test_end_to_end_processing(self):
        """Test end-to-end context processing."""
        config = MambaConfig(d_model=64, num_mamba_layers=2, device="cpu", dtype=torch.float32)

        manager = MambaHybridManager(config)
        manager.load_model()

        # Simulate processing a large context
        batch_size, seq_len, d_model = 1, 100, 64
        input_tensor = torch.randn(batch_size, seq_len, d_model)
        input_ids = torch.randint(0, 1000, (batch_size, seq_len))

        output = manager.process_context(
            input_tensor=input_tensor, input_ids=input_ids, use_attention=True
        )

        assert output.shape == (batch_size, seq_len, d_model)
        assert not torch.isnan(output).any()

    def test_memory_efficiency(self):
        """Test memory efficiency features."""
        config = MambaConfig(
            d_model=128, max_context_length=1_000_000, device="cpu", dtype=torch.float32
        )

        processor = ConstitutionalMambaHybrid(config)

        # Test memory usage reporting
        usage = processor.get_memory_usage()
        assert usage["max_context_tokens"] == 1_000_000

        # Test memory efficient mode
        processor.enable_memory_efficient_mode()

        # Test memory cache reset
        processor.reset_memory_cache()


class TestConstitutionalCompliance:
    """Test constitutional compliance features."""

    def test_constitutional_hash_integration(self):
        """Test that constitutional hash is properly integrated."""
        config = MambaConfig()
        processor = ConstitutionalMambaHybrid(config)

        assert processor.constitutional_hash == CONSTITUTIONAL_HASH

        usage = processor.get_memory_usage()
        assert usage["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_constitutional_validation(self):
        """Test constitutional validation in processing."""
        config = MambaConfig()
        processor = ConstitutionalMambaHybrid(config)

        # Ensure processing maintains constitutional compliance
        batch_size, seq_len, d_model = 1, 50, 512
        x = torch.randn(batch_size, seq_len, d_model)

        output = processor(x)

        # Output should be valid (not NaN, finite)
        assert torch.isfinite(output).all()
        assert not torch.isnan(output).any()


if __name__ == "__main__":
    # Run basic smoke tests

    config = MambaConfig(d_model=64, num_mamba_layers=2, device="cpu", dtype=torch.float32)
    processor = ConstitutionalMambaHybrid(config)

    # Test basic functionality
    batch_size, seq_len, d_model = 1, 20, 64
    x = torch.randn(batch_size, seq_len, d_model)

    output = processor(x)

    # Test JRT preparation
    prepared = processor._prepare_jrt_context(x, [5, 10, 15])

    # Test memory reporting
    usage = processor.get_memory_usage()
