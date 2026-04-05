# mypy: ignore-errors
# Mixin class: all methods reference self.* attrs provided by OPAClientCore.
# Cannot statically verify mixin composition without Protocol-based injection.
"""
ACGS-2 OPA Client — Health & Multi-Path Mixin
Constitutional Hash: 608508a9bd224290

Provides multi-path policy evaluation, health check, and
support-set candidate generation methods for OPAClient.
"""

import json
import os

from httpx import (
    ConnectError as HTTPConnectError,
)
from httpx import (
    ConnectTimeout as HTTPConnectTimeout,
)
from httpx import (
    HTTPStatusError,
)
from httpx import (
    TimeoutException as HTTPTimeoutException,
)

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)


class OPAClientHealthMixin:
    """Mixin providing multi-path evaluation and health-check methods for OPAClient.

    All methods reference ``self`` attributes that are initialized
    by ``OPAClientCore.__init__``.
    """

    async def evaluate_policy_multi_path(
        self,
        input_data: JSONDict,
        policy_path: str = "data.acgs.allow",
        *,
        max_paths: int = 8,
    ) -> JSONDict:
        """Evaluate a policy across multiple candidate support sets.

        The baseline decision is always evaluated first. If ``support_set_candidates``
        is provided in input_data, each candidate dict is merged into the baseline
        input and evaluated as an alternative path. The result includes all explored
        paths plus minimal support sets among allowed alternatives.
        """
        sanitized_input: JSONDict = {
            key: value for key, value in input_data.items() if key != "support_set_candidates"
        }
        baseline = await self.evaluate_policy(sanitized_input, policy_path=policy_path)

        candidates = self._extract_support_set_candidates(input_data, max_paths=max_paths)
        paths: list[JSONDict] = [
            {
                "path_id": "baseline",
                "allowed": baseline.get("allowed", False),
                "reason": baseline.get("reason", ""),
                "support_set": {},
                "metadata": baseline.get("metadata", {}),
            }
        ]

        for idx, support_set in enumerate(candidates, start=1):
            candidate_input: JSONDict = {**sanitized_input, **support_set}
            try:
                decision = await self.evaluate_policy(candidate_input, policy_path=policy_path)
            except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError) as e:
                decision = self._handle_evaluation_error(e, policy_path)

            paths.append(
                {
                    "path_id": f"candidate_{idx}",
                    "allowed": decision.get("allowed", False),
                    "reason": decision.get("reason", ""),
                    "support_set": support_set,
                    "metadata": decision.get("metadata", {}),
                }
            )

        allowed_paths = [path for path in paths if path.get("allowed")]
        minimal_support_sets = self._minimal_support_sets(allowed_paths)
        diversity = self._compute_diversity_metrics(paths, allowed_paths, minimal_support_sets)
        self._multipath_evaluation_count += 1
        self._multipath_last_path_count = len(paths)
        self._multipath_last_diversity_ratio = float(diversity.get("path_diversity_ratio", 0.0))
        self._multipath_last_support_family_count = int(diversity.get("support_family_count", 0))

        return {
            "result": baseline.get("result", False),
            "allowed": baseline.get("allowed", False),
            "reason": baseline.get("reason", ""),
            "metadata": {
                **baseline.get("metadata", {}),
                "path_count": len(paths),
                "allowed_path_count": len(allowed_paths),
                "minimal_support_set_count": len(minimal_support_sets),
                **diversity,
            },
            "paths": paths,
            "minimal_support_sets": minimal_support_sets,
        }

    def _extract_support_set_candidates(
        self, input_data: JSONDict, max_paths: int
    ) -> list[JSONDict]:
        """Extract candidate support sets used for multi-path exploration."""
        raw = input_data.get("support_set_candidates")
        if not isinstance(raw, list):
            return []

        candidates: list[JSONDict] = []
        for item in raw:
            if isinstance(item, dict):
                candidates.append(item)
            if len(candidates) >= max_paths:
                break
        return candidates

    def _is_temporal_multi_path_enabled(self) -> bool:
        """Return whether temporal history multi-path exploration is enabled."""
        return os.getenv("ACGS_ENABLE_TEMPORAL_MULTI_PATH", "").lower() in ("1", "true", "yes")

    def _is_multi_path_candidate_generation_enabled(self) -> bool:
        """Return whether generic support-set candidate generation is enabled."""
        return os.getenv("ACGS_ENABLE_OPA_MULTI_PATH_GENERATION", "").lower() in (
            "1",
            "true",
            "yes",
        )

    def _build_temporal_support_set_candidates(
        self, action_history: list[str], max_paths: int = 6
    ) -> list[JSONDict]:
        """Generate temporal support-set candidates from action history windows."""
        if len(action_history) <= 1:
            return []

        candidates: list[JSONDict] = []
        seen: set[tuple[str, ...]] = set()

        # Prefix without latest step (counterfactual of missing immediate prerequisite).
        prefix = tuple(action_history[:-1])
        if prefix and prefix not in seen:
            seen.add(prefix)
            candidates.append({"action_history": list(prefix)})

        # Short recent windows emphasize alternative temporal routes.
        max_window = min(len(action_history), max_paths + 1)
        for window in range(1, max_window):
            recent = tuple(action_history[-window:])
            if recent and recent not in seen:
                seen.add(recent)
                candidates.append({"action_history": list(recent)})
            if len(candidates) >= max_paths:
                break

        return candidates[:max_paths]

    def _compute_diversity_metrics(
        self,
        paths: list[JSONDict],
        allowed_paths: list[JSONDict],
        minimal_support_sets: list[JSONDict],
    ) -> JSONDict:
        """Compute diversity-oriented metadata for multi-path evaluation."""
        support_families: set[tuple[str, ...]] = set()
        for path in paths:
            support_set = path.get("support_set", {})
            if not isinstance(support_set, dict):
                continue
            support_families.add(tuple(sorted(support_set.keys())))

        allowed_count = len(allowed_paths)
        minimal_count = len(minimal_support_sets)
        diversity_ratio = minimal_count / allowed_count if allowed_count > 0 else 0.0

        return {
            "path_diversity_ratio": diversity_ratio,
            "support_family_count": len(support_families),
        }

    def _build_constitutional_support_set_candidates(
        self, message: JSONDict, max_paths: int = 6
    ) -> list[JSONDict]:
        """Build constitutional candidates by removing optional boolean evidence flags."""
        metadata = message.get("metadata", {})
        if not isinstance(metadata, dict):
            return []

        true_flags = [key for key, value in metadata.items() if isinstance(value, bool) and value]
        candidates: list[JSONDict] = []
        for flag in true_flags[:max_paths]:
            adjusted_metadata = {**metadata}
            adjusted_metadata.pop(flag, None)
            adjusted_message = {**message, "metadata": adjusted_metadata}
            candidates.append({"message": adjusted_message})
        return candidates

    def _build_authorization_support_set_candidates(
        self, context: JSONDict, max_paths: int = 6
    ) -> list[JSONDict]:
        """Build authorization candidates by varying optional context evidence."""
        candidates: list[JSONDict] = []
        seen: set[str] = set()

        true_flags = [key for key, value in context.items() if isinstance(value, bool) and value]
        for flag in true_flags:
            adjusted_context = {**context}
            adjusted_context.pop(flag, None)
            signature = json.dumps(adjusted_context, sort_keys=True)
            if signature in seen:
                continue
            seen.add(signature)
            candidates.append({"context": adjusted_context})
            if len(candidates) >= max_paths:
                return candidates

        roles = context.get("roles")
        if isinstance(roles, list):
            role_values = [role for role in roles if isinstance(role, str)]
            for idx in range(len(role_values)):
                adjusted_context = {
                    **context,
                    "roles": role_values[:idx] + role_values[idx + 1 :],
                }
                signature = json.dumps(adjusted_context, sort_keys=True)
                if signature in seen:
                    continue
                seen.add(signature)
                candidates.append({"context": adjusted_context})
                if len(candidates) >= max_paths:
                    break

        return candidates

    def _build_policy_lifecycle_support_set_candidates(
        self, input_data: JSONDict, max_paths: int = 6
    ) -> list[JSONDict]:
        """Build support-set candidates for policy lifecycle governance actions."""
        action = input_data.get("action", "")
        if not isinstance(action, str):
            return []

        lifecycle_actions = {
            "modify_policy",
            "apply_policy_change",
            "update_policy",
            "publish_policy",
            "rollback_policy",
        }
        if action not in lifecycle_actions:
            return []

        candidates: list[JSONDict] = []
        seen: set[str] = set()

        optional_flags = [
            "requires_human_approval",
            "has_security_review",
            "has_compliance_review",
        ]
        for flag in optional_flags:
            if input_data.get(flag) is True:
                candidate = {flag: False}
                signature = json.dumps(candidate, sort_keys=True)
                if signature in seen:
                    continue
                seen.add(signature)
                candidates.append(candidate)
                if len(candidates) >= max_paths:
                    return candidates

        context = input_data.get("context", {})
        if isinstance(context, dict):
            for flag in optional_flags:
                if context.get(flag) is True:
                    adjusted_context = {**context, flag: False}
                    candidate = {"context": adjusted_context}
                    signature = json.dumps(candidate, sort_keys=True)
                    if signature in seen:
                        continue
                    seen.add(signature)
                    candidates.append(candidate)
                    if len(candidates) >= max_paths:
                        break

        return candidates

    def _minimal_support_sets(self, allowed_paths: list[JSONDict]) -> list[JSONDict]:
        """Return only minimal support sets (drop strict supersets)."""
        normalized: list[tuple[frozenset[str], JSONDict]] = []
        for path in allowed_paths:
            support_set = path.get("support_set", {})
            if not isinstance(support_set, dict):
                continue
            signature = frozenset(
                f"{key}={json.dumps(value, sort_keys=True)}" for key, value in support_set.items()
            )
            normalized.append((signature, support_set))

        minimal: list[tuple[frozenset[str], JSONDict]] = []
        for idx, (sig, support) in enumerate(normalized):
            is_minimal = True
            for other_idx, (other_sig, _other_support) in enumerate(normalized):
                if idx == other_idx:
                    continue
                if other_sig < sig:
                    is_minimal = False
                    break
            if is_minimal:
                minimal.append((sig, support))

        unique: dict[frozenset[str], JSONDict] = {}
        for sig, support in minimal:
            unique[sig] = support
        return list(unique.values())

    async def health_check(self) -> JSONDict:
        """Check OPA service health."""
        try:
            if self.mode == "http" and self._http_client:
                response = await self._http_client.get(f"{self.opa_url}/health", timeout=2.0)
                response.raise_for_status()
                return {"status": "healthy", "mode": "http"}
            return {"status": "healthy", "mode": self.mode}
        except (HTTPConnectError, HTTPConnectTimeout) as e:
            return {"status": "unhealthy", "error": f"Connection failed: {e}"}
        except HTTPTimeoutException as e:
            return {"status": "unhealthy", "error": f"Timeout: {e}"}
        except HTTPStatusError as e:
            return {"status": "unhealthy", "error": f"HTTP error: {e}"}
