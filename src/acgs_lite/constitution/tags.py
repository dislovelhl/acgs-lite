"""Tagging and labeling system for governance rules and artifacts.

Provides a flexible tag registry with optional namespaces, bulk tagging,
tag-based artifact querying, tag renaming/merging, and usage statistics.

Example::

    from acgs_lite.constitution.tags import TagRegistry

    registry = TagRegistry()
    registry.tag("rule:SAFE-001", ["pii", "gdpr", "critical"])
    registry.tag("rule:SAFE-002", ["pii", "financial"])

    pii_items = registry.items_for_tag("pii")
    assert "rule:SAFE-001" in pii_items
    assert "rule:SAFE-002" in pii_items

    tags = registry.tags_for("rule:SAFE-001")
    assert "gdpr" in tags

    registry.rename_tag("critical", "severity:critical")
    assert "severity:critical" in registry.tags_for("rule:SAFE-001")
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TagStats:
    """Usage statistics for a single tag."""

    tag: str
    item_count: int
    items: list[str] = field(default_factory=list)


class TagRegistry:
    """Flexible tagging system for governance rules and artifacts.

    Supports arbitrary string tags, bulk operations, tag renaming,
    tag merging, namespace-prefixed tags, and usage statistics.

    Example::

        reg = TagRegistry()
        reg.tag("rule:R1", ["security", "pii"])
        reg.tag("rule:R2", ["security"])

        security_items = reg.items_for_tag("security")
        assert len(security_items) == 2

        reg.merge_tags("pii", "gdpr:pii")
        assert "gdpr:pii" in reg.tags_for("rule:R1")
        assert "pii" not in reg.tags_for("rule:R1")
    """

    def __init__(self) -> None:
        self._item_tags: dict[str, set[str]] = {}
        self._tag_items: dict[str, set[str]] = {}

    def tag(self, item_id: str, tags: list[str]) -> None:
        """Add one or more tags to *item_id*."""
        current = self._item_tags.setdefault(item_id, set())
        for t in tags:
            current.add(t)
            self._tag_items.setdefault(t, set()).add(item_id)

    def untag(self, item_id: str, tags: list[str]) -> None:
        """Remove specific tags from *item_id*."""
        current = self._item_tags.get(item_id, set())
        for t in tags:
            current.discard(t)
            bucket = self._tag_items.get(t)
            if bucket is not None:
                bucket.discard(item_id)
                if not bucket:
                    del self._tag_items[t]
        if not current and item_id in self._item_tags:
            del self._item_tags[item_id]

    def clear_tags(self, item_id: str) -> None:
        """Remove all tags from *item_id*."""
        tags = list(self._item_tags.get(item_id, set()))
        self.untag(item_id, tags)

    def remove_item(self, item_id: str) -> None:
        """Completely unregister *item_id* from the registry."""
        self.clear_tags(item_id)

    def tags_for(self, item_id: str) -> set[str]:
        return set(self._item_tags.get(item_id, set()))

    def items_for_tag(self, tag: str) -> set[str]:
        return set(self._tag_items.get(tag, set()))

    def items_for_any_tag(self, tags: list[str]) -> set[str]:
        result: set[str] = set()
        for t in tags:
            result |= self._tag_items.get(t, set())
        return result

    def items_for_all_tags(self, tags: list[str]) -> set[str]:
        if not tags:
            return set()
        result = set(self._tag_items.get(tags[0], set()))
        for t in tags[1:]:
            result &= self._tag_items.get(t, set())
        return result

    def rename_tag(self, old_tag: str, new_tag: str) -> int:
        """Rename *old_tag* to *new_tag* across all items. Returns items updated."""
        items = list(self._tag_items.pop(old_tag, set()))
        for item_id in items:
            bucket = self._item_tags.get(item_id)
            if bucket is not None:
                bucket.discard(old_tag)
                bucket.add(new_tag)
            self._tag_items.setdefault(new_tag, set()).add(item_id)
        return len(items)

    def merge_tags(self, source_tag: str, target_tag: str) -> int:
        """Merge *source_tag* into *target_tag*, removing *source_tag*."""
        return self.rename_tag(source_tag, target_tag)

    def bulk_tag(self, item_ids: list[str], tags: list[str]) -> None:
        for item_id in item_ids:
            self.tag(item_id, tags)

    def bulk_untag(self, item_ids: list[str], tags: list[str]) -> None:
        for item_id in item_ids:
            self.untag(item_id, tags)

    def all_tags(self) -> list[str]:
        return sorted(self._tag_items.keys())

    def all_items(self) -> list[str]:
        return sorted(self._item_tags.keys())

    def tag_stats(self) -> list[TagStats]:
        return [
            TagStats(
                tag=tag,
                item_count=len(items),
                items=sorted(items),
            )
            for tag, items in sorted(self._tag_items.items())
        ]

    def stats_for_tag(self, tag: str) -> TagStats | None:
        items = self._tag_items.get(tag)
        if items is None:
            return None
        return TagStats(tag=tag, item_count=len(items), items=sorted(items))

    def summary(self) -> dict[str, object]:
        return {
            "total_tags": len(self._tag_items),
            "total_items": len(self._item_tags),
            "total_tag_assignments": sum(len(tags) for tags in self._item_tags.values()),
        }
