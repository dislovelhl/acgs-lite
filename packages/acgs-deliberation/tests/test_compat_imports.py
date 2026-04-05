from acgs_deliberation import DeliberationLayer, DeliberationQueue, get_vote_collector
from acgs_deliberation.integration import DeliberationLayer as NewIntegrationLayer
from enhanced_agent_bus.deliberation_layer import DeliberationQueue as LegacyDeliberationQueue
from enhanced_agent_bus.deliberation_layer.integration import DeliberationLayer as LegacyLayer


def test_deliberation_layer_reexport_points_to_legacy_type() -> None:
    assert DeliberationLayer is LegacyLayer


def test_deliberation_queue_reexport_points_to_legacy_type() -> None:
    assert DeliberationQueue is LegacyDeliberationQueue


def test_vote_collector_factory_is_callable() -> None:
    assert callable(get_vote_collector)


def test_integration_module_reexport_points_to_legacy_type() -> None:
    assert NewIntegrationLayer is LegacyLayer
