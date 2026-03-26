# Constitutional Hash: 608508a9bd224290
"""Optional Workflow Persistence Module (Phase 9).

When unavailable, all exported names are stubbed to ``object``
(mirroring the pattern used by all other ``_ext_*`` lazy-load modules) so
that callers can guard with ``if PERSISTENCE_AVAILABLE`` without hitting
``NameError``.  All names are listed in ``_EXT_ALL`` so the bus ``__init__``
can re-export them unconditionally.
"""

try:
    from .persistence import (
        DurableWorkflowExecutor,
        InMemoryWorkflowRepository,
        ReplayEngine,
        WorkflowCompensation,
        WorkflowEvent,
        WorkflowInstance,
        WorkflowRepository,
        WorkflowStep,
    )

    PERSISTENCE_AVAILABLE = True
except ImportError:
    PERSISTENCE_AVAILABLE = False
    DurableWorkflowExecutor = object  # type: ignore[assignment, misc]
    InMemoryWorkflowRepository = object  # type: ignore[assignment, misc]
    ReplayEngine = object  # type: ignore[assignment, misc]
    WorkflowCompensation = object  # type: ignore[assignment, misc]
    WorkflowEvent = object  # type: ignore[assignment, misc]
    WorkflowInstance = object  # type: ignore[assignment, misc]
    WorkflowRepository = object  # type: ignore[assignment, misc]
    WorkflowStep = object  # type: ignore[assignment, misc]

_EXT_ALL = [
    "PERSISTENCE_AVAILABLE",
    "DurableWorkflowExecutor",
    "InMemoryWorkflowRepository",
    "ReplayEngine",
    "WorkflowCompensation",
    "WorkflowEvent",
    "WorkflowInstance",
    "WorkflowRepository",
    "WorkflowStep",
]
