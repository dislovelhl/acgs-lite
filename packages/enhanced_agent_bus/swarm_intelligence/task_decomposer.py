"""
Swarm Intelligence - Task Decomposer

DAG-based task decomposition engine with predictive ML capabilities.

Constitutional Hash: 608508a9bd224290
"""

from collections.abc import Callable

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .enums import TaskPriority
from .models import DecompositionPattern, SwarmTask

logger = get_logger(__name__)
# Configuration constants
PATTERN_MATCH_THRESHOLD = 0.3  # Minimum pattern match score (30%) for pattern matching
DEFAULT_MAX_HISTORY_SIZE = 1000


class TaskDecomposer:
    """
    DAG-based task decomposition engine v3.1 with predictive ML capabilities.

    Features:
    - Pattern-based decomposition
    - Historical success tracking
    - Complexity estimation
    - Optimal strategy selection

    Breaks complex tasks into sub-tasks with dependency tracking.
    """

    def __init__(self, max_history_size: int = DEFAULT_MAX_HISTORY_SIZE):
        self._decomposition_rules: dict[str, Callable] = {}
        self._historical_patterns: dict[str, DecompositionPattern] = {}
        self._task_history: list[dict] = []  # Completed task data
        self._max_history_size = max_history_size
        self._register_default_rules()
        self._register_ml_patterns()

    def _register_default_rules(self) -> None:
        """Register default decomposition rules."""
        # Code generation decomposition
        self._decomposition_rules["code_generation"] = self._decompose_code_generation
        # Testing decomposition
        self._decomposition_rules["testing"] = self._decompose_testing
        # Documentation decomposition
        self._decomposition_rules["documentation"] = self._decompose_documentation
        # Refactoring decomposition
        self._decomposition_rules["refactoring"] = self._decompose_refactoring
        # Bug fix decomposition
        self._decomposition_rules["bug_fix"] = self._decompose_bug_fix

    def _register_ml_patterns(self) -> None:
        """Register ML patterns for predictive decomposition."""
        self._historical_patterns = {
            "api_endpoint": DecompositionPattern(
                pattern_name="api_endpoint",
                keywords=["api", "endpoint", "rest", "http", "route"],
                avg_completion_time=1800.0,  # 30 minutes
                avg_subtasks=4,
                success_rate=0.88,
                complexity_score=4.5,
            ),
            "database_migration": DecompositionPattern(
                pattern_name="database_migration",
                keywords=["migration", "database", "schema", "table", "sql"],
                avg_completion_time=3600.0,  # 60 minutes
                avg_subtasks=6,
                success_rate=0.75,
                complexity_score=7.0,
            ),
            "ui_component": DecompositionPattern(
                pattern_name="ui_component",
                keywords=["ui", "component", "frontend", "react", "html", "css"],
                avg_completion_time=2400.0,  # 40 minutes
                avg_subtasks=3,
                success_rate=0.92,
                complexity_score=3.5,
            ),
            "authentication": DecompositionPattern(
                pattern_name="authentication",
                keywords=["auth", "login", "oauth", "jwt", "security", "authentication"],
                avg_completion_time=5400.0,  # 90 minutes
                avg_subtasks=7,
                success_rate=0.82,
                complexity_score=8.0,
            ),
            "performance_optimization": DecompositionPattern(
                pattern_name="performance_optimization",
                keywords=["performance", "optimize", "cache", "speed", "slow"],
                avg_completion_time=4200.0,  # 70 minutes
                avg_subtasks=5,
                success_rate=0.71,
                complexity_score=6.5,
            ),
        }

    def predict_task_characteristics(
        self,
        task: SwarmTask,
    ) -> JSONDict:
        """
        Predict task characteristics using pattern matching.

        Returns complexity, estimated time, and recommended subtask count.
        """
        description_lower = task.description.lower()
        words = set(description_lower.split())

        best_match = None
        best_score = 0.0

        for pattern in self._historical_patterns.values():
            # Calculate pattern match score
            pattern_words = set(k.lower() for k in pattern.keywords)
            matching_words = words & pattern_words
            match_score = len(matching_words) / len(pattern_words) if pattern_words else 0

            if match_score > best_score and match_score >= PATTERN_MATCH_THRESHOLD:
                best_score = match_score
                best_match = pattern

        if best_match:
            return {
                "predicted_complexity": best_match.complexity_score,
                "estimated_completion_time": best_match.avg_completion_time,
                "recommended_subtasks": best_match.avg_subtasks,
                "success_rate": best_match.success_rate,
                "matched_pattern": best_match.pattern_name,
                "confidence": best_score,
            }

        # Default prediction for unknown patterns
        return {
            "predicted_complexity": 5.0,
            "estimated_completion_time": 3600.0,
            "recommended_subtasks": 4,
            "success_rate": 0.80,
            "matched_pattern": None,
            "confidence": 0.0,
        }

    def select_optimal_strategy(
        self,
        task: SwarmTask,
        predictions: JSONDict,
    ) -> str:
        """
        Select the optimal decomposition strategy based on predictions.

        Returns the strategy name to use.
        """
        complexity = predictions["predicted_complexity"]
        success_rate = predictions["success_rate"]

        # High complexity tasks need more granular decomposition
        if complexity >= 7.0:
            return "granular"

        # Low success rate patterns need careful planning
        if success_rate < 0.75:
            return "conservative"

        # Fast tasks can be more streamlined
        if predictions["estimated_completion_time"] < 1800:
            return "streamlined"

        return "standard"

    def _decompose_code_generation(self, task: SwarmTask) -> list[SwarmTask]:
        """Decompose a code generation task."""
        base_id = task.id
        subtasks = [
            SwarmTask(
                id=f"{base_id}_design",
                description=f"Design architecture for: {task.description}",
                required_capabilities=["architecture", "design"],
                priority=task.priority,
                dependencies=[],
            ),
            SwarmTask(
                id=f"{base_id}_implement",
                description=f"Implement code for: {task.description}",
                required_capabilities=["coding", "implementation"],
                priority=task.priority,
                dependencies=[f"{base_id}_design"],
            ),
            SwarmTask(
                id=f"{base_id}_test",
                description=f"Write tests for: {task.description}",
                required_capabilities=["testing", "qa"],
                priority=task.priority,
                dependencies=[f"{base_id}_implement"],
            ),
            SwarmTask(
                id=f"{base_id}_review",
                description=f"Review code for: {task.description}",
                required_capabilities=["code_review"],
                priority=task.priority,
                dependencies=[f"{base_id}_test"],
            ),
        ]
        return subtasks

    def _decompose_testing(self, task: SwarmTask) -> list[SwarmTask]:
        """Decompose a testing task."""
        base_id = task.id
        return [
            SwarmTask(
                id=f"{base_id}_unit",
                description=f"Unit tests for: {task.description}",
                required_capabilities=["unit_testing"],
                priority=task.priority,
            ),
            SwarmTask(
                id=f"{base_id}_integration",
                description=f"Integration tests for: {task.description}",
                required_capabilities=["integration_testing"],
                priority=task.priority,
                dependencies=[f"{base_id}_unit"],
            ),
            SwarmTask(
                id=f"{base_id}_e2e",
                description=f"E2E tests for: {task.description}",
                required_capabilities=["e2e_testing"],
                priority=task.priority,
                dependencies=[f"{base_id}_integration"],
            ),
        ]

    def _decompose_documentation(self, task: SwarmTask) -> list[SwarmTask]:
        """Decompose a documentation task."""
        base_id = task.id
        return [
            SwarmTask(
                id=f"{base_id}_api",
                description=f"API documentation for: {task.description}",
                required_capabilities=["technical_writing"],
                priority=task.priority,
            ),
            SwarmTask(
                id=f"{base_id}_user",
                description=f"User documentation for: {task.description}",
                required_capabilities=["user_documentation"],
                priority=task.priority,
            ),
        ]

    def _decompose_refactoring(self, task: SwarmTask) -> list[SwarmTask]:
        """Decompose a refactoring task."""
        base_id = task.id
        return [
            SwarmTask(
                id=f"{base_id}_analyze",
                description=f"Analyze code for refactoring: {task.description}",
                required_capabilities=["code_analysis", "refactoring"],
                priority=task.priority,
            ),
            SwarmTask(
                id=f"{base_id}_refactor",
                description=f"Execute refactoring: {task.description}",
                required_capabilities=["refactoring", "coding"],
                priority=task.priority,
                dependencies=[f"{base_id}_analyze"],
            ),
            SwarmTask(
                id=f"{base_id}_validate",
                description=f"Validate refactoring: {task.description}",
                required_capabilities=["testing", "validation"],
                priority=task.priority,
                dependencies=[f"{base_id}_refactor"],
            ),
        ]

    def _decompose_bug_fix(self, task: SwarmTask) -> list[SwarmTask]:
        """Decompose a bug fix task."""
        base_id = task.id
        return [
            SwarmTask(
                id=f"{base_id}_reproduce",
                description=f"Reproduce bug: {task.description}",
                required_capabilities=["debugging", "testing"],
                priority=TaskPriority.HIGH if task.priority.value <= 2 else task.priority,
            ),
            SwarmTask(
                id=f"{base_id}_root_cause",
                description=f"Identify root cause: {task.description}",
                required_capabilities=["debugging", "analysis"],
                priority=task.priority,
                dependencies=[f"{base_id}_reproduce"],
            ),
            SwarmTask(
                id=f"{base_id}_fix",
                description=f"Implement fix: {task.description}",
                required_capabilities=["coding", "debugging"],
                priority=task.priority,
                dependencies=[f"{base_id}_root_cause"],
            ),
            SwarmTask(
                id=f"{base_id}_verify",
                description=f"Verify fix and add regression test: {task.description}",
                required_capabilities=["testing", "qa"],
                priority=task.priority,
                dependencies=[f"{base_id}_fix"],
            ),
        ]

    def decompose(
        self,
        task: SwarmTask,
        task_type: str | None = None,
    ) -> list[SwarmTask]:
        """
        Decompose a task into subtasks.

        Args:
            task: The task to decompose
            task_type: Type hint for decomposition rule selection

        Returns:
            List of subtasks with dependencies
        """
        if task_type and task_type in self._decomposition_rules:
            return self._decomposition_rules[task_type](task)  # type: ignore[no-any-return]

        # Auto-detect based on description
        description_lower = task.description.lower()
        for rule_type, rule_func in self._decomposition_rules.items():
            if rule_type in description_lower:
                return rule_func(task)  # type: ignore[no-any-return]

        # No decomposition needed
        return [task]

    def register_rule(self, task_type: str, rule: Callable) -> None:
        """Register a custom decomposition rule."""
        self._decomposition_rules[task_type] = rule

    def _add_task_to_history(self, task_data: dict) -> None:
        """
        Add a completed task to history with automatic pruning.

        FIX-002: Prevents unbounded memory growth by enforcing max_history_size.

        Args:
            task_data: Dictionary containing task completion data.
        """
        self._task_history.append(task_data)
        # Prune history if it exceeds max size
        if len(self._task_history) > self._max_history_size:
            # Remove oldest entries (from the beginning)
            excess = len(self._task_history) - self._max_history_size
            self._task_history = self._task_history[excess:]


__all__ = [
    "TaskDecomposer",
]
