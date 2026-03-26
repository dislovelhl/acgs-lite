"""
Constitutional Gap Analysis Tests
Constitutional Hash: 608508a9bd224290

Phase 10 Task 10: Constitutional Gap Analysis

Tests for:
- Legacy policy scanning
- Gap severity scoring (critical, high, medium, low)
- Remediation recommendation generation
- Gap closure tracking
"""

import pytest

from enterprise_sso.gap_analysis import (
    CONSTITUTIONAL_HASH,
    ConstitutionalGap,
    ConstitutionalPolicyScanner,
    GapCategory,
    GapClassifier,
    GapSeverity,
    GapStatus,
    GapTracker,
    GapTrackingDashboard,
    PolicyLocation,
    RemediationEngine,
    RemediationSuggestion,
    RemediationType,
    ScanResult,
)

# Mark all tests as governance tests (95% coverage required)
# Constitutional Hash: 608508a9bd224290
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

# ============================================================================
# Test Classes
# ============================================================================


class TestLegacyPolicyScanning:
    """Tests for legacy policy scanning."""

    def test_scan_policy_with_missing_hash(self):
        """Test detection of missing constitutional hash."""
        scanner = ConstitutionalPolicyScanner()
        policy = """
        package policy

        allow {
            input.action == "read"
        }
        """
        gaps = scanner.scan_policy(policy, "test.rego", "tenant-1")

        assert any(g.category == GapCategory.MISSING_HASH for g in gaps)
        assert any(g.severity == GapSeverity.CRITICAL for g in gaps)

    def test_scan_policy_with_valid_hash(self):
        """Test policy with valid constitutional hash passes."""
        scanner = ConstitutionalPolicyScanner()
        policy = f"""
        package policy

        constitutional_hash := "{CONSTITUTIONAL_HASH}"

        allow {{
            input.action == "read"
            validate_constitutional(constitutional_hash)
        }}
        """
        gaps = scanner.scan_policy(policy, "test.rego", "tenant-1")

        assert not any(g.category == GapCategory.MISSING_HASH for g in gaps)

    def test_scan_policy_with_invalid_hash(self):
        """Test detection of invalid constitutional hash."""
        scanner = ConstitutionalPolicyScanner()
        policy = """
        package policy

        constitutional_hash := "wrong_hash_12345"

        allow {
            input.action == "read"
        }
        """
        gaps = scanner.scan_policy(policy, "test.rego", "tenant-1")

        assert any(g.category == GapCategory.INVALID_HASH for g in gaps)

    def test_scan_policy_with_self_validation(self):
        """Test detection of self-validation pattern."""
        scanner = ConstitutionalPolicyScanner()
        policy = f"""
        package policy

        constitutional_hash := "{CONSTITUTIONAL_HASH}"

        allow {{
            self.validate(input)
        }}
        """
        gaps = scanner.scan_policy(policy, "test.rego", "tenant-1")

        assert any(g.category == GapCategory.SELF_VALIDATION for g in gaps)
        assert any(g.severity == GapSeverity.CRITICAL for g in gaps)

    def test_scan_policy_missing_audit(self):
        """Test detection of missing audit requirements."""
        scanner = ConstitutionalPolicyScanner()
        policy = f"""
        package policy

        constitutional_hash := "{CONSTITUTIONAL_HASH}"

        allow {{
            input.action == "read"
        }}
        """
        gaps = scanner.scan_policy(policy, "test.rego", "tenant-1")

        assert any(g.category == GapCategory.MISSING_AUDIT for g in gaps)

    def test_scan_policy_missing_maci_role(self):
        """Test detection of missing MACI role checks."""
        scanner = ConstitutionalPolicyScanner()
        policy = f"""
        package policy

        constitutional_hash := "{CONSTITUTIONAL_HASH}"
        audit := true

        allow {{
            input.action == "read"
        }}
        """
        gaps = scanner.scan_policy(policy, "test.rego", "tenant-1")

        assert any(g.category == GapCategory.NO_MACI_ROLE for g in gaps)

    def test_scan_policy_insecure_default(self):
        """Test detection of insecure default-allow pattern."""
        scanner = ConstitutionalPolicyScanner()
        policy = f"""
        package policy

        constitutional_hash := "{CONSTITUTIONAL_HASH}"
        maci_role := "executive"
        audit := true
        check_input := true

        default allow = true
        """
        gaps = scanner.scan_policy(policy, "test.rego", "tenant-1")

        assert any(g.category == GapCategory.INSECURE_DEFAULT for g in gaps)

    def test_batch_scan_policies(self):
        """Test batch scanning of multiple policies."""
        scanner = ConstitutionalPolicyScanner()
        policies = [
            ("package a\nallow { true }", "a.rego"),
            ("package b\nallow { true }", "b.rego"),
            (f'constitutional_hash := "{CONSTITUTIONAL_HASH}"', "c.rego"),
        ]

        result = scanner.scan_policies_batch(policies, "tenant-1")

        assert result.policies_scanned == 3
        assert result.gaps_found > 0
        assert result.scan_start is not None
        assert result.scan_end is not None
        assert result.constitutional_hash == CONSTITUTIONAL_HASH


class TestGapSeverityScoring:
    """Tests for gap severity scoring."""

    def test_critical_severity_highest_score(self):
        """Test that critical severity has highest score."""
        classifier = GapClassifier()

        critical_gap = ConstitutionalGap(
            gap_id="1",
            category=GapCategory.MISSING_HASH,
            severity=GapSeverity.CRITICAL,
            location=PolicyLocation(file_path="test.rego"),
            description="Missing hash",
        )

        low_gap = ConstitutionalGap(
            gap_id="2",
            category=GapCategory.MISSING_VALIDATION,
            severity=GapSeverity.LOW,
            location=PolicyLocation(file_path="test.rego"),
            description="Missing validation",
        )

        critical_score = classifier.calculate_priority_score(critical_gap)
        low_score = classifier.calculate_priority_score(low_gap)

        assert critical_score > low_score

    def test_category_multiplier_effect(self):
        """Test that category multiplier affects score."""
        classifier = GapClassifier()

        self_validation_gap = ConstitutionalGap(
            gap_id="1",
            category=GapCategory.SELF_VALIDATION,
            severity=GapSeverity.CRITICAL,
            location=PolicyLocation(file_path="test.rego"),
            description="Self validation",
        )

        missing_hash_gap = ConstitutionalGap(
            gap_id="2",
            category=GapCategory.MISSING_HASH,
            severity=GapSeverity.CRITICAL,
            location=PolicyLocation(file_path="test.rego"),
            description="Missing hash",
        )

        self_val_score = classifier.calculate_priority_score(self_validation_gap)
        missing_hash_score = classifier.calculate_priority_score(missing_hash_gap)

        # Self-validation has 2.0 multiplier vs 1.5 for missing hash
        assert self_val_score > missing_hash_score

    def test_prioritize_gaps_ordering(self):
        """Test that gaps are correctly ordered by priority."""
        classifier = GapClassifier()

        gaps = [
            ConstitutionalGap(
                gap_id="1",
                category=GapCategory.MISSING_VALIDATION,
                severity=GapSeverity.LOW,
                location=PolicyLocation(file_path="test.rego"),
                description="Low priority",
            ),
            ConstitutionalGap(
                gap_id="2",
                category=GapCategory.SELF_VALIDATION,
                severity=GapSeverity.CRITICAL,
                location=PolicyLocation(file_path="test.rego"),
                description="Highest priority",
            ),
            ConstitutionalGap(
                gap_id="3",
                category=GapCategory.MISSING_AUDIT,
                severity=GapSeverity.HIGH,
                location=PolicyLocation(file_path="test.rego"),
                description="Medium priority",
            ),
        ]

        prioritized = classifier.prioritize_gaps(gaps)

        # Critical self-validation should be first
        assert prioritized[0].gap_id == "2"
        # Low priority should be last
        assert prioritized[-1].gap_id == "1"

    def test_severity_for_category_mapping(self):
        """Test default severity mapping for categories."""
        classifier = GapClassifier()

        assert (
            classifier.get_severity_for_category(GapCategory.SELF_VALIDATION)
            == GapSeverity.CRITICAL
        )
        assert (
            classifier.get_severity_for_category(GapCategory.MISSING_HASH) == GapSeverity.CRITICAL
        )
        assert classifier.get_severity_for_category(GapCategory.MISSING_AUDIT) == GapSeverity.HIGH
        assert (
            classifier.get_severity_for_category(GapCategory.INSECURE_DEFAULT) == GapSeverity.MEDIUM
        )


class TestRemediationRecommendations:
    """Tests for remediation recommendation generation."""

    def test_generate_suggestion_for_missing_hash(self):
        """Test remediation suggestion for missing hash."""
        engine = RemediationEngine()
        gap = ConstitutionalGap(
            gap_id="1",
            category=GapCategory.MISSING_HASH,
            severity=GapSeverity.CRITICAL,
            location=PolicyLocation(file_path="test.rego"),
            description="Missing constitutional hash",
        )

        suggestion = engine.generate_suggestion(gap)

        assert suggestion.remediation_type == RemediationType.ADD_CODE
        assert "constitutional_hash" in suggestion.code_snippet.lower()
        assert "CONSTITUTIONAL_HASH" in suggestion.code_snippet
        assert suggestion.effort_estimate == "low"

    def test_generate_suggestion_for_self_validation(self):
        """Test remediation suggestion for self-validation."""
        engine = RemediationEngine()
        gap = ConstitutionalGap(
            gap_id="1",
            category=GapCategory.SELF_VALIDATION,
            severity=GapSeverity.CRITICAL,
            location=PolicyLocation(file_path="test.rego"),
            description="Self validation detected",
        )

        suggestion = engine.generate_suggestion(gap)

        assert suggestion.remediation_type == RemediationType.MODIFY_CODE
        assert "JUDICIAL" in suggestion.code_snippet or "different agent" in suggestion.code_snippet
        assert suggestion.effort_estimate == "high"

    def test_generate_suggestion_for_insecure_default(self):
        """Test remediation suggestion for insecure default."""
        engine = RemediationEngine()
        gap = ConstitutionalGap(
            gap_id="1",
            category=GapCategory.INSECURE_DEFAULT,
            severity=GapSeverity.MEDIUM,
            location=PolicyLocation(file_path="test.rego"),
            description="Default allow pattern",
        )

        suggestion = engine.generate_suggestion(gap)

        assert "deny" in suggestion.code_snippet.lower()
        assert suggestion.effort_estimate == "low"

    def test_generate_batch_suggestions(self):
        """Test batch generation of suggestions."""
        engine = RemediationEngine()
        gaps = [
            ConstitutionalGap(
                gap_id="1",
                category=GapCategory.MISSING_HASH,
                severity=GapSeverity.CRITICAL,
                location=PolicyLocation(file_path="test.rego"),
                description="Missing hash",
            ),
            ConstitutionalGap(
                gap_id="2",
                category=GapCategory.MISSING_AUDIT,
                severity=GapSeverity.HIGH,
                location=PolicyLocation(file_path="test.rego"),
                description="Missing audit",
            ),
        ]

        suggestions = engine.generate_batch_suggestions(gaps)

        assert len(suggestions) == 2
        assert all(s.constitutional_hash == CONSTITUTIONAL_HASH for s in suggestions)

    def test_suggestion_includes_gap_reference(self):
        """Test that suggestions reference their gap."""
        engine = RemediationEngine()
        gap = ConstitutionalGap(
            gap_id="gap-123",
            category=GapCategory.MISSING_HASH,
            severity=GapSeverity.CRITICAL,
            location=PolicyLocation(file_path="test.rego"),
            description="Missing hash",
        )

        suggestion = engine.generate_suggestion(gap)

        assert suggestion.gap_id == "gap-123"

    def test_unknown_category_fallback(self):
        """Test fallback for unknown category."""
        engine = RemediationEngine()
        gap = ConstitutionalGap(
            gap_id="1",
            category=GapCategory.NO_CONSTITUTIONAL_CHECK,  # Not in templates
            severity=GapSeverity.MEDIUM,
            location=PolicyLocation(file_path="test.rego"),
            description="Unknown gap type",
        )

        suggestion = engine.generate_suggestion(gap)

        assert suggestion.remediation_type == RemediationType.MANUAL_REVIEW


class TestGapClosureTracking:
    """Tests for gap closure tracking dashboard."""

    def test_register_and_track_gap(self):
        """Test registering and tracking a gap."""
        tracker = GapTracker()
        gap = ConstitutionalGap(
            gap_id="1",
            category=GapCategory.MISSING_HASH,
            severity=GapSeverity.CRITICAL,
            location=PolicyLocation(file_path="test.rego"),
            description="Missing hash",
        )

        tracker.register_gap(gap)
        retrieved = tracker.get_gap("1")

        assert retrieved is not None
        assert retrieved.status == GapStatus.OPEN

    def test_update_gap_status(self):
        """Test updating gap status."""
        tracker = GapTracker()
        gap = ConstitutionalGap(
            gap_id="1",
            category=GapCategory.MISSING_HASH,
            severity=GapSeverity.CRITICAL,
            location=PolicyLocation(file_path="test.rego"),
            description="Missing hash",
        )

        tracker.register_gap(gap)
        updated = tracker.update_status("1", GapStatus.IN_PROGRESS, assigned_to="dev-1")

        assert updated.status == GapStatus.IN_PROGRESS
        assert updated.assigned_to == "dev-1"

    def test_resolve_gap_records_time(self):
        """Test that resolving a gap records resolution time."""
        tracker = GapTracker()
        gap = ConstitutionalGap(
            gap_id="1",
            category=GapCategory.MISSING_HASH,
            severity=GapSeverity.CRITICAL,
            location=PolicyLocation(file_path="test.rego"),
            description="Missing hash",
        )

        tracker.register_gap(gap)
        resolved = tracker.update_status("1", GapStatus.RESOLVED, notes="Fixed")

        assert resolved.status == GapStatus.RESOLVED
        assert resolved.resolved_at is not None
        assert resolved.resolution_notes == "Fixed"

    def test_get_gaps_by_status(self):
        """Test filtering gaps by status."""
        tracker = GapTracker()

        for i in range(5):
            gap = ConstitutionalGap(
                gap_id=str(i),
                category=GapCategory.MISSING_HASH,
                severity=GapSeverity.CRITICAL,
                location=PolicyLocation(file_path="test.rego"),
                description=f"Gap {i}",
            )
            tracker.register_gap(gap)

        tracker.update_status("0", GapStatus.RESOLVED)
        tracker.update_status("1", GapStatus.IN_PROGRESS)

        open_gaps = tracker.get_gaps_by_status(GapStatus.OPEN)
        assert len(open_gaps) == 3

    def test_get_gaps_by_severity(self):
        """Test filtering gaps by severity."""
        tracker = GapTracker()

        tracker.register_gap(
            ConstitutionalGap(
                gap_id="1",
                category=GapCategory.MISSING_HASH,
                severity=GapSeverity.CRITICAL,
                location=PolicyLocation(file_path="test.rego"),
                description="Critical gap",
            )
        )
        tracker.register_gap(
            ConstitutionalGap(
                gap_id="2",
                category=GapCategory.MISSING_VALIDATION,
                severity=GapSeverity.LOW,
                location=PolicyLocation(file_path="test.rego"),
                description="Low gap",
            )
        )

        critical_gaps = tracker.get_gaps_by_severity(GapSeverity.CRITICAL)
        assert len(critical_gaps) == 1

    def test_dashboard_metrics(self):
        """Test dashboard metrics calculation."""
        tracker = GapTracker()

        for i in range(10):
            gap = ConstitutionalGap(
                gap_id=str(i),
                category=GapCategory.MISSING_HASH,
                severity=GapSeverity.CRITICAL,
                location=PolicyLocation(file_path="test.rego"),
                description=f"Gap {i}",
            )
            tracker.register_gap(gap)

        # Resolve 3 gaps
        for i in range(3):
            tracker.update_status(str(i), GapStatus.RESOLVED)

        # 2 in progress
        tracker.update_status("3", GapStatus.IN_PROGRESS)
        tracker.update_status("4", GapStatus.IN_PROGRESS)

        dashboard = tracker.get_dashboard("tenant-1")

        assert dashboard.total_gaps == 10
        assert dashboard.resolved_gaps == 3
        assert dashboard.in_progress_gaps == 2
        assert dashboard.open_gaps == 5
        assert dashboard.closure_rate == 30.0

    def test_dashboard_includes_severity_breakdown(self):
        """Test dashboard includes severity breakdown."""
        tracker = GapTracker()

        tracker.register_gap(
            ConstitutionalGap(
                gap_id="1",
                category=GapCategory.MISSING_HASH,
                severity=GapSeverity.CRITICAL,
                location=PolicyLocation(file_path="test.rego"),
                description="Critical",
            )
        )
        tracker.register_gap(
            ConstitutionalGap(
                gap_id="2",
                category=GapCategory.MISSING_AUDIT,
                severity=GapSeverity.HIGH,
                location=PolicyLocation(file_path="test.rego"),
                description="High",
            )
        )

        dashboard = tracker.get_dashboard("tenant-1")

        assert "critical" in dashboard.gaps_by_severity
        assert "high" in dashboard.gaps_by_severity
        assert dashboard.constitutional_hash == CONSTITUTIONAL_HASH


class TestConstitutionalCompliance:
    """Tests for constitutional compliance in gap analysis."""

    def test_gaps_include_constitutional_hash(self):
        """Test that all gaps include constitutional hash."""
        gap = ConstitutionalGap(
            gap_id="1",
            category=GapCategory.MISSING_HASH,
            severity=GapSeverity.CRITICAL,
            location=PolicyLocation(file_path="test.rego"),
            description="Test",
        )

        assert gap.constitutional_hash == CONSTITUTIONAL_HASH

    def test_scan_results_include_hash(self):
        """Test that scan results include constitutional hash."""
        scanner = ConstitutionalPolicyScanner()
        result = scanner.scan_policies_batch([("test", "test.rego")], "tenant-1")

        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_suggestions_include_hash(self):
        """Test that suggestions include constitutional hash."""
        engine = RemediationEngine()
        gap = ConstitutionalGap(
            gap_id="1",
            category=GapCategory.MISSING_HASH,
            severity=GapSeverity.CRITICAL,
            location=PolicyLocation(file_path="test.rego"),
            description="Test",
        )

        suggestion = engine.generate_suggestion(gap)

        assert suggestion.constitutional_hash == CONSTITUTIONAL_HASH

    def test_dashboard_includes_hash(self):
        """Test that dashboard includes constitutional hash."""
        tracker = GapTracker()
        dashboard = tracker.get_dashboard("tenant-1")

        assert dashboard.constitutional_hash == CONSTITUTIONAL_HASH
