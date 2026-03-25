"""
Information Flow Control labels for Enhanced Agent Bus.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Confidentiality(IntEnum):
    """Confidentiality lattice ordered from least to most sensitive."""

    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    SECRET = 3


class Integrity(IntEnum):
    """Integrity lattice ordered from least to most trusted."""

    UNTRUSTED = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    TRUSTED = 4


@dataclass(frozen=True)
class IFCLabel:
    """Security label combining confidentiality and integrity."""

    confidentiality: Confidentiality = Confidentiality.PUBLIC
    integrity: Integrity = Integrity.MEDIUM

    def taint_merge(self, other: "IFCLabel") -> "IFCLabel":
        """Merge two labels conservatively."""
        return IFCLabel(
            confidentiality=max(self.confidentiality, other.confidentiality),
            integrity=min(self.integrity, other.integrity),
        )

    def can_flow_to(self, target: "IFCLabel") -> bool:
        """Bell-LaPadula + Biba style flow check."""
        return target.confidentiality >= self.confidentiality and self.integrity >= target.integrity

    def to_dict(self) -> dict[str, int]:
        """Serialize the label as integer enum values."""
        return {
            "confidentiality": int(self.confidentiality),
            "integrity": int(self.integrity),
        }

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> "IFCLabel":
        """Deserialize a label produced by ``to_dict``."""
        return cls(
            confidentiality=Confidentiality(data["confidentiality"]),
            integrity=Integrity(data["integrity"]),
        )


@dataclass(frozen=True)
class IFCViolation:
    """Describes a blocked IFC flow."""

    source_label: IFCLabel
    target_label: IFCLabel
    policy: str
    detail: str = ""

    @property
    def is_confidentiality_violation(self) -> bool:
        return self.source_label.confidentiality > self.target_label.confidentiality

    @property
    def is_integrity_violation(self) -> bool:
        return self.source_label.integrity < self.target_label.integrity

    def to_dict(self) -> dict[str, object]:
        return {
            "source_label": self.source_label.to_dict(),
            "target_label": self.target_label.to_dict(),
            "policy": self.policy,
            "detail": self.detail,
        }


def taint_merge(*labels: IFCLabel) -> IFCLabel:
    """Merge zero or more labels conservatively."""
    if not labels:
        return IFCLabel()

    merged = labels[0]
    for label in labels[1:]:
        merged = merged.taint_merge(label)
    return merged
