"""
ACGS-2 Enhanced Agent Bus - Constitutional Diff Engine
Constitutional Hash: cdd01ef066bc6cf2

Engine to compute semantic diffs between constitutional versions,
highlighting added/removed/modified principles with detailed analysis.
"""

import difflib
from typing import Optional

from src.core.shared.types import JSONDict, JSONList
from typing_extensions import TypedDict

from enhanced_agent_bus.observability.structured_logging import get_logger


class _CumulativeChanges(TypedDict):
    """type definition for cumulative changes."""

    added_fields: JSONDict
    removed_fields: JSONDict
    modified_fields: JSONDict


class _CumulativeDiff(TypedDict):
    """type definition for cumulative diff."""

    version_count: int
    versions: list[JSONDict]
    cumulative_changes: _CumulativeChanges
    total_changes: int


from pydantic import BaseModel, Field  # noqa: E402

# Import centralized constitutional hash
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    # Fallback for standalone usage
    from src.core.shared.constants import CONSTITUTIONAL_HASH

from src.core.shared.json_utils import dumps as json_dumps  # noqa: E402
from src.core.shared.types import JSONDict  # noqa: E402

from .storage import ConstitutionalStorageService  # type: ignore[attr-defined]  # noqa: E402
from .version_model import ConstitutionalVersion  # noqa: E402

logger = get_logger(__name__)


class DiffChange(BaseModel):
    """Represents a single change in the diff.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    change_type: str = Field(..., pattern="^(added|removed|modified)$")
    path: str = Field(..., description="JSON path to the changed field")
    old_value: object | None = Field(None)
    new_value: object | None = Field(None)
    description: str = Field(default="")


class PrincipleChange(BaseModel):
    """Represents a change to a constitutional principle.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    principle_id: str = Field(...)
    change_type: str = Field(..., pattern="^(added|removed|modified)$")
    old_content: str | None = Field(None)
    new_content: str | None = Field(None)
    impact_level: str = Field(default="medium", pattern="^(low|medium|high|critical)$")


class SemanticDiff(BaseModel):
    """Semantic diff between two constitutional versions.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    from_version: str = Field(...)
    to_version: str = Field(...)
    from_version_id: str = Field(...)
    to_version_id: str = Field(...)
    from_hash: str = Field(...)
    to_hash: str = Field(...)
    hash_changed: bool = Field(...)

    # Detailed changes
    added_fields: JSONDict = Field(default_factory=dict)
    removed_fields: JSONDict = Field(default_factory=dict)
    modified_fields: dict[str, JSONDict] = Field(default_factory=dict)

    # Principle-level changes
    principle_changes: list[PrincipleChange] = Field(default_factory=list)

    # All changes as a flat list
    all_changes: list[DiffChange] = Field(default_factory=list)

    # Summary statistics
    total_changes: int = Field(default=0)
    additions_count: int = Field(default=0)
    removals_count: int = Field(default=0)
    modifications_count: int = Field(default=0)

    # Impact assessment
    impact_level: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    breaking_changes: list[str] = Field(default_factory=list)


class ConstitutionalDiffEngine:
    """Constitutional diff engine for computing semantic diffs.

    This engine provides:
    - JSON diff between any two constitutional versions
    - Principle-level change detection
    - Impact assessment for changes
    - Text-level diff for principle content
    - Breaking change detection

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(self, storage: ConstitutionalStorageService):
        """Initialize diff engine.

        Args:
            storage: ConstitutionalStorageService instance for version access
        """
        self.storage = storage

        # Fields that indicate breaking changes if modified
        self.breaking_fields = {
            "constitutional_hash",
            "version",
            "core_principles",
            "enforcement_rules",
            "maci_roles",
        }

    async def compute_diff(
        self, from_version_id: str, to_version_id: str, include_principles: bool = True
    ) -> SemanticDiff | None:
        """Compute semantic diff between two constitutional versions.

        Args:
            from_version_id: Source version ID
            to_version_id: Target version ID
            include_principles: Whether to analyze principle-level changes

        Returns:
            SemanticDiff object or None if versions not found
        """
        logger.info(f"[{CONSTITUTIONAL_HASH}] Computing diff: {from_version_id} -> {to_version_id}")

        # Get versions
        from_version = await self.storage.get_version(from_version_id)
        to_version = await self.storage.get_version(to_version_id)

        if not from_version or not to_version:
            logger.error(
                f"[{CONSTITUTIONAL_HASH}] Version not found "
                f"(from: {from_version_id}, to: {to_version_id})"
            )
            return None

        # Create base diff
        diff = SemanticDiff(
            from_version=from_version.version,
            to_version=to_version.version,
            from_version_id=from_version.version_id,
            to_version_id=to_version.version_id,
            from_hash=from_version.constitutional_hash,
            to_hash=to_version.constitutional_hash,
            hash_changed=from_version.constitutional_hash != to_version.constitutional_hash,
        )

        # Compute content diff
        self._compute_content_diff(diff, from_version.content, to_version.content)

        # Analyze principle changes if requested
        if include_principles:
            await self._analyze_principle_changes(diff, from_version, to_version)

        # Assess impact
        self._assess_impact(diff)

        # Detect breaking changes
        self._detect_breaking_changes(diff)

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Diff computed: "
            f"{diff.total_changes} changes, impact={diff.impact_level}"
        )

        return diff

    async def compute_diff_from_content(
        self,
        from_version_id: str,
        proposed_content: JSONDict,
    ) -> SemanticDiff | None:
        """Diff a stored version against proposed content (dict, not a version ID)."""
        from_version = await self.storage.get_version(from_version_id)
        if not from_version:
            logger.error(f"[{CONSTITUTIONAL_HASH}] Source version not found: {from_version_id}")
            return None

        diff = SemanticDiff(
            from_version=from_version.version,
            to_version="proposed",
            from_version_id=from_version.version_id,
            to_version_id="proposed",
            from_hash=from_version.constitutional_hash,
            to_hash="pending",
            hash_changed=True,
        )

        self._compute_content_diff(diff, from_version.content, proposed_content)
        self._assess_impact(diff)
        self._detect_breaking_changes(diff)

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Content diff computed: "
            f"{diff.total_changes} changes, impact={diff.impact_level}"
        )
        return diff

    def _compute_content_diff(
        self,
        diff: SemanticDiff,
        from_content: JSONDict,
        to_content: JSONDict,
        path: str = "",
    ) -> None:
        """Compute content diff recursively.

        Args:
            diff: SemanticDiff object to populate
            from_content: Source content dictionary
            to_content: Target content dictionary
            path: Current JSON path (for nested fields)
        """
        # Find added and modified fields
        for key, to_value in to_content.items():
            current_path = f"{path}.{key}" if path else key

            if key not in from_content:
                # Field added
                diff.added_fields[current_path] = to_value
                diff.all_changes.append(
                    DiffChange(
                        change_type="added",
                        path=current_path,
                        old_value=None,
                        new_value=to_value,
                        description=f"Added field: {current_path}",
                    )
                )
                diff.additions_count += 1

            elif from_content[key] != to_value:
                # Field modified
                from_val = from_content[key]

                # If both are dicts, recurse
                if isinstance(from_val, dict) and isinstance(to_value, dict):
                    self._compute_content_diff(diff, from_val, to_value, current_path)
                else:
                    diff.modified_fields[current_path] = {"from": from_val, "to": to_value}
                    diff.all_changes.append(
                        DiffChange(
                            change_type="modified",
                            path=current_path,
                            old_value=from_val,
                            new_value=to_value,
                            description=f"Modified field: {current_path}",
                        )
                    )
                    diff.modifications_count += 1

        # Find removed fields
        for key, from_value in from_content.items():
            if key not in to_content:
                current_path = f"{path}.{key}" if path else key
                diff.removed_fields[current_path] = from_value
                diff.all_changes.append(
                    DiffChange(
                        change_type="removed",
                        path=current_path,
                        old_value=from_value,
                        new_value=None,
                        description=f"Removed field: {current_path}",
                    )
                )
                diff.removals_count += 1

        # Update total count
        diff.total_changes = diff.additions_count + diff.removals_count + diff.modifications_count

    async def _analyze_principle_changes(
        self,
        diff: SemanticDiff,
        from_version: ConstitutionalVersion,
        to_version: ConstitutionalVersion,
    ) -> None:
        """Analyze changes at the principle level.

        Args:
            diff: SemanticDiff object to populate
            from_version: Source version
            to_version: Target version
        """
        # Extract principles from content (assuming they're in a "principles" key)
        from_principles = from_version.content.get("principles", {})
        to_principles = to_version.content.get("principles", {})

        # If principles are a dict
        if isinstance(from_principles, dict) and isinstance(to_principles, dict):
            self._analyze_dict_principles(diff, from_principles, to_principles)
        # If principles are a list
        elif isinstance(from_principles, list) and isinstance(to_principles, list):
            self._analyze_list_principles(diff, from_principles, to_principles)

    def _analyze_dict_principles(
        self, diff: SemanticDiff, from_principles: JSONDict, to_principles: JSONDict
    ) -> None:
        """Analyze principle changes when principles are stored as dict.

        Args:
            diff: SemanticDiff object to populate
            from_principles: Source principles
            to_principles: Target principles
        """
        # Added principles
        for principle_id, content in to_principles.items():
            if principle_id not in from_principles:
                diff.principle_changes.append(
                    PrincipleChange(
                        principle_id=principle_id,
                        change_type="added",
                        old_content=None,
                        new_content=self._stringify_principle(content),
                        impact_level="high",
                    )
                )

        # Modified principles
        for principle_id, from_content in from_principles.items():
            if principle_id in to_principles:
                to_content = to_principles[principle_id]
                if from_content != to_content:
                    diff.principle_changes.append(
                        PrincipleChange(
                            principle_id=principle_id,
                            change_type="modified",
                            old_content=self._stringify_principle(from_content),
                            new_content=self._stringify_principle(to_content),
                            impact_level=self._assess_principle_impact(
                                principle_id, from_content, to_content
                            ),
                        )
                    )

        # Removed principles
        for principle_id, content in from_principles.items():
            if principle_id not in to_principles:
                diff.principle_changes.append(
                    PrincipleChange(
                        principle_id=principle_id,
                        change_type="removed",
                        old_content=self._stringify_principle(content),
                        new_content=None,
                        impact_level="critical",
                    )
                )

    def _analyze_list_principles(
        self, diff: SemanticDiff, from_principles: JSONList, to_principles: JSONList
    ) -> None:
        """Analyze principle changes when principles are stored as list.

        Args:
            diff: SemanticDiff object to populate
            from_principles: Source principles
            to_principles: Target principles
        """
        # Simple list comparison
        from_set = set(self._stringify_principle(p) for p in from_principles)
        to_set = set(self._stringify_principle(p) for p in to_principles)

        # Added
        for idx, principle in enumerate(to_principles):
            principle_str = self._stringify_principle(principle)
            if principle_str not in from_set:
                diff.principle_changes.append(
                    PrincipleChange(
                        principle_id=f"principle_{idx}",
                        change_type="added",
                        old_content=None,
                        new_content=principle_str,
                        impact_level="high",
                    )
                )

        # Removed
        for idx, principle in enumerate(from_principles):
            principle_str = self._stringify_principle(principle)
            if principle_str not in to_set:
                diff.principle_changes.append(
                    PrincipleChange(
                        principle_id=f"principle_{idx}",
                        change_type="removed",
                        old_content=principle_str,
                        new_content=None,
                        impact_level="critical",
                    )
                )

    def _stringify_principle(self, principle: object) -> str:
        """Convert principle to string representation.

        Args:
            principle: Principle content (dict, str, or other)

        Returns:
            String representation
        """
        if isinstance(principle, str):
            return principle
        elif isinstance(principle, dict):
            return json_dumps(principle, sort_keys=True)  # type: ignore[no-any-return]
        else:
            return str(principle)

    def _assess_principle_impact(
        self, principle_id: str, from_content: object, to_content: object
    ) -> str:
        """Assess impact level of a principle change.

        Args:
            principle_id: Principle identifier
            from_content: Original content
            to_content: New content

        Returns:
            Impact level (low, medium, high, critical)
        """
        # Critical principles have highest impact
        critical_principles = {"core_governance", "enforcement", "maci"}
        if any(cp in principle_id.lower() for cp in critical_principles):
            return "critical"

        # Calculate content similarity
        from_str = self._stringify_principle(from_content)
        to_str = self._stringify_principle(to_content)

        # Use difflib to compute similarity ratio
        similarity = difflib.SequenceMatcher(None, from_str, to_str).ratio()

        if similarity >= 0.8:
            return "low"
        elif similarity >= 0.5:
            return "medium"
        else:
            return "high"

    def _assess_impact(self, diff: SemanticDiff) -> None:
        """Assess overall impact level of the diff.

        Args:
            diff: SemanticDiff object to update
        """
        # Critical if hash changed
        if diff.hash_changed:
            diff.impact_level = "critical"
            return

        # Critical if any principle removed
        if any(pc.change_type == "removed" for pc in diff.principle_changes):
            diff.impact_level = "critical"
            return

        # High if many changes or critical principle modified
        if diff.total_changes > 10:
            diff.impact_level = "high"
            return

        if any(pc.impact_level == "critical" for pc in diff.principle_changes):
            diff.impact_level = "critical"
            return

        # High if any principle added
        if any(pc.change_type == "added" for pc in diff.principle_changes):
            diff.impact_level = "high"
            return

        # Medium if moderate changes
        if diff.total_changes > 3:
            diff.impact_level = "medium"
            return

        # Low otherwise
        diff.impact_level = "low"

    def _detect_breaking_changes(self, diff: SemanticDiff) -> None:
        """Detect breaking changes in the diff.

        Args:
            diff: SemanticDiff object to update
        """
        # Check for breaking field modifications
        for field_path in diff.modified_fields.keys():
            # Extract root field name
            root_field = field_path.split(".")[0]
            if root_field in self.breaking_fields:
                diff.breaking_changes.append(
                    f"Breaking change: Modified critical field '{field_path}'"
                )

        # Check for breaking field removals
        for field_path in diff.removed_fields.keys():
            root_field = field_path.split(".")[0]
            if root_field in self.breaking_fields:
                diff.breaking_changes.append(
                    f"Breaking change: Removed critical field '{field_path}'"
                )

        # Check for principle removals
        for pc in diff.principle_changes:
            if pc.change_type == "removed":
                diff.breaking_changes.append(
                    f"Breaking change: Removed principle '{pc.principle_id}'"
                )

    async def compute_text_diff(self, from_version_id: str, to_version_id: str) -> str | None:
        """Compute text-level unified diff between two versions.

        Args:
            from_version_id: Source version ID
            to_version_id: Target version ID

        Returns:
            Unified diff string or None if versions not found
        """
        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Computing text diff: {from_version_id} -> {to_version_id}"
        )

        # Get versions
        from_version = await self.storage.get_version(from_version_id)
        to_version = await self.storage.get_version(to_version_id)

        if not from_version or not to_version:
            return None

        # Convert content to formatted JSON strings
        from_text = json_dumps(from_version.content, indent=2, sort_keys=True)
        to_text = json_dumps(to_version.content, indent=2, sort_keys=True)

        # Split into lines
        from_lines = from_text.splitlines(keepends=True)
        to_lines = to_text.splitlines(keepends=True)

        # Generate unified diff
        diff = difflib.unified_diff(
            from_lines,
            to_lines,
            fromfile=f"v{from_version.version}",
            tofile=f"v{to_version.version}",
            lineterm="",
        )

        return "".join(diff)

    async def compute_multi_version_diff(self, version_ids: list[str]) -> JSONDict | None:
        """Compute diff across multiple versions.

        Args:
            version_ids: list of version IDs in chronological order

        Returns:
            Dictionary with cumulative diff information
        """
        if len(version_ids) < 2:
            logger.warning(f"[{CONSTITUTIONAL_HASH}] Need at least 2 versions for multi-diff")
            return None

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Computing multi-version diff: {len(version_ids)} versions"
        )

        cumulative_diff: _CumulativeDiff = {
            "version_count": len(version_ids),
            "versions": [],
            "cumulative_changes": {
                "added_fields": {},
                "removed_fields": {},
                "modified_fields": {},
            },
            "total_changes": 0,
        }

        # Compute pairwise diffs
        for i in range(len(version_ids) - 1):
            from_id = version_ids[i]
            to_id = version_ids[i + 1]

            diff = await self.compute_diff(from_id, to_id, include_principles=True)
            if not diff:
                continue

            cumulative_diff["versions"].append(
                {
                    "from_version": diff.from_version,
                    "to_version": diff.to_version,
                    "changes": diff.total_changes,
                    "impact_level": diff.impact_level,
                }
            )

            # Accumulate changes
            cumulative_diff["cumulative_changes"]["added_fields"].update(diff.added_fields)  # type: ignore[index]
            cumulative_diff["cumulative_changes"]["removed_fields"].update(diff.removed_fields)  # type: ignore[index]
            cumulative_diff["cumulative_changes"]["modified_fields"].update(diff.modified_fields)  # type: ignore[index]
            cumulative_diff["total_changes"] += diff.total_changes

        return dict(cumulative_diff)  # type: ignore[return-value]
