"""exp185: RuleProvenanceGraph — rule lineage and deprecation tracking.

Directed graph of rule evolution: which rules replaced which, deprecation
chains, and impact analysis for understanding how governance has evolved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ProvenanceRelation(Enum):
    REPLACED_BY = "replaced_by"
    DEPRECATED_BY = "deprecated_by"
    SPLIT_INTO = "split_into"
    MERGED_FROM = "merged_from"
    DERIVED_FROM = "derived_from"


@dataclass(frozen=True)
class ProvenanceEdge:
    source_rule_id: str
    target_rule_id: str
    relation: ProvenanceRelation
    reason: str
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source_rule_id,
            "target": self.target_rule_id,
            "relation": self.relation.value,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class RuleNode:
    rule_id: str
    version: int = 1
    is_active: bool = True
    is_deprecated: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    deprecated_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "rule_id": self.rule_id,
            "version": self.version,
            "is_active": self.is_active,
            "is_deprecated": self.is_deprecated,
            "created_at": self.created_at.isoformat(),
        }
        if self.deprecated_at:
            d["deprecated_at"] = self.deprecated_at.isoformat()
        if self.metadata:
            d["metadata"] = self.metadata
        return d


class RuleProvenanceGraph:
    """Directed graph tracking rule evolution, deprecation, and lineage.

    Enables impact analysis: "if I deprecate rule X, what depends on it?"
    and history queries: "what did rule Y replace?"
    """

    __slots__ = ("_nodes", "_edges", "_outgoing", "_incoming")

    def __init__(self) -> None:
        self._nodes: dict[str, RuleNode] = {}
        self._edges: list[ProvenanceEdge] = []
        self._outgoing: dict[str, list[int]] = {}
        self._incoming: dict[str, list[int]] = {}

    def add_rule(
        self,
        rule_id: str,
        version: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> RuleNode:
        if rule_id in self._nodes:
            msg = f"Rule already exists: {rule_id}"
            raise ValueError(msg)
        node = RuleNode(rule_id=rule_id, version=version, metadata=metadata or {})
        self._nodes[rule_id] = node
        return node

    def add_relation(
        self,
        source_id: str,
        target_id: str,
        relation: ProvenanceRelation,
        reason: str = "",
    ) -> ProvenanceEdge:
        if source_id not in self._nodes:
            msg = f"Unknown source rule: {source_id}"
            raise ValueError(msg)
        if target_id not in self._nodes:
            msg = f"Unknown target rule: {target_id}"
            raise ValueError(msg)
        if source_id == target_id:
            msg = "Self-referencing provenance not allowed"
            raise ValueError(msg)

        edge = ProvenanceEdge(
            source_rule_id=source_id,
            target_rule_id=target_id,
            relation=relation,
            reason=reason,
            timestamp=datetime.now(timezone.utc),
        )
        idx = len(self._edges)
        self._edges.append(edge)
        self._outgoing.setdefault(source_id, []).append(idx)
        self._incoming.setdefault(target_id, []).append(idx)
        return edge

    def deprecate_rule(
        self,
        rule_id: str,
        replaced_by: str | None = None,
        reason: str = "",
    ) -> None:
        if rule_id not in self._nodes:
            msg = f"Unknown rule: {rule_id}"
            raise ValueError(msg)
        node = self._nodes[rule_id]
        node.is_deprecated = True
        node.is_active = False
        node.deprecated_at = datetime.now(timezone.utc)

        if replaced_by is not None:
            if replaced_by not in self._nodes:
                msg = f"Unknown replacement rule: {replaced_by}"
                raise ValueError(msg)
            self.add_relation(rule_id, replaced_by, ProvenanceRelation.REPLACED_BY, reason)

    def get_node(self, rule_id: str) -> RuleNode | None:
        return self._nodes.get(rule_id)

    def successors(self, rule_id: str) -> list[ProvenanceEdge]:
        indices = self._outgoing.get(rule_id, [])
        return [self._edges[i] for i in indices]

    def predecessors(self, rule_id: str) -> list[ProvenanceEdge]:
        indices = self._incoming.get(rule_id, [])
        return [self._edges[i] for i in indices]

    def lineage(self, rule_id: str) -> list[str]:
        """Trace the full ancestry of a rule back to its roots."""
        visited: set[str] = set()
        chain: list[str] = []

        def _walk_back(rid: str) -> None:
            if rid in visited:
                return
            visited.add(rid)
            chain.append(rid)
            for edge in self.predecessors(rid):
                _walk_back(edge.source_rule_id)

        _walk_back(rule_id)
        return chain

    def descendants(self, rule_id: str) -> list[str]:
        """Find all rules that evolved from this rule."""
        visited: set[str] = set()
        result: list[str] = []

        def _walk_forward(rid: str) -> None:
            if rid in visited:
                return
            visited.add(rid)
            result.append(rid)
            for edge in self.successors(rid):
                _walk_forward(edge.target_rule_id)

        _walk_forward(rule_id)
        return result

    def active_replacement(self, rule_id: str) -> str | None:
        """Find the currently active rule that replaced a deprecated one."""
        for desc_id in self.descendants(rule_id):
            node = self._nodes.get(desc_id)
            if node and node.is_active and desc_id != rule_id:
                return desc_id
        return None

    def deprecated_rules(self) -> list[RuleNode]:
        return [n for n in self._nodes.values() if n.is_deprecated]

    def active_rules(self) -> list[RuleNode]:
        return [n for n in self._nodes.values() if n.is_active]

    def roots(self) -> list[str]:
        """Rules with no predecessors (original rules)."""
        return [rid for rid in self._nodes if rid not in self._incoming]

    def leaves(self) -> list[str]:
        """Rules with no successors (current endpoints)."""
        return [rid for rid in self._nodes if rid not in self._outgoing]

    def impact_analysis(self, rule_id: str) -> dict[str, Any]:
        """Analyze the impact of deprecating a rule."""
        descs = self.descendants(rule_id)
        active_descs = [d for d in descs if self._nodes[d].is_active and d != rule_id]
        dep_descs = [d for d in descs if self._nodes[d].is_deprecated and d != rule_id]
        return {
            "rule_id": rule_id,
            "total_descendants": len(descs) - 1,
            "active_descendants": active_descs,
            "deprecated_descendants": dep_descs,
            "is_leaf": rule_id in self.leaves(),
            "lineage_depth": len(self.lineage(rule_id)),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": {rid: n.to_dict() for rid, n in self._nodes.items()},
            "edges": [e.to_dict() for e in self._edges],
            "stats": {
                "total_rules": len(self._nodes),
                "active": len(self.active_rules()),
                "deprecated": len(self.deprecated_rules()),
                "roots": len(self.roots()),
                "leaves": len(self.leaves()),
                "edges": len(self._edges),
            },
        }

    def __len__(self) -> int:
        return len(self._nodes)
