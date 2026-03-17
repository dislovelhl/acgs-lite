"""Option C compatibility shim for ``src.core.shared``.

This package root exposes the five approved shim domains plus the new
``core`` bounded-context facade (Design F, Phase 1):

- ``core``               — **recommended** entry point for Top-5 modules
- ``types``              — type aliases (re-exported via ``core``)
- ``constants``          — system constants (re-exported via ``core``)
- ``structured_logging`` — canonical ``get_logger`` (re-exported via ``core``)
- ``errors``             — exception hierarchy (re-exported via ``core``)
- ``constitutional_hash``— algorithm-agile hash management

All other historical root-level exports are deprecated and intentionally removed.
Consumers should prefer ``from src.core.shared.core import ...`` for new code.
"""

from . import constants, constitutional_hash, core, errors, structured_logging, types

__version__ = "3.1.0"

__all__ = [
    "__version__",
    "constants",
    "constitutional_hash",
    "core",
    "errors",
    "structured_logging",
    "types",
]
