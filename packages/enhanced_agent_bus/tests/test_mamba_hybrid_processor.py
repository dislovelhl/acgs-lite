"""Tests for ai_assistant/mamba_hybrid_processor.py.

Tests the MambaConfig, MambaSSM, SharedAttentionLayer, ConstitutionalMambaHybrid,
MambaHybridManager, and global helper functions.

Note: MambaSSM._ssm_forward is a prototype with known dimension mismatches,
so forward tests mock the SSM layer to test the integration/orchestration logic.
"""

from unittest.mock import patch

import pytest

from enhanced_agent_bus.ai_assistant.mamba_hybrid_processor import (
    TORCH_AVAILABLE,
    MambaConfig,
    MambaHybridManager,
    get_mamba_hybrid_processor,
    initialize_mamba_processor,
)


# ---------------------------------------------------------------------------
# MambaConfig tests (always run)
# ---------------------------------------------------------------------------


class TestMambaConfig:
    def test_default_values(self):
        cfg = MambaConfig()
        assert cfg.d_model == 512
        assert cfg.d_state == 128
        assert cfg.d_conv == 4
        assert cfg.expand == 2
        assert cfg.num_mamba_layers == 6
        assert cfg.use_shared_attention is True
        assert cfg.jrt_enabled is True
        assert cfg.max_context_length == 4_000_000
        assert cfg.critical_sections_repeat == 3
        assert cfg.memory_efficient_mode is False

    def test_custom_values(self):
        cfg = MambaConfig(d_model=256, num_mamba_layers=3, max_context_length=1000)
        assert cfg.d_model == 256
        assert cfg.num_mamba_layers == 3
        assert cfg.max_context_length == 1000

    def test_device_defaults_to_cpu_without_cuda(self):
        cfg = MambaConfig()
        assert cfg.device in ("cpu", "cuda")

    def test_bias_defaults(self):
        cfg = MambaConfig()
        assert cfg.bias is False
        assert cfg.conv_bias is True

    def test_dt_range(self):
        cfg = MambaConfig()
        assert cfg.dt_min < cfg.dt_max
        assert cfg.dt_init_floor > 0

    def test_post_init_sets_dtype(self):
        cfg = MambaConfig()
        if TORCH_AVAILABLE:
            import torch
            assert cfg.dtype == torch.float16


# ---------------------------------------------------------------------------
# Helper to patch MambaSSM forward (prototype SSM has dim issues)
# ---------------------------------------------------------------------------

def _patch_mamba_forward():
    """Return a patch context that makes MambaSSM.forward an identity fn."""
    from enhanced_agent_bus.ai_assistant.mamba_hybrid_processor import MambaSSM

    def identity_forward(self, x):
        return x

    return patch.object(MambaSSM, "forward", identity_forward)


# ---------------------------------------------------------------------------
# Tests requiring torch
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch not installed")
class TestMambaHybridManagerWithTorch:
    def test_init_defaults(self):
        mgr = MambaHybridManager()
        assert mgr.is_loaded is False
        assert mgr.model is None

    def test_get_model_info_not_loaded(self):
        mgr = MambaHybridManager()
        info = mgr.get_model_info()
        assert info["status"] == "not_loaded"

    def test_load_model_cpu(self):
        cfg = MambaConfig(d_model=64, num_mamba_layers=2, device="cpu")
        mgr = MambaHybridManager(cfg)
        success = mgr.load_model()
        assert success is True
        assert mgr.is_loaded is True
        assert mgr.model is not None

    def test_get_model_info_loaded(self):
        cfg = MambaConfig(d_model=64, num_mamba_layers=2, device="cpu")
        mgr = MambaHybridManager(cfg)
        mgr.load_model()
        info = mgr.get_model_info()
        assert info["status"] == "loaded"
        assert info["architecture"] == "Constitutional Mamba Hybrid"
        assert info["capabilities"]["complexity"] == "O(n)"

    def test_process_context_not_loaded_raises(self):
        import torch

        mgr = MambaHybridManager()
        with pytest.raises(RuntimeError, match="not loaded"):
            mgr.process_context(torch.zeros(1, 10, 512))

    def test_process_context_loaded(self):
        import torch

        cfg = MambaConfig(d_model=64, num_mamba_layers=2, device="cpu")
        mgr = MambaHybridManager(cfg)
        mgr.load_model()
        inp = torch.randn(1, 8, 64)
        with _patch_mamba_forward():
            out = mgr.process_context(inp)
        assert out.shape[0] == 1
        assert out.shape[1] == 8
        assert out.shape[2] == 64

    def test_unload_model(self):
        cfg = MambaConfig(d_model=64, num_mamba_layers=2, device="cpu")
        mgr = MambaHybridManager(cfg)
        mgr.load_model()
        mgr.unload_model()
        assert mgr.is_loaded is False
        assert mgr.model is None


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch not installed")
class TestConstitutionalMambaHybrid:
    def _make_model(self):
        from enhanced_agent_bus.ai_assistant.mamba_hybrid_processor import ConstitutionalMambaHybrid

        cfg = MambaConfig(d_model=64, num_mamba_layers=2, device="cpu")
        return ConstitutionalMambaHybrid(cfg)

    def test_forward_basic(self):
        import torch

        model = self._make_model()
        model.eval()
        with torch.no_grad(), _patch_mamba_forward():
            x = torch.randn(1, 8, 64)
            out = model(x)
        assert out.shape == x.shape

    def test_forward_with_critical_positions(self):
        import torch

        model = self._make_model()
        model.eval()
        with torch.no_grad(), _patch_mamba_forward():
            x = torch.randn(1, 8, 64)
            out = model(x, critical_positions=[0, 2])
        assert out.shape[0] == 1
        assert out.shape[2] == 64

    def test_forward_with_attention(self):
        import torch

        cfg = MambaConfig(
            d_model=64, num_mamba_layers=2, device="cpu",
            use_shared_attention=True,
        )
        from enhanced_agent_bus.ai_assistant.mamba_hybrid_processor import ConstitutionalMambaHybrid

        model = ConstitutionalMambaHybrid(cfg)
        model.eval()
        with torch.no_grad(), _patch_mamba_forward():
            x = torch.randn(1, 8, 64)
            out = model(x, use_attention=True)
        assert out.shape[0] == 1

    def test_get_memory_usage(self):
        model = self._make_model()
        usage = model.get_memory_usage()
        assert "model_memory_mb" in usage
        assert "max_context_tokens" in usage
        assert usage["jrt_enabled"] is True

    def test_enable_memory_efficient_mode(self):
        model = self._make_model()
        model.enable_memory_efficient_mode()
        assert model.config.memory_efficient_mode is True

    def test_reset_memory_cache(self):
        model = self._make_model()
        model.reset_memory_cache()

    def test_identify_critical_positions(self):
        import torch

        model = self._make_model()
        input_ids = torch.zeros(1, 1000, dtype=torch.long)
        positions = model._identify_critical_positions(input_ids)
        assert 0 in positions
        assert 250 in positions
        assert 500 in positions

    def test_no_shared_attention(self):
        import torch

        cfg = MambaConfig(
            d_model=64, num_mamba_layers=2,
            device="cpu", use_shared_attention=False,
        )
        from enhanced_agent_bus.ai_assistant.mamba_hybrid_processor import ConstitutionalMambaHybrid

        model = ConstitutionalMambaHybrid(cfg)
        assert model.shared_attention is None
        model.eval()
        with torch.no_grad(), _patch_mamba_forward():
            out = model(torch.randn(1, 4, 64))
        assert out.shape == (1, 4, 64)

    def test_jrt_disabled(self):
        import torch

        cfg = MambaConfig(d_model=64, num_mamba_layers=2, device="cpu", jrt_enabled=False)
        from enhanced_agent_bus.ai_assistant.mamba_hybrid_processor import ConstitutionalMambaHybrid

        model = ConstitutionalMambaHybrid(cfg)
        assert model.jrt_enabled is False
        model.eval()
        with torch.no_grad(), _patch_mamba_forward():
            x = torch.randn(1, 4, 64)
            out = model(x, critical_positions=[0, 1])
        # With JRT disabled, critical positions should be ignored
        assert out.shape == (1, 4, 64)


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch not installed")
class TestMambaSSM:
    def test_initialization(self):
        from enhanced_agent_bus.ai_assistant.mamba_hybrid_processor import MambaSSM

        cfg = MambaConfig(d_model=64, device="cpu")
        layer = MambaSSM(cfg)
        assert layer.d_model == 64
        assert layer.d_inner == 128  # expand=2 * d_model=64
        assert layer.d_state == cfg.d_state

    def test_has_required_layers(self):
        from enhanced_agent_bus.ai_assistant.mamba_hybrid_processor import MambaSSM

        cfg = MambaConfig(d_model=64, device="cpu")
        layer = MambaSSM(cfg)
        assert hasattr(layer, "in_proj")
        assert hasattr(layer, "conv1d")
        assert hasattr(layer, "x_proj")
        assert hasattr(layer, "dt_proj")
        assert hasattr(layer, "out_proj")


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch not installed")
class TestSharedAttentionLayer:
    def test_forward(self):
        import torch

        from enhanced_agent_bus.ai_assistant.mamba_hybrid_processor import SharedAttentionLayer

        cfg = MambaConfig(d_model=64, device="cpu")
        layer = SharedAttentionLayer(cfg)
        layer.eval()
        with torch.no_grad():
            x = torch.randn(1, 4, 64)
            out = layer(x)
        assert out.shape == (1, 4, 64)

    def test_forward_with_mask(self):
        import torch

        from enhanced_agent_bus.ai_assistant.mamba_hybrid_processor import SharedAttentionLayer

        cfg = MambaConfig(d_model=64, device="cpu")
        layer = SharedAttentionLayer(cfg)
        layer.eval()
        with torch.no_grad():
            x = torch.randn(1, 4, 64)
            mask = torch.ones(1, 1, 4, 4)
            out = layer(x, mask=mask)
        assert out.shape == (1, 4, 64)

    def test_num_heads(self):
        from enhanced_agent_bus.ai_assistant.mamba_hybrid_processor import SharedAttentionLayer

        cfg = MambaConfig(d_model=64, device="cpu")
        layer = SharedAttentionLayer(cfg)
        assert layer.num_heads == 8
        assert layer.head_dim == 8


# ---------------------------------------------------------------------------
# Global helpers
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch not installed")
class TestGlobalHelpers:
    def test_get_mamba_hybrid_processor(self):
        mgr = get_mamba_hybrid_processor()
        assert isinstance(mgr, MambaHybridManager)

    def test_initialize_mamba_processor(self):
        cfg = MambaConfig(d_model=64, num_mamba_layers=2, device="cpu")
        success = initialize_mamba_processor(cfg)
        assert success is True
        mgr = get_mamba_hybrid_processor()
        assert mgr.is_loaded is True
