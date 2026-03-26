from enhanced_agent_bus.observability import CapacityValidationResult
from enhanced_agent_bus.observability.capacity_metrics import ValidationResult


def test_capacity_validation_result_alias_matches_capacity_metrics_validation_result():
    assert CapacityValidationResult.SUCCESS.value == ValidationResult.SUCCESS.value
    assert CapacityValidationResult.FAILURE.value == ValidationResult.FAILURE.value
    assert CapacityValidationResult.ERROR.value == ValidationResult.ERROR.value
