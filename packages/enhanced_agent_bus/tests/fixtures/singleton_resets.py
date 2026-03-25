"""
Fixtures that reset singleton state between tests.

Constitutional Hash: 608508a9bd224290
"""

import pytest


def _reset_singletons() -> None:
    """Reset all known singletons to prevent state pollution between tests."""
    for import_path, func_name in [
        ("enhanced_agent_bus.deliberation_layer.integration", "reset_deliberation_layer"),
        ("enhanced_agent_bus.batch_processor", "reset_batch_processor"),
        ("enhanced_agent_bus.impact_scorer_infra.service", "reset_impact_scorer"),
        ("enhanced_agent_bus.deliberation_layer.adaptive_router", "reset_adaptive_router"),
        ("enhanced_agent_bus.deliberation_layer.deliberation_queue", "reset_deliberation_queue"),
    ]:
        try:
            mod = __import__(import_path, fromlist=[func_name])
            getattr(mod, func_name)()
        except (ImportError, AttributeError):
            pass

    # Reset bundle_registry global distribution service to prevent xdist state leak
    try:
        import enhanced_agent_bus.bundle_registry as _br

        _br._distribution_service = None
    except (ImportError, AttributeError):
        pass


@pytest.fixture(autouse=True)
def reset_global_state():
    """Reset global singletons before each test to prevent state pollution.

    Constitutional Hash: 608508a9bd224290
    """
    _reset_singletons()

    # Reset runtime security scanner with Docker sandbox disabled
    try:
        import enhanced_agent_bus.runtime_security as _rt_sec

        config = _rt_sec.RuntimeSecurityConfig(enable_runtime_guardrails=False)
        _rt_sec._scanner = _rt_sec.RuntimeSecurityScanner(config)
    except (ImportError, AttributeError):
        pass

    yield  # Run the test

    _reset_singletons()
