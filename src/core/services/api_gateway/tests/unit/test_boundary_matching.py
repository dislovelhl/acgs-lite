"""Unit tests for fnmatch-based action boundary matching.
Constitutional Hash: 608508a9bd224290

Tests the boundary matching logic used by AutonomyTierEnforcementMiddleware
to evaluate whether a BOUNDED-tier agent's action_type falls within configured
action_boundaries (US-003).

Boundary matching semantics:
  - Exact match: 'read:documents' matches pattern 'read:documents'
  - Wildcard suffix: 'read:*' matches 'read:documents', 'read:users'
  - No match → BLOCKED (fail-closed)
  - Empty boundaries list → all actions BLOCKED (fail-closed)
  - None / empty action_type → BLOCKED

Tests invoke AutonomyTierEnforcementMiddleware._is_action_allowed directly
to verify the extracted boundary matching helper in isolation.
"""

from __future__ import annotations

import pytest

from src.core.services.api_gateway.middleware.autonomy_tier import (
    AutonomyTierEnforcementMiddleware,
)


class TestBoundaryMatchingExactMatch:
    """Exact pattern matching (no wildcard)."""

    @pytest.mark.unit
    def test_exact_match_approved(self) -> None:
        """Exact action type matches exact boundary pattern → True (APPROVED)."""
        assert (
            AutonomyTierEnforcementMiddleware._is_action_allowed(
                "read:documents", ["read:documents"]
            )
            is True
        )

    @pytest.mark.unit
    def test_exact_match_different_action_blocked(self) -> None:
        """Action type that differs from exact boundary pattern → False (BLOCKED)."""
        assert (
            AutonomyTierEnforcementMiddleware._is_action_allowed(
                "write:documents", ["read:documents"]
            )
            is False
        )

    @pytest.mark.unit
    def test_action_matches_one_of_many_exact_patterns(self) -> None:
        """Action type matching one of several exact patterns → True (APPROVED)."""
        assert (
            AutonomyTierEnforcementMiddleware._is_action_allowed(
                "read:documents", ["write:documents", "read:documents", "delete:documents"]
            )
            is True
        )

    @pytest.mark.unit
    def test_action_not_in_multi_exact_pattern_list_blocked(self) -> None:
        """Action type not matching any pattern in list → False (BLOCKED)."""
        assert (
            AutonomyTierEnforcementMiddleware._is_action_allowed(
                "delete:documents", ["read:documents", "write:documents"]
            )
            is False
        )


class TestBoundaryMatchingWildcard:
    """Wildcard pattern matching using fnmatch '*'."""

    @pytest.mark.unit
    def test_wildcard_matches_read_documents(self) -> None:
        """Pattern 'read:*' matches 'read:documents' → True (APPROVED)."""
        assert (
            AutonomyTierEnforcementMiddleware._is_action_allowed("read:documents", ["read:*"])
            is True
        )

    @pytest.mark.unit
    def test_wildcard_matches_read_users(self) -> None:
        """Pattern 'read:*' matches 'read:users' → True (APPROVED)."""
        assert (
            AutonomyTierEnforcementMiddleware._is_action_allowed("read:users", ["read:*"]) is True
        )

    @pytest.mark.unit
    def test_wildcard_does_not_match_different_prefix(self) -> None:
        """'write:anything' does not match boundary 'read:*' → False (BLOCKED)."""
        assert (
            AutonomyTierEnforcementMiddleware._is_action_allowed("write:anything", ["read:*"])
            is False
        )

    @pytest.mark.unit
    def test_dot_wildcard_matches_agent_query(self) -> None:
        """Wildcard 'agent.*' matches 'agent.query' → True (APPROVED)."""
        assert (
            AutonomyTierEnforcementMiddleware._is_action_allowed("agent.query", ["agent.*"]) is True
        )

    @pytest.mark.unit
    def test_dot_wildcard_does_not_match_system_shutdown(self) -> None:
        """Wildcard 'agent.*' does not match 'system.shutdown' → False (BLOCKED)."""
        assert (
            AutonomyTierEnforcementMiddleware._is_action_allowed("system.shutdown", ["agent.*"])
            is False
        )

    @pytest.mark.unit
    def test_multiple_patterns_first_matches(self) -> None:
        """Action matches first pattern in multi-pattern list → True (APPROVED)."""
        assert (
            AutonomyTierEnforcementMiddleware._is_action_allowed(
                "read:documents", ["read:*", "write:*"]
            )
            is True
        )

    @pytest.mark.unit
    def test_multiple_patterns_second_matches(self) -> None:
        """Action matches second pattern in multi-pattern list → True (APPROVED)."""
        assert (
            AutonomyTierEnforcementMiddleware._is_action_allowed(
                "write:documents", ["read:*", "write:*"]
            )
            is True
        )

    @pytest.mark.unit
    def test_multiple_patterns_none_match(self) -> None:
        """Action matches none of the patterns → False (BLOCKED)."""
        assert (
            AutonomyTierEnforcementMiddleware._is_action_allowed(
                "delete:documents", ["read:*", "write:*"]
            )
            is False
        )


class TestBoundaryMatchingFailClosed:
    """Fail-closed semantics: empty boundaries or null/empty inputs → BLOCKED."""

    @pytest.mark.unit
    def test_empty_boundaries_all_actions_blocked(self) -> None:
        """Empty action_boundaries list → False (BLOCKED) — fail-closed for zero permissions."""
        assert AutonomyTierEnforcementMiddleware._is_action_allowed("read:documents", []) is False

    @pytest.mark.unit
    def test_none_action_type_blocked(self) -> None:
        """None action_type against any boundary → False (BLOCKED)."""
        assert (
            AutonomyTierEnforcementMiddleware._is_action_allowed(
                None,
                ["read:*"],  # type: ignore[arg-type]
            )
            is False
        )

    @pytest.mark.unit
    def test_empty_string_action_type_blocked(self) -> None:
        """Empty string action_type against any boundary → False (BLOCKED)."""
        assert AutonomyTierEnforcementMiddleware._is_action_allowed("", ["read:*"]) is False

    @pytest.mark.unit
    def test_empty_boundaries_and_none_action_type_blocked(self) -> None:
        """Empty boundaries AND None action_type → False (BLOCKED)."""
        assert (
            AutonomyTierEnforcementMiddleware._is_action_allowed(
                None,
                [],  # type: ignore[arg-type]
            )
            is False
        )

    @pytest.mark.unit
    def test_empty_boundaries_wildcard_action_blocked(self) -> None:
        """Even a wildcard action_type against empty boundaries → False (BLOCKED)."""
        assert AutonomyTierEnforcementMiddleware._is_action_allowed("read:*", []) is False
