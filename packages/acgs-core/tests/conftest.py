"""conftest.py for acgs-core tests.

Inserts packages/acgs-core/src at the front of sys.path so that
``acgs.audit_memory``, ``acgs.policy``, etc. are resolved from the
acgs-core package rather than the backward-compat shim in acgs-lite/src/acgs/.

Both packages expose a ``src/acgs/`` directory.  When both are installed as
editable packages Python resolves the one that appears first in sys.path.
This conftest ensures acgs-core wins for its own tests without requiring
any changes to the installed packages.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Walk up from tests/ → acgs-core/ → src/acgs/
_CORE_SRC = Path(__file__).parent.parent / "src"
_CORE_SRC_STR = str(_CORE_SRC.resolve())

if _CORE_SRC_STR not in sys.path:
    sys.path.insert(0, _CORE_SRC_STR)
