"""bounded-context facade for src.core.shared (Design F, Phase 1).

Re-exports the Top-5 modules as a single import surface.
"""

from . import constants, constitutional_hash, errors, structured_logging, types

__all__ = ["constants", "constitutional_hash", "errors", "structured_logging", "types"]
