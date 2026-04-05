# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/enums.py

Covers all enum classes, every value, string coercion, membership checks,
helper methods, and __all__ exports to achieve ≥95% line coverage.
"""

from enum import Enum

import pytest

from enhanced_agent_bus.enums import (
    AgentCapability,
    AutonomyTier,
    BatchItemStatus,
    MessageStatus,
    MessageType,
    Priority,
    RiskLevel,
    TaskComplexity,
    TaskType,
    ValidationStatus,
)
from enhanced_agent_bus.enums import (
    __all__ as enums_all,
)

# ---------------------------------------------------------------------------
# __all__ exports
# ---------------------------------------------------------------------------


class TestAllExports:
    def test_all_contains_message_type(self):
        assert "MessageType" in enums_all

    def test_all_contains_priority(self):
        assert "Priority" in enums_all

    def test_all_contains_validation_status(self):
        assert "ValidationStatus" in enums_all

    def test_all_contains_risk_level(self):
        assert "RiskLevel" in enums_all

    def test_all_contains_message_status(self):
        assert "MessageStatus" in enums_all

    def test_all_contains_batch_item_status(self):
        assert "BatchItemStatus" in enums_all

    def test_all_contains_task_complexity(self):
        assert "TaskComplexity" in enums_all

    def test_all_contains_task_type(self):
        assert "TaskType" in enums_all

    def test_all_contains_autonomy_tier(self):
        assert "AutonomyTier" in enums_all

    def test_all_contains_agent_capability(self):
        assert "AgentCapability" in enums_all


# ---------------------------------------------------------------------------
# MessageType
# ---------------------------------------------------------------------------


class TestMessageType:
    def test_is_enum(self):
        assert issubclass(MessageType, Enum)

    def test_command_value(self):
        assert MessageType.COMMAND.value == "command"

    def test_query_value(self):
        assert MessageType.QUERY.value == "query"

    def test_response_value(self):
        assert MessageType.RESPONSE.value == "response"

    def test_event_value(self):
        assert MessageType.EVENT.value == "event"

    def test_notification_value(self):
        assert MessageType.NOTIFICATION.value == "notification"

    def test_heartbeat_value(self):
        assert MessageType.HEARTBEAT.value == "heartbeat"

    def test_governance_request_value(self):
        assert MessageType.GOVERNANCE_REQUEST.value == "governance_request"

    def test_governance_response_value(self):
        assert MessageType.GOVERNANCE_RESPONSE.value == "governance_response"

    def test_constitutional_validation_value(self):
        assert MessageType.CONSTITUTIONAL_VALIDATION.value == "constitutional_validation"

    def test_task_request_value(self):
        assert MessageType.TASK_REQUEST.value == "task_request"

    def test_task_response_value(self):
        assert MessageType.TASK_RESPONSE.value == "task_response"

    def test_audit_log_value(self):
        assert MessageType.AUDIT_LOG.value == "audit_log"

    def test_member_count(self):
        assert len(MessageType) == 14

    def test_lookup_by_value_command(self):
        assert MessageType("command") == MessageType.COMMAND

    def test_lookup_by_value_query(self):
        assert MessageType("query") == MessageType.QUERY

    def test_lookup_by_value_governance_request(self):
        assert MessageType("governance_request") == MessageType.GOVERNANCE_REQUEST

    def test_membership_command(self):
        assert MessageType.COMMAND in MessageType

    def test_membership_audit_log(self):
        assert MessageType.AUDIT_LOG in MessageType

    def test_name_command(self):
        assert MessageType.COMMAND.name == "COMMAND"

    def test_name_constitutional_validation(self):
        assert MessageType.CONSTITUTIONAL_VALIDATION.name == "CONSTITUTIONAL_VALIDATION"

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            MessageType("nonexistent")

    def test_str_representation(self):
        assert "COMMAND" in str(MessageType.COMMAND)

    def test_repr_representation(self):
        assert "MessageType" in repr(MessageType.COMMAND)

    def test_all_values_are_strings(self):
        for member in MessageType:
            assert isinstance(member.value, str)

    def test_no_duplicate_values(self):
        values = [m.value for m in MessageType]
        assert len(values) == len(set(values))

    def test_iteration_order(self):
        members = list(MessageType)
        assert members[0] == MessageType.COMMAND
        assert members[-1] == MessageType.AUDIT_LOG


# ---------------------------------------------------------------------------
# Priority
# ---------------------------------------------------------------------------


class TestPriority:
    def test_is_enum(self):
        assert issubclass(Priority, Enum)

    def test_low_value(self):
        assert Priority.LOW.value == 0

    def test_normal_value(self):
        assert Priority.NORMAL.value == 1

    def test_medium_value(self):
        assert Priority.MEDIUM.value == 1

    def test_high_value(self):
        assert Priority.HIGH.value == 2

    def test_critical_value(self):
        assert Priority.CRITICAL.value == 3

    def test_normal_is_alias_for_medium(self):
        # NORMAL and MEDIUM share the same value; Python enum treats them as aliases
        assert Priority.NORMAL is Priority.MEDIUM

    def test_lookup_by_value_0(self):
        assert Priority(0) == Priority.LOW

    def test_lookup_by_value_1(self):
        # Both NORMAL and MEDIUM map to value 1; canonical member is whichever is defined first
        assert Priority(1) is Priority.NORMAL

    def test_lookup_by_value_2(self):
        assert Priority(2) == Priority.HIGH

    def test_lookup_by_value_3(self):
        assert Priority(3) == Priority.CRITICAL

    def test_ordering_low_less_than_high(self):
        assert Priority.LOW.value < Priority.HIGH.value

    def test_ordering_high_less_than_critical(self):
        assert Priority.HIGH.value < Priority.CRITICAL.value

    def test_name_low(self):
        assert Priority.LOW.name == "LOW"

    def test_name_high(self):
        assert Priority.HIGH.name == "HIGH"

    def test_name_critical(self):
        assert Priority.CRITICAL.name == "CRITICAL"

    def test_all_values_are_ints(self):
        for member in Priority:
            assert isinstance(member.value, int)

    def test_membership_low(self):
        assert Priority.LOW in Priority

    def test_membership_critical(self):
        assert Priority.CRITICAL in Priority

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            Priority(99)

    def test_repr(self):
        assert "Priority" in repr(Priority.HIGH)

    def test_str(self):
        assert "HIGH" in str(Priority.HIGH)

    def test_unique_member_count(self):
        # NORMAL is an alias for MEDIUM, so unique members = 4
        assert len(Priority) == 4


# ---------------------------------------------------------------------------
# ValidationStatus
# ---------------------------------------------------------------------------


class TestValidationStatus:
    def test_is_enum(self):
        assert issubclass(ValidationStatus, Enum)

    def test_pending_value(self):
        assert ValidationStatus.PENDING.value == "pending"

    def test_valid_value(self):
        assert ValidationStatus.VALID.value == "valid"

    def test_invalid_value(self):
        assert ValidationStatus.INVALID.value == "invalid"

    def test_warning_value(self):
        assert ValidationStatus.WARNING.value == "warning"

    def test_member_count(self):
        assert len(ValidationStatus) == 4

    def test_lookup_pending(self):
        assert ValidationStatus("pending") == ValidationStatus.PENDING

    def test_lookup_valid(self):
        assert ValidationStatus("valid") == ValidationStatus.VALID

    def test_lookup_invalid(self):
        assert ValidationStatus("invalid") == ValidationStatus.INVALID

    def test_lookup_warning(self):
        assert ValidationStatus("warning") == ValidationStatus.WARNING

    def test_membership(self):
        for member in ValidationStatus:
            assert member in ValidationStatus

    def test_no_duplicate_values(self):
        values = [m.value for m in ValidationStatus]
        assert len(values) == len(set(values))

    def test_invalid_lookup_raises(self):
        with pytest.raises(ValueError):
            ValidationStatus("approved")


# ---------------------------------------------------------------------------
# RiskLevel (re-exported from enhanced_agent_bus._compat.enums)
# ---------------------------------------------------------------------------


class TestRiskLevel:
    def test_is_importable_from_enums(self):
        assert RiskLevel is not None

    def test_low_value(self):
        assert RiskLevel.LOW == "low" or RiskLevel.LOW.value == "low"

    def test_medium_value(self):
        assert RiskLevel.MEDIUM == "medium" or RiskLevel.MEDIUM.value == "medium"

    def test_high_value(self):
        assert RiskLevel.HIGH == "high" or RiskLevel.HIGH.value == "high"

    def test_critical_value(self):
        assert RiskLevel.CRITICAL == "critical" or RiskLevel.CRITICAL.value == "critical"

    def test_member_count(self):
        assert len(RiskLevel) == 4

    def test_membership_low(self):
        assert RiskLevel.LOW in RiskLevel

    def test_membership_critical(self):
        assert RiskLevel.CRITICAL in RiskLevel

    def test_name_low(self):
        assert RiskLevel.LOW.name == "LOW"

    def test_name_critical(self):
        assert RiskLevel.CRITICAL.name == "CRITICAL"


# ---------------------------------------------------------------------------
# AutonomyTier
# ---------------------------------------------------------------------------


class TestAutonomyTier:
    def test_is_enum(self):
        assert issubclass(AutonomyTier, Enum)

    def test_advisory_value(self):
        assert AutonomyTier.ADVISORY.value == "advisory"

    def test_human_approved_value(self):
        assert AutonomyTier.HUMAN_APPROVED.value == "human_approved"

    def test_bounded_value(self):
        assert AutonomyTier.BOUNDED.value == "bounded"

    def test_unrestricted_value(self):
        assert AutonomyTier.UNRESTRICTED.value == "unrestricted"

    def test_member_count(self):
        assert len(AutonomyTier) == 4

    def test_lookup_advisory(self):
        assert AutonomyTier("advisory") == AutonomyTier.ADVISORY

    def test_lookup_human_approved(self):
        assert AutonomyTier("human_approved") == AutonomyTier.HUMAN_APPROVED

    def test_lookup_bounded(self):
        assert AutonomyTier("bounded") == AutonomyTier.BOUNDED

    def test_lookup_unrestricted(self):
        assert AutonomyTier("unrestricted") == AutonomyTier.UNRESTRICTED

    def test_membership(self):
        for member in AutonomyTier:
            assert member in AutonomyTier

    def test_no_duplicate_values(self):
        values = [m.value for m in AutonomyTier]
        assert len(values) == len(set(values))

    def test_name_advisory(self):
        assert AutonomyTier.ADVISORY.name == "ADVISORY"

    def test_name_unrestricted(self):
        assert AutonomyTier.UNRESTRICTED.name == "UNRESTRICTED"

    def test_invalid_lookup_raises(self):
        with pytest.raises(ValueError):
            AutonomyTier("full_autonomy")

    def test_str(self):
        assert "ADVISORY" in str(AutonomyTier.ADVISORY)

    def test_repr(self):
        assert "AutonomyTier" in repr(AutonomyTier.BOUNDED)


# ---------------------------------------------------------------------------
# MessageStatus
# ---------------------------------------------------------------------------


class TestMessageStatus:
    def test_is_enum(self):
        assert issubclass(MessageStatus, Enum)

    def test_pending_value(self):
        assert MessageStatus.PENDING.value == "pending"

    def test_processing_value(self):
        assert MessageStatus.PROCESSING.value == "processing"

    def test_delivered_value(self):
        assert MessageStatus.DELIVERED.value == "delivered"

    def test_failed_value(self):
        assert MessageStatus.FAILED.value == "failed"

    def test_expired_value(self):
        assert MessageStatus.EXPIRED.value == "expired"

    def test_pending_deliberation_value(self):
        assert MessageStatus.PENDING_DELIBERATION.value == "pending_deliberation"

    def test_validated_value(self):
        assert MessageStatus.VALIDATED.value == "validated"

    def test_member_count(self):
        assert len(MessageStatus) == 7

    def test_lookup_pending(self):
        assert MessageStatus("pending") == MessageStatus.PENDING

    def test_lookup_delivered(self):
        assert MessageStatus("delivered") == MessageStatus.DELIVERED

    def test_lookup_pending_deliberation(self):
        assert MessageStatus("pending_deliberation") == MessageStatus.PENDING_DELIBERATION

    def test_lookup_validated(self):
        assert MessageStatus("validated") == MessageStatus.VALIDATED

    def test_membership(self):
        for member in MessageStatus:
            assert member in MessageStatus

    def test_no_duplicate_values(self):
        values = [m.value for m in MessageStatus]
        assert len(values) == len(set(values))

    def test_invalid_lookup_raises(self):
        with pytest.raises(ValueError):
            MessageStatus("unknown_status")

    def test_name_failed(self):
        assert MessageStatus.FAILED.name == "FAILED"

    def test_name_expired(self):
        assert MessageStatus.EXPIRED.name == "EXPIRED"


# ---------------------------------------------------------------------------
# BatchItemStatus
# ---------------------------------------------------------------------------


class TestBatchItemStatus:
    def test_is_enum(self):
        assert issubclass(BatchItemStatus, Enum)

    def test_pending_value(self):
        assert BatchItemStatus.PENDING.value == "pending"

    def test_processing_value(self):
        assert BatchItemStatus.PROCESSING.value == "processing"

    def test_success_value(self):
        assert BatchItemStatus.SUCCESS.value == "success"

    def test_failed_value(self):
        assert BatchItemStatus.FAILED.value == "failed"

    def test_skipped_value(self):
        assert BatchItemStatus.SKIPPED.value == "skipped"

    def test_member_count(self):
        assert len(BatchItemStatus) == 5

    def test_lookup_success(self):
        assert BatchItemStatus("success") == BatchItemStatus.SUCCESS

    def test_lookup_skipped(self):
        assert BatchItemStatus("skipped") == BatchItemStatus.SKIPPED

    def test_membership(self):
        for member in BatchItemStatus:
            assert member in BatchItemStatus

    def test_no_duplicate_values(self):
        values = [m.value for m in BatchItemStatus]
        assert len(values) == len(set(values))

    def test_invalid_lookup_raises(self):
        with pytest.raises(ValueError):
            BatchItemStatus("cancelled")

    def test_name_success(self):
        assert BatchItemStatus.SUCCESS.name == "SUCCESS"

    def test_name_skipped(self):
        assert BatchItemStatus.SKIPPED.name == "SKIPPED"


# ---------------------------------------------------------------------------
# TaskComplexity
# ---------------------------------------------------------------------------


class TestTaskComplexity:
    def test_is_enum(self):
        assert issubclass(TaskComplexity, Enum)

    def test_trivial_value(self):
        assert TaskComplexity.TRIVIAL.value == "trivial"

    def test_simple_value(self):
        assert TaskComplexity.SIMPLE.value == "simple"

    def test_moderate_value(self):
        assert TaskComplexity.MODERATE.value == "moderate"

    def test_complex_value(self):
        assert TaskComplexity.COMPLEX.value == "complex"

    def test_visionary_value(self):
        assert TaskComplexity.VISIONARY.value == "visionary"

    def test_member_count(self):
        assert len(TaskComplexity) == 5

    def test_lookup_trivial(self):
        assert TaskComplexity("trivial") == TaskComplexity.TRIVIAL

    def test_lookup_visionary(self):
        assert TaskComplexity("visionary") == TaskComplexity.VISIONARY

    def test_membership(self):
        for member in TaskComplexity:
            assert member in TaskComplexity

    def test_no_duplicate_values(self):
        values = [m.value for m in TaskComplexity]
        assert len(values) == len(set(values))

    def test_invalid_lookup_raises(self):
        with pytest.raises(ValueError):
            TaskComplexity("impossible")

    def test_name_complex(self):
        assert TaskComplexity.COMPLEX.name == "COMPLEX"

    def test_name_moderate(self):
        assert TaskComplexity.MODERATE.name == "MODERATE"


# ---------------------------------------------------------------------------
# TaskType
# ---------------------------------------------------------------------------


class TestTaskType:
    def test_is_enum(self):
        assert issubclass(TaskType, Enum)

    # Original general categories
    def test_coding_value(self):
        assert TaskType.CODING.value == "coding"

    def test_research_value(self):
        assert TaskType.RESEARCH.value == "research"

    def test_analysis_value(self):
        assert TaskType.ANALYSIS.value == "analysis"

    def test_creative_value(self):
        assert TaskType.CREATIVE.value == "creative"

    def test_integration_value(self):
        assert TaskType.INTEGRATION.value == "integration"

    def test_governance_value(self):
        assert TaskType.GOVERNANCE.value == "governance"

    def test_unknown_value(self):
        assert TaskType.UNKNOWN.value == "unknown"

    # Specific task types
    def test_code_generation_value(self):
        assert TaskType.CODE_GENERATION.value == "code_generation"

    def test_code_review_value(self):
        assert TaskType.CODE_REVIEW.value == "code_review"

    def test_debugging_value(self):
        assert TaskType.DEBUGGING.value == "debugging"

    def test_architecture_value(self):
        assert TaskType.ARCHITECTURE.value == "architecture"

    def test_documentation_value(self):
        assert TaskType.DOCUMENTATION.value == "documentation"

    def test_testing_value(self):
        assert TaskType.TESTING.value == "testing"

    def test_deployment_value(self):
        assert TaskType.DEPLOYMENT.value == "deployment"

    def test_optimization_value(self):
        assert TaskType.OPTIMIZATION.value == "optimization"

    def test_security_audit_value(self):
        assert TaskType.SECURITY_AUDIT.value == "security_audit"

    def test_constitutional_validation_value(self):
        assert TaskType.CONSTITUTIONAL_VALIDATION.value == "constitutional_validation"

    def test_workflow_automation_value(self):
        assert TaskType.WORKFLOW_AUTOMATION.value == "workflow_automation"

    def test_member_count(self):
        assert len(TaskType) == 18

    def test_lookup_coding(self):
        assert TaskType("coding") == TaskType.CODING

    def test_lookup_security_audit(self):
        assert TaskType("security_audit") == TaskType.SECURITY_AUDIT

    def test_lookup_workflow_automation(self):
        assert TaskType("workflow_automation") == TaskType.WORKFLOW_AUTOMATION

    def test_membership(self):
        for member in TaskType:
            assert member in TaskType

    def test_no_duplicate_values(self):
        values = [m.value for m in TaskType]
        assert len(values) == len(set(values))

    def test_invalid_lookup_raises(self):
        with pytest.raises(ValueError):
            TaskType("not_a_task_type")

    def test_name_coding(self):
        assert TaskType.CODING.name == "CODING"

    def test_name_constitutional_validation(self):
        assert TaskType.CONSTITUTIONAL_VALIDATION.name == "CONSTITUTIONAL_VALIDATION"


# ---------------------------------------------------------------------------
# AgentCapability
# ---------------------------------------------------------------------------


class TestAgentCapability:
    def test_is_enum(self):
        assert issubclass(AgentCapability, Enum)

    # Core capabilities
    def test_code_generation_value(self):
        assert AgentCapability.CODE_GENERATION.value == "code_generation"

    def test_code_review_value(self):
        assert AgentCapability.CODE_REVIEW.value == "code_review"

    def test_research_value(self):
        assert AgentCapability.RESEARCH.value == "research"

    def test_analysis_value(self):
        assert AgentCapability.ANALYSIS.value == "analysis"

    def test_creative_value(self):
        assert AgentCapability.CREATIVE.value == "creative"

    def test_integration_value(self):
        assert AgentCapability.INTEGRATION.value == "integration"

    def test_governance_value(self):
        assert AgentCapability.GOVERNANCE.value == "governance"

    def test_orchestration_value(self):
        assert AgentCapability.ORCHESTRATION.value == "orchestration"

    def test_verification_value(self):
        assert AgentCapability.VERIFICATION.value == "verification"

    # Language-specific experts
    def test_python_expert_value(self):
        assert AgentCapability.PYTHON_EXPERT.value == "python_expert"

    def test_typescript_expert_value(self):
        assert AgentCapability.TYPESCRIPT_EXPERT.value == "typescript_expert"

    def test_rust_expert_value(self):
        assert AgentCapability.RUST_EXPERT.value == "rust_expert"

    # Specialized capabilities
    def test_security_specialist_value(self):
        assert AgentCapability.SECURITY_SPECIALIST.value == "security_specialist"

    def test_constitutional_validator_value(self):
        assert AgentCapability.CONSTITUTIONAL_VALIDATOR.value == "constitutional_validator"

    def test_research_specialist_value(self):
        assert AgentCapability.RESEARCH_SPECIALIST.value == "research_specialist"

    def test_architecture_designer_value(self):
        assert AgentCapability.ARCHITECTURE_DESIGNER.value == "architecture_designer"

    def test_test_automation_value(self):
        assert AgentCapability.TEST_AUTOMATION.value == "test_automation"

    def test_performance_optimizer_value(self):
        assert AgentCapability.PERFORMANCE_OPTIMIZER.value == "performance_optimizer"

    def test_member_count(self):
        assert len(AgentCapability) == 18

    def test_lookup_code_generation(self):
        assert AgentCapability("code_generation") == AgentCapability.CODE_GENERATION

    def test_lookup_constitutional_validator(self):
        assert (
            AgentCapability("constitutional_validator") == AgentCapability.CONSTITUTIONAL_VALIDATOR
        )

    def test_lookup_performance_optimizer(self):
        assert AgentCapability("performance_optimizer") == AgentCapability.PERFORMANCE_OPTIMIZER

    def test_membership(self):
        for member in AgentCapability:
            assert member in AgentCapability

    def test_no_duplicate_values(self):
        values = [m.value for m in AgentCapability]
        assert len(values) == len(set(values))

    def test_invalid_lookup_raises(self):
        with pytest.raises(ValueError):
            AgentCapability("magic_powers")

    def test_name_python_expert(self):
        assert AgentCapability.PYTHON_EXPERT.name == "PYTHON_EXPERT"

    def test_name_governance(self):
        assert AgentCapability.GOVERNANCE.name == "GOVERNANCE"

    def test_str(self):
        assert "CODE_GENERATION" in str(AgentCapability.CODE_GENERATION)

    def test_repr(self):
        assert "AgentCapability" in repr(AgentCapability.RUST_EXPERT)


# ---------------------------------------------------------------------------
# Cross-enum consistency checks
# ---------------------------------------------------------------------------


class TestCrossEnumConsistency:
    def test_all_enums_are_enum_subclasses(self):
        for enum_cls in [
            MessageType,
            Priority,
            ValidationStatus,
            AutonomyTier,
            MessageStatus,
            BatchItemStatus,
            TaskComplexity,
            TaskType,
            AgentCapability,
        ]:
            assert issubclass(enum_cls, Enum)

    def test_all_enums_have_at_least_one_member(self):
        for enum_cls in [
            MessageType,
            Priority,
            ValidationStatus,
            AutonomyTier,
            MessageStatus,
            BatchItemStatus,
            TaskComplexity,
            TaskType,
            AgentCapability,
        ]:
            assert len(enum_cls) >= 1

    def test_risk_level_is_re_exported_from_shared(self):
        from enhanced_agent_bus._compat.enums import RiskLevel as SharedRiskLevel
        from enhanced_agent_bus.enums import RiskLevel as BusRiskLevel

        assert SharedRiskLevel is BusRiskLevel

    def test_enum_equality_by_identity(self):
        a = MessageType.COMMAND
        b = MessageType.COMMAND
        assert a is b

    def test_enum_inequality_across_types(self):
        # Two different enum members with the same string value don't compare equal
        assert ValidationStatus.PENDING != MessageStatus.PENDING

    def test_priority_normal_medium_alias(self):
        # Confirm canonical member for value=1 is NORMAL (defined first)
        canonical = Priority(1)
        assert canonical.name == "NORMAL"

    def test_task_type_and_agent_capability_share_code_review_semantics(self):
        # Both enums have CODE_REVIEW; their values match semantically
        assert TaskType.CODE_REVIEW.value == AgentCapability.CODE_REVIEW.value == "code_review"

    def test_all_string_enum_values_are_lowercase(self):
        """Validate consistent lowercase convention for string-valued enums."""
        string_enums = [
            MessageType,
            ValidationStatus,
            AutonomyTier,
            MessageStatus,
            BatchItemStatus,
            TaskComplexity,
            TaskType,
            AgentCapability,
        ]
        for enum_cls in string_enums:
            for member in enum_cls:
                assert member.value == member.value.lower(), (
                    f"{enum_cls.__name__}.{member.name} value {member.value!r} is not lowercase"
                )
