# Constitutional Hash: 608508a9bd224290
"""Optional Explanation Service for FR-12 Decision Explanation API."""

try:
    from .explanation_service import (
        CounterfactualEngine,
        ExplanationService,
        get_explanation_service,
        reset_explanation_service,
    )

    EXPLANATION_SERVICE_AVAILABLE = True
except ImportError:
    EXPLANATION_SERVICE_AVAILABLE = False
    CounterfactualEngine = object  # type: ignore[assignment, misc]
    ExplanationService = object  # type: ignore[assignment, misc]
    get_explanation_service = object  # type: ignore[assignment, misc]
    reset_explanation_service = object  # type: ignore[assignment, misc]

_EXT_ALL = [
    "EXPLANATION_SERVICE_AVAILABLE",
    "ExplanationService",
    "CounterfactualEngine",
    "get_explanation_service",
    "reset_explanation_service",
]
