# Constitutional Hash: cdd01ef066bc6cf2
"""Optional Decision Store for FR-12 Decision Explanation API."""

try:
    from .decision_store import (
        DecisionStore,
        get_decision_store,
        reset_decision_store,
    )

    DECISION_STORE_AVAILABLE = True
except ImportError:
    DECISION_STORE_AVAILABLE = False
    DecisionStore = object  # type: ignore[assignment, misc]
    get_decision_store = object  # type: ignore[assignment, misc]
    reset_decision_store = object  # type: ignore[assignment, misc]

_EXT_ALL = [
    "DECISION_STORE_AVAILABLE",
    "DecisionStore",
    "get_decision_store",
    "reset_decision_store",
]
