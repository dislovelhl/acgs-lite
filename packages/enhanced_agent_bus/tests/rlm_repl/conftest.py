"""
Shared fixtures and helpers for RLM REPL tests.
Constitutional Hash: 608508a9bd224290
"""

from unittest.mock import patch

REPL_MODULE = "enhanced_agent_bus.rlm_repl"


def _make_repl(config=None):
    """Patch environment and instantiate RLMREPLEnvironment."""
    from enhanced_agent_bus.rlm_repl import REPLConfig, RLMREPLEnvironment

    with (
        patch(f"{REPL_MODULE}.is_repl_enabled", return_value=True),
        patch(f"{REPL_MODULE}.IS_PRODUCTION", False),
        patch(f"{REPL_MODULE}.ENABLE_RLM_REPL", True),
    ):
        return RLMREPLEnvironment(config)
