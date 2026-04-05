"""
Model-First Tool Documentation System for ACGS-2.

Implements Anthropic's best practice of designing tool interfaces from
the model's perspective. Provides structured documentation that helps
AI agents understand when and how to use tools effectively.

Constitutional Hash: 608508a9bd224290
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

try:
    from enhanced_agent_bus._compat.types import (
        JSONDict,
        JSONList,
    )
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    JSONList = list  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
# Constitutional compliance
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

__all__ = [
    "AGENT_TOOLS",
    "CONSTITUTIONAL_HASH",
    "CONSTITUTIONAL_TOOLS",
    "GOVERNANCE_TOOLS",
    "ToolCategory",
    "ToolDefinition",
    "ToolExample",
    "ToolParameter",
    "ToolRegistry",
    "create_tool_registry",
    "tool",
]


class ToolCategory(Enum):
    """Categories for organizing tools."""

    CONSTITUTIONAL = "constitutional"
    GOVERNANCE = "governance"
    AGENT = "agent"
    MEMORY = "memory"
    RESEARCH = "research"
    WORKFLOW = "workflow"
    UTILITY = "utility"
    AUTOMATION = "automation"


@dataclass
class ToolParameter:
    """
    Tool parameter definition with rich documentation.

    Follows model-first design: describe parameters the way an AI would understand them.
    """

    name: str
    type: str
    description: str
    required: bool = True
    default: object | None = None
    enum_values: list[str] | None = None
    examples: JSONList = field(default_factory=list)
    constraints: str | None = None

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for schema generation."""
        result = {
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "required": self.required,
        }
        if self.default is not None:
            result["default"] = self.default
        if self.enum_values:
            result["enum"] = self.enum_values
        if self.examples:
            result["examples"] = self.examples
        if self.constraints:
            result["constraints"] = self.constraints
        return result

    def to_json_schema(self) -> JSONDict:
        """Convert to JSON Schema format."""
        schema: JSONDict = {
            "description": self.description,
        }

        # Map Python types to JSON Schema types
        type_mapping = {
            "str": "string",
            "string": "string",
            "int": "integer",
            "integer": "integer",
            "float": "number",
            "number": "number",
            "bool": "boolean",
            "boolean": "boolean",
            "list": "array",
            "array": "array",
            "dict": "object",
            "object": "object",
            "any": {},
        }

        schema["type"] = type_mapping.get(self.type.lower(), "string")

        if self.enum_values:
            schema["enum"] = self.enum_values
        if self.default is not None:
            schema["default"] = self.default
        if self.examples:
            schema["examples"] = self.examples

        return schema


@dataclass
class ToolExample:
    """
    Example usage of a tool.

    Shows input/output pairs to help models understand expected behavior.
    """

    description: str
    input: JSONDict
    output: object
    notes: str | None = None

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        result = {
            "description": self.description,
            "input": self.input,
            "output": self.output,
        }
        if self.notes:
            result["notes"] = self.notes
        return result


@dataclass
class ToolDefinition:
    """
    Complete tool definition with model-first documentation.

    Structured to help AI agents:
    1. Understand WHEN to use the tool
    2. Know WHAT to expect as output
    3. Handle EDGE CASES appropriately
    4. Avoid COMMON MISTAKES
    """

    name: str
    description: str
    category: ToolCategory

    # When to use/not use
    use_when: list[str] = field(default_factory=list)
    do_not_use_for: list[str] = field(default_factory=list)

    # Parameters
    parameters: list[ToolParameter] = field(default_factory=list)

    # Output documentation
    returns: str = ""
    return_type: str = "any"

    # Examples
    examples: list[ToolExample] = field(default_factory=list)

    # Edge cases and errors
    edge_cases: list[str] = field(default_factory=list)
    common_errors: dict[str, str] = field(default_factory=dict)

    # Relationships
    related_tools: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)

    # Metadata
    version: str = "1.0.0"
    constitutional_hash: str = CONSTITUTIONAL_HASH
    handler: Callable | None = None

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "use_when": self.use_when,
            "do_not_use_for": self.do_not_use_for,
            "parameters": [p.to_dict() for p in self.parameters],
            "returns": self.returns,
            "return_type": self.return_type,
            "examples": [e.to_dict() for e in self.examples],
            "edge_cases": self.edge_cases,
            "common_errors": self.common_errors,
            "related_tools": self.related_tools,
            "prerequisites": self.prerequisites,
            "version": self.version,
            "constitutional_hash": self.constitutional_hash,
        }

    def to_prompt_format(self) -> str:
        """
        Format tool definition for inclusion in prompts.

        This is the key model-first format that helps AI agents understand the tool.
        """
        lines = [
            f"### {self.name}",
            "",
            self.description,
            "",
        ]

        # When to use
        if self.use_when:
            lines.append("**USE THIS WHEN:**")
            for item in self.use_when:
                lines.append(f"- {item}")
            lines.append("")

        # When NOT to use
        if self.do_not_use_for:
            lines.append("**DO NOT USE FOR:**")
            for item in self.do_not_use_for:
                lines.append(f"- {item}")
            lines.append("")

        # Parameters
        if self.parameters:
            lines.append("**PARAMETERS:**")
            for param in self.parameters:
                required = "(required)" if param.required else "(optional)"
                lines.append(f"- `{param.name}` ({param.type}) {required}: {param.description}")
                if param.constraints:
                    lines.append(f"  - Constraints: {param.constraints}")
                if param.examples:
                    lines.append(f"  - Examples: {', '.join(str(e) for e in param.examples)}")
            lines.append("")

        # Returns
        if self.returns:
            lines.append("**RETURNS:**")
            lines.append(self.returns)
            lines.append("")

        # Examples
        if self.examples:
            lines.append("**EXAMPLES:**")
            for example in self.examples:
                lines.append(f"- {example.description}")
                lines.append(f"  Input: `{json.dumps(example.input)}`")
                lines.append(f"  Output: `{json.dumps(example.output)}`")
                if example.notes:
                    lines.append(f"  Note: {example.notes}")
            lines.append("")

        # Edge cases
        if self.edge_cases:
            lines.append("**EDGE CASES:**")
            for case in self.edge_cases:
                lines.append(f"- {case}")
            lines.append("")

        # Common errors
        if self.common_errors:
            lines.append("**COMMON ERRORS:**")
            for error, solution in self.common_errors.items():
                lines.append(f"- `{error}`: {solution}")
            lines.append("")

        # Related tools
        if self.related_tools:
            lines.append(f"**RELATED:** {', '.join(self.related_tools)}")

        return "\n".join(lines)

    def to_openai_schema(self) -> JSONDict:
        """Generate OpenAI-compatible function schema."""
        properties = {}
        required = []

        for param in self.parameters:
            properties[param.name] = param.to_json_schema()
            if param.required:
                required.append(param.name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    def to_anthropic_schema(self) -> JSONDict:
        """Generate Anthropic-compatible tool schema."""
        input_schema = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        for param in self.parameters:
            input_schema["properties"][param.name] = param.to_json_schema()  # type: ignore[index]
            if param.required:
                input_schema["required"].append(param.name)  # type: ignore[attr-defined, union-attr]

        return {
            "name": self.name,
            "description": self._build_rich_description(),
            "input_schema": input_schema,
        }

    def _build_rich_description(self) -> str:
        """Build rich description for Anthropic tool format."""
        parts = [self.description]

        if self.use_when:
            parts.append("\n\nUSE THIS WHEN:")
            parts.extend(f"\n- {item}" for item in self.use_when)

        if self.do_not_use_for:
            parts.append("\n\nDO NOT USE FOR:")
            parts.extend(f"\n- {item}" for item in self.do_not_use_for)

        if self.returns:
            parts.append(f"\n\nRETURNS:\n{self.returns}")

        if self.edge_cases:
            parts.append("\n\nEDGE CASES:")
            parts.extend(f"\n- {case}" for case in self.edge_cases)

        return "".join(parts)


class ToolRegistry:
    """
    Registry for tool definitions.

    Provides centralized management and retrieval of tool documentation.
    """

    def __init__(self, constitutional_hash: str = CONSTITUTIONAL_HASH):
        self._tools: dict[str, ToolDefinition] = {}
        self._constitutional_hash = constitutional_hash
        self._categories: dict[ToolCategory, list[str]] = {cat: [] for cat in ToolCategory}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition."""
        tool.constitutional_hash = self._constitutional_hash
        self._tools[tool.name] = tool
        self._categories[tool.category].append(tool.name)
        logger.debug(f"Registered tool: {tool.name} in category {tool.category.value}")

    def get(self, name: str) -> ToolDefinition | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_by_category(self, category: ToolCategory) -> list[ToolDefinition]:
        """Get all tools in a category."""
        return [self._tools[name] for name in self._categories[category] if name in self._tools]

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_all_by_category(self) -> dict[str, list[ToolDefinition]]:
        """Get all tool definitions grouped by category."""
        return {
            cat.value: [self._tools[name] for name in names]
            for cat, names in self._categories.items()
        }

    def get_all(self) -> list[ToolDefinition]:
        """Get all tool definitions."""
        return list(self._tools.values())

    def to_prompt_format(self, category: ToolCategory | None = None) -> str:
        """Generate prompt-format documentation for tools."""
        if category:
            tools = self.get_by_category(category)
        else:
            tools = self.get_all()

        return "\n\n---\n\n".join(tool.to_prompt_format() for tool in tools)

    def to_openai_schemas(self) -> list[JSONDict]:
        """Generate OpenAI-compatible schemas for all tools."""
        return [tool.to_openai_schema() for tool in self._tools.values()]

    def to_anthropic_schemas(self) -> list[JSONDict]:
        """Generate Anthropic-compatible schemas for all tools."""
        return [tool.to_anthropic_schema() for tool in self._tools.values()]

    def find_related(self, tool_name: str) -> list[ToolDefinition]:
        """Find tools related to the given tool."""
        tool = self.get(tool_name)
        if not tool:
            return []

        related = []
        for related_name in tool.related_tools:
            related_tool = self.get(related_name)
            if related_tool:
                related.append(related_tool)

        return related

    def get_stats(self) -> JSONDict:
        """Get registry statistics."""
        return {
            "total_tools": len(self._tools),
            "by_category": {cat.value: len(names) for cat, names in self._categories.items()},
            "constitutional_hash": self._constitutional_hash,
        }


def tool(
    name: str,
    description: str,
    category: ToolCategory = ToolCategory.UTILITY,
    use_when: list[str] | None = None,
    do_not_use_for: list[str] | None = None,
    returns: str = "",
    **kwargs,
) -> Callable:
    """
    Decorator to create a documented tool from a function.

    Usage:
        @tool(
            name="my_tool",
            description="Does something useful",
            category=ToolCategory.UTILITY,
            use_when=["You need to do X"],
        )
        async def my_tool(arg1: str, arg2: int = 10):
            return result
    """

    def decorator(func: Callable) -> Callable:
        # Extract parameters from function signature
        import inspect

        sig = inspect.signature(func)
        parameters = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            param_type = "any"
            if param.annotation != inspect.Parameter.empty:
                param_type = getattr(param.annotation, "__name__", str(param.annotation))

            required = param.default == inspect.Parameter.empty
            default = None if required else param.default

            parameters.append(
                ToolParameter(
                    name=param_name,
                    type=param_type,
                    description=f"Parameter: {param_name}",
                    required=required,
                    default=default,
                )
            )

        tool_def = ToolDefinition(
            name=name,
            description=description,
            category=category,
            use_when=use_when or [],
            do_not_use_for=do_not_use_for or [],
            parameters=parameters,
            returns=returns,
            handler=func,
            **kwargs,
        )

        func._tool_definition = tool_def  # type: ignore[attr-defined]
        return func

    return decorator


def create_tool_registry(
    constitutional_hash: str = CONSTITUTIONAL_HASH,
    include_defaults: bool = True,
) -> ToolRegistry:
    """
    Factory function to create a tool registry.

    Args:
        constitutional_hash: Constitutional hash for compliance
        include_defaults: Whether to include default ACGS-2 tools

    Returns:
        Configured ToolRegistry
    """
    registry = ToolRegistry(constitutional_hash)

    if include_defaults:
        for tool_def in CONSTITUTIONAL_TOOLS + GOVERNANCE_TOOLS + AGENT_TOOLS + WUYING_TOOLS:
            registry.register(tool_def)

    return registry


# =============================================================================
# Pre-defined ACGS-2 Tool Definitions
# =============================================================================

CONSTITUTIONAL_TOOLS = [
    ToolDefinition(
        name="validate_constitutional_compliance",
        description="Validates an action against the constitutional governance framework.",
        category=ToolCategory.CONSTITUTIONAL,
        use_when=[
            "You need to check if an action complies with constitutional principles",
            "Before executing any governance-impacting operation",
            "When MACI role requires cross-validation",
        ],
        do_not_use_for=[
            "Read-only queries that don't modify governance state",
            "Actions already validated in the current workflow",
        ],
        parameters=[
            ToolParameter(
                name="action",
                type="string",
                description="The type of action to validate (e.g., 'modify_policy', 'approve_request')",
                required=True,
                examples=["modify_policy", "approve_request", "escalate_issue"],
            ),
            ToolParameter(
                name="context",
                type="object",
                description="Additional context for validation including resource IDs and metadata",
                required=False,
                default={},
            ),
            ToolParameter(
                name="strict_mode",
                type="boolean",
                description="Whether to use strict validation (rejects on any uncertainty)",
                required=False,
                default=True,
            ),
        ],
        returns="""- is_compliant: boolean indicating compliance status
- violations: list of violated principles (if any)
- confidence: 0.0-1.0 confidence score
- hash_verified: whether constitutional hash matches
- recommendations: suggested remediation actions""",
        return_type="object",
        examples=[
            ToolExample(
                description="Validate a policy modification",
                input={"action": "modify_policy", "context": {"policy_id": "POL-123"}},
                output={
                    "is_compliant": True,
                    "violations": [],
                    "confidence": 0.98,
                    "hash_verified": True,
                },
            ),
            ToolExample(
                description="Detect a violation",
                input={"action": "delete_audit_log", "context": {}},
                output={
                    "is_compliant": False,
                    "violations": ["IMMUTABILITY_PRINCIPLE"],
                    "confidence": 0.99,
                    "hash_verified": True,
                },
                notes="Audit logs cannot be deleted per constitutional principles",
            ),
        ],
        edge_cases=[
            "Empty action: Returns is_compliant=false with 'empty_action' violation",
            "Invalid policy_id: Returns is_compliant=false with 'policy_not_found' violation",
            "Network timeout: Raises ConstitutionalValidationTimeout (retry recommended)",
        ],
        common_errors={
            "InvalidActionError": "Ensure action is a valid string from the allowed actions list",
            "HashMismatchError": "Constitutional hash mismatch - system integrity may be compromised",
        },
        related_tools=["get_constitutional_principles", "audit_action"],
    ),
    ToolDefinition(
        name="get_constitutional_principles",
        description="Retrieves the current set of constitutional principles governing the system.",
        category=ToolCategory.CONSTITUTIONAL,
        use_when=[
            "You need to understand what principles apply to a decision",
            "Explaining why an action was approved or rejected",
            "Building prompts that reference constitutional constraints",
        ],
        do_not_use_for=[
            "Modifying constitutional principles (use propose_amendment)",
            "Checking specific action compliance (use validate_constitutional_compliance)",
        ],
        parameters=[
            ToolParameter(
                name="category",
                type="string",
                description="Filter principles by category",
                required=False,
                enum_values=["safety", "ethics", "governance", "privacy", "all"],
                default="all",
            ),
        ],
        returns="List of constitutional principles with their IDs, descriptions, and severity levels",
        return_type="array",
        examples=[
            ToolExample(
                description="Get all principles",
                input={"category": "all"},
                output=[
                    {
                        "id": "PRIN-001",
                        "name": "Transparency",
                        "category": "ethics",
                        "severity": "high",
                    },
                    {
                        "id": "PRIN-002",
                        "name": "Immutability",
                        "category": "governance",
                        "severity": "critical",
                    },
                ],
            ),
        ],
        edge_cases=[
            "Unknown category: Returns empty list with warning",
        ],
        related_tools=["validate_constitutional_compliance", "propose_amendment"],
    ),
]

GOVERNANCE_TOOLS = [
    ToolDefinition(
        name="create_governance_proposal",
        description="Creates a new governance proposal for system changes that require approval.",
        category=ToolCategory.GOVERNANCE,
        use_when=[
            "Proposing changes to system policies or configurations",
            "Requesting approval for high-impact actions",
            "Initiating multi-stakeholder decision processes",
        ],
        do_not_use_for=[
            "Minor configuration changes that don't require approval",
            "Emergency actions (use emergency_action instead)",
            "Read-only queries or status checks",
        ],
        parameters=[
            ToolParameter(
                name="title",
                type="string",
                description="Short, descriptive title for the proposal",
                required=True,
                constraints="Max 100 characters",
                examples=["Update Rate Limiting Policy", "Add New Agent Role"],
            ),
            ToolParameter(
                name="description",
                type="string",
                description="Detailed description of the proposed change and its rationale",
                required=True,
                constraints="Min 50 characters for adequate context",
            ),
            ToolParameter(
                name="impact_level",
                type="string",
                description="Expected impact level of the change",
                required=True,
                enum_values=["low", "medium", "high", "critical"],
            ),
            ToolParameter(
                name="changes",
                type="object",
                description="Specific changes to be made if approved",
                required=True,
            ),
            ToolParameter(
                name="deadline",
                type="string",
                description="ISO 8601 datetime for voting deadline",
                required=False,
                examples=["2024-12-31T23:59:59Z"],
            ),
        ],
        returns="""- proposal_id: Unique identifier for tracking
- status: Current status (pending, under_review, approved, rejected)
- required_approvals: Number of approvals needed
- current_approvals: Current approval count""",
        return_type="object",
        examples=[
            ToolExample(
                description="Create a policy update proposal",
                input={
                    "title": "Increase API Rate Limit",
                    "description": "Propose increasing the API rate limit from 100 to 200 requests per minute to accommodate growth.",
                    "impact_level": "medium",
                    "changes": {"rate_limit": {"old": 100, "new": 200}},
                },
                output={
                    "proposal_id": "PROP-2024-001",
                    "status": "pending",
                    "required_approvals": 3,
                    "current_approvals": 0,
                },
            ),
        ],
        edge_cases=[
            "Duplicate proposal: Returns existing proposal_id with warning",
            "Invalid impact_level: Validation error with allowed values",
        ],
        related_tools=["vote_on_proposal", "get_proposal_status", "cancel_proposal"],
    ),
    ToolDefinition(
        name="audit_action",
        description="Records an action in the immutable audit log for compliance and traceability.",
        category=ToolCategory.GOVERNANCE,
        use_when=[
            "After completing any governance action",
            "Recording decisions and their rationale",
            "Creating compliance trails for regulatory purposes",
        ],
        do_not_use_for=[
            "Temporary or debug logging (use standard logging)",
            "High-frequency operational events (use metrics instead)",
        ],
        parameters=[
            ToolParameter(
                name="action_type",
                type="string",
                description="Type of action being audited",
                required=True,
                examples=["policy_change", "access_grant", "approval", "rejection"],
            ),
            ToolParameter(
                name="actor_id",
                type="string",
                description="Identifier of the entity performing the action",
                required=True,
            ),
            ToolParameter(
                name="details",
                type="object",
                description="Action details and context",
                required=True,
            ),
            ToolParameter(
                name="outcome",
                type="string",
                description="Result of the action",
                required=True,
                enum_values=["success", "failure", "partial"],
            ),
        ],
        returns="audit_id: Immutable identifier for the audit record",
        return_type="string",
        examples=[
            ToolExample(
                description="Audit a policy change",
                input={
                    "action_type": "policy_change",
                    "actor_id": "agent-001",
                    "details": {
                        "policy_id": "POL-123",
                        "field": "rate_limit",
                        "old": 100,
                        "new": 200,
                    },
                    "outcome": "success",
                },
                output="AUDIT-2024-001234",
            ),
        ],
        edge_cases=[
            "Audit service unavailable: Queues action for retry, returns pending_audit_id",
        ],
        related_tools=["query_audit_log", "export_audit_report"],
    ),
]

AGENT_TOOLS = [
    ToolDefinition(
        name="spawn_agent",
        description="Spawns a new specialized agent in the swarm with specified capabilities.",
        category=ToolCategory.AGENT,
        use_when=[
            "A task requires specialized capabilities not available in current agents",
            "Workload demands additional parallel processing capacity",
            "Specific domain expertise is needed for a subtask",
        ],
        do_not_use_for=[
            "Tasks that can be handled by existing agents",
            "When at maximum agent capacity (check get_swarm_status first)",
            "Short-lived, simple operations",
        ],
        parameters=[
            ToolParameter(
                name="name",
                type="string",
                description="Human-readable name for the agent",
                required=True,
                constraints="Max 50 characters, alphanumeric and hyphens only",
                examples=["code-analyzer", "research-specialist"],
            ),
            ToolParameter(
                name="capabilities",
                type="array",
                description="List of capabilities the agent should have",
                required=True,
                examples=[["CODE_ANALYSIS", "PATTERN_DETECTION"], ["RESEARCH", "SUMMARIZATION"]],
            ),
            ToolParameter(
                name="priority",
                type="string",
                description="Agent priority for resource allocation",
                required=False,
                enum_values=["low", "normal", "high", "critical"],
                default="normal",
            ),
        ],
        returns="""- agent_id: Unique identifier for the spawned agent
- status: Current agent status (initializing, ready, busy)
- capabilities: Confirmed list of capabilities""",
        return_type="object",
        examples=[
            ToolExample(
                description="Spawn a code analysis agent",
                input={
                    "name": "code-analyzer-1",
                    "capabilities": ["CODE_ANALYSIS", "SECURITY_SCAN"],
                    "priority": "high",
                },
                output={
                    "agent_id": "agent-a1b2c3d4",
                    "status": "ready",
                    "capabilities": ["CODE_ANALYSIS", "SECURITY_SCAN"],
                },
            ),
        ],
        edge_cases=[
            "Max agents reached: Returns error with suggestion to terminate idle agents",
            "Invalid capability: Returns error with list of valid capabilities",
            "Name conflict: Appends unique suffix automatically",
        ],
        common_errors={
            "MaxAgentsExceeded": "Terminate unused agents or wait for capacity",
            "InvalidCapability": "Check VALID_CAPABILITIES for allowed values",
        },
        related_tools=["terminate_agent", "get_swarm_status", "assign_task"],
        prerequisites=["get_swarm_status (recommended to check capacity)"],
    ),
    ToolDefinition(
        name="assign_task",
        description="Assigns a task to an available agent based on capability matching.",
        category=ToolCategory.AGENT,
        use_when=[
            "You have a specific task that needs to be executed by an agent",
            "Delegating work to specialized agents in the swarm",
            "Breaking down complex tasks into agent-executable units",
        ],
        do_not_use_for=[
            "Tasks that you can handle directly",
            "When no suitable agents are available (spawn one first)",
            "Extremely time-sensitive operations (may have queue delay)",
        ],
        parameters=[
            ToolParameter(
                name="description",
                type="string",
                description="Clear description of what the task requires",
                required=True,
                constraints="Be specific about expected outcomes",
            ),
            ToolParameter(
                name="required_capabilities",
                type="array",
                description="Capabilities needed to complete this task",
                required=True,
            ),
            ToolParameter(
                name="priority",
                type="string",
                description="Task priority",
                required=False,
                enum_values=["low", "normal", "high", "critical"],
                default="normal",
            ),
            ToolParameter(
                name="deadline",
                type="string",
                description="Optional ISO 8601 deadline",
                required=False,
            ),
            ToolParameter(
                name="agent_id",
                type="string",
                description="Specific agent to assign to (optional, auto-selects if omitted)",
                required=False,
            ),
        ],
        returns="""- task_id: Unique task identifier for tracking
- assigned_agent: ID of the agent assigned to the task
- estimated_completion: Estimated completion time
- status: Current task status""",
        return_type="object",
        examples=[
            ToolExample(
                description="Assign a code review task",
                input={
                    "description": "Review the authentication module for security vulnerabilities",
                    "required_capabilities": ["CODE_ANALYSIS", "SECURITY_SCAN"],
                    "priority": "high",
                },
                output={
                    "task_id": "task-x1y2z3",
                    "assigned_agent": "agent-a1b2c3d4",
                    "estimated_completion": "2024-01-15T12:00:00Z",
                    "status": "assigned",
                },
            ),
        ],
        edge_cases=[
            "No matching agent: Returns error suggesting spawn_agent",
            "All agents busy: Queues task and returns queue position",
        ],
        related_tools=["spawn_agent", "get_task_status", "cancel_task"],
    ),
]

WUYING_TOOLS = [
    ToolDefinition(
        name="browser_automation",
        description="Opens a headless or headed browser in a Wuying sandbox for web tasks.",
        category=ToolCategory.AUTOMATION,
        use_when=[
            "Interacting with web applications that require JS rendering",
            "Scraping data from dynamic websites",
            "Verifying UI changes in a live environment",
        ],
        parameters=[
            ToolParameter(
                name="url",
                type="string",
                description="Target URL to navigate to",
                required=True,
            ),
            ToolParameter(
                name="action",
                type="string",
                description="Action to perform (click, type, screenshot, evaluate)",
                required=True,
                enum_values=["navigate", "click", "type", "screenshot", "extract_text"],
            ),
            ToolParameter(
                name="selector",
                type="string",
                description="CSS selector for elements (if applicable)",
                required=False,
            ),
            ToolParameter(
                name="value",
                type="string",
                description="Value to type or script to evaluate",
                required=False,
            ),
        ],
        returns="Action result, screenshot (base64) or extracted content",
        return_type="object",
        related_tools=["computer_use", "spawn_agent"],
        edge_cases=[
            "Page load timeout: Returns status=timeout",
            "Selector not found: Returns error with current DOM snippet",
        ],
    ),
    ToolDefinition(
        name="computer_use",
        description="Controls a cloud desktop instance via Wuying for general computing tasks.",
        category=ToolCategory.AUTOMATION,
        use_when=[
            "Executing GUI-based software",
            "Performing complex cross-application workflows",
            "Legacy system interaction via remote desktop",
        ],
        parameters=[
            ToolParameter(
                name="command",
                type="string",
                description="Command to execute or input to send",
                required=True,
            ),
            ToolParameter(
                name="action_type",
                type="string",
                description="Type of interaction",
                required=True,
                enum_values=["shell", "mouse_click", "keyboard_input", "screenshot"],
            ),
            ToolParameter(
                name="coordinates",
                type="array",
                description="X, Y coordinates for mouse actions",
                required=False,
            ),
        ],
        returns="Command output or visual confirmation",
        return_type="object",
        related_tools=["browser_automation", "spawn_agent"],
    ),
]
