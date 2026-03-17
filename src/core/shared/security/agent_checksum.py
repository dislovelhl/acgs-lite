# Constitutional Hash: cdd01ef066bc6cf2
"""Agent checksum computation and verification for JWT binding.

Implements IETF draft-goswami-agentic-jwt-00 inspired agent code integrity
claims. The agent checksum hash (ach) binds a JWT token to the specific
code version of the agent that was issued the credential, preventing
modified or tampered agents from reusing tokens.

Checksum components:
- agent_code_hash: SHA-256 of the agent's source code or deployment artifact
- config_hash: SHA-256 of the agent's configuration
- version: semantic version string

The combined checksum is: SHA-256(agent_code_hash || config_hash || version)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class AgentChecksum:
    """Immutable agent checksum record."""

    agent_id: str
    tenant_id: str
    checksum: str  # SHA-256 hex digest
    agent_code_hash: str
    config_hash: str
    version: str
    computed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def matches(self, other_checksum: str) -> bool:
        """Constant-time comparison to prevent timing attacks."""
        return hmac_compare(self.checksum, other_checksum)


@dataclass(frozen=True)
class ChecksumVerification:
    """Result of a checksum verification."""

    valid: bool
    expected: str
    actual: str
    agent_id: str
    tenant_id: str
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    error: str | None = None


def hmac_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing side-channels."""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b, strict=True):
        result |= ord(x) ^ ord(y)
    return result == 0


def compute_agent_checksum(
    agent_code_hash: str,
    config_hash: str,
    version: str,
) -> str:
    """Compute the combined agent checksum from components.

    The checksum is SHA-256(code_hash || config_hash || version),
    providing a single claim value that binds the token to a
    specific agent build.

    Args:
        agent_code_hash: SHA-256 hex digest of the agent's source code.
        config_hash: SHA-256 hex digest of the agent's configuration.
        version: Semantic version string (e.g., "1.2.3").

    Returns:
        SHA-256 hex digest of the combined components.
    """
    combined = f"{agent_code_hash}:{config_hash}:{version}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def hash_file(path: Path) -> str:
    """Compute SHA-256 of a file, reading in 8KB chunks.

    Args:
        path: Path to the file to hash.

    Returns:
        SHA-256 hex digest.

    Raises:
        FileNotFoundError: If the file does not exist.
        PermissionError: If the file cannot be read.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_directory(directory: Path, extensions: tuple[str, ...] = (".py",)) -> str:
    """Compute a deterministic SHA-256 of all matching files in a directory.

    Files are sorted by path to ensure deterministic output regardless
    of filesystem ordering.

    Args:
        directory: Root directory to scan.
        extensions: File extensions to include.

    Returns:
        SHA-256 hex digest of the combined file contents.
    """
    h = hashlib.sha256()
    files = sorted(p for p in directory.rglob("*") if p.is_file() and p.suffix in extensions)
    for file_path in files:
        # Include relative path in hash to detect file renames
        rel_path = file_path.relative_to(directory)
        h.update(str(rel_path).encode("utf-8"))
        h.update(b"\x00")
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        h.update(b"\x01")  # File separator
    return h.hexdigest()


def hash_config(config: dict) -> str:
    """Compute SHA-256 of a configuration dict.

    The dict is serialized with sorted keys to ensure determinism.

    Args:
        config: Configuration dictionary.

    Returns:
        SHA-256 hex digest.
    """
    import json

    serialized = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_agent_checksum(
    agent_id: str,
    tenant_id: str,
    agent_code_hash: str,
    config_hash: str,
    version: str,
) -> AgentChecksum:
    """Build a complete AgentChecksum record.

    Args:
        agent_id: Agent identifier.
        tenant_id: Tenant identifier.
        agent_code_hash: SHA-256 of the agent's source.
        config_hash: SHA-256 of the agent's configuration.
        version: Semantic version string.

    Returns:
        Frozen AgentChecksum dataclass.
    """
    checksum = compute_agent_checksum(agent_code_hash, config_hash, version)
    return AgentChecksum(
        agent_id=agent_id,
        tenant_id=tenant_id,
        checksum=checksum,
        agent_code_hash=agent_code_hash,
        config_hash=config_hash,
        version=version,
    )


def verify_agent_checksum(
    token_checksum: str,
    expected_checksum: str,
    agent_id: str,
    tenant_id: str,
) -> ChecksumVerification:
    """Verify an agent checksum from a JWT against the expected value.

    Uses constant-time comparison to prevent timing attacks.

    Args:
        token_checksum: The `ach` claim from the JWT.
        expected_checksum: The expected checksum for this agent version.
        agent_id: Agent identifier (for logging/auditing).
        tenant_id: Tenant identifier (for logging/auditing).

    Returns:
        ChecksumVerification with the result.
    """
    valid = hmac_compare(token_checksum, expected_checksum)

    if not valid:
        logger.warning(
            "Agent checksum mismatch",
            agent_id=agent_id,
            tenant_id=tenant_id,
            expected=expected_checksum[:16] + "...",
            actual=token_checksum[:16] + "...",
        )

    return ChecksumVerification(
        valid=valid,
        expected=expected_checksum,
        actual=token_checksum,
        agent_id=agent_id,
        tenant_id=tenant_id,
        error=None if valid else "Agent code has been modified since token issuance",
    )


__all__ = [
    "AgentChecksum",
    "ChecksumVerification",
    "build_agent_checksum",
    "compute_agent_checksum",
    "hash_config",
    "hash_directory",
    "hash_file",
    "hmac_compare",
    "verify_agent_checksum",
]
