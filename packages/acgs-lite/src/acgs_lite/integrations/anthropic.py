"""ACGS-Lite Anthropic Integration.

Wraps Anthropic's Messages API with constitutional governance.

Usage::

    from acgs_lite.integrations.anthropic import GovernedAnthropic

    client = GovernedAnthropic(api_key="sk-ant-...")
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": "Hello!"}],
    )

Constitutional Hash: 608508a9bd224290\n\nPublic integration clients use `audit_mode="full"` so exported stats and audit APIs reflect the durable `AuditLog`.\n"""

from __future__ import annotations

import copy
import json
import logging
import re
from typing import Any

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution
from acgs_lite.engine import GovernanceEngine

logger = logging.getLogger(__name__)

try:
    from anthropic import Anthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    Anthropic = object  # type: ignore[assignment,misc]


# Tool definitions for ACGS governance tools (Anthropic tool_use format).
# These mirror what the MCP server exposes, allowing Claude to call
# governance tools on itself via tool_use.
_GOVERNANCE_TOOLS: list[dict[str, Any]] = [
    {
        "name": "validate_action",
        "description": (
            "Validate text against constitutional governance rules. "
            "Returns detailed validation result with any violations found."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text or action to validate.",
                },
                "agent_id": {
                    "type": "string",
                    "description": ("Identifier for the agent performing the action."),
                    "default": "self",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "check_compliance",
        "description": (
            "Quick boolean compliance check. Returns true if the text "
            "passes all constitutional rules, false otherwise."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to check for compliance.",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "get_constitution",
        "description": (
            "Get the active constitutional rules. Returns all enabled "
            "rules with their IDs, text, severity, and categories."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_audit_log",
        "description": (
            "Get recent governance decisions from the audit log. "
            "Returns the most recent validation entries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": ("Maximum number of entries to return."),
                    "default": 20,
                },
                "agent_id": {
                    "type": "string",
                    "description": ("Filter entries by agent ID. Omit to return all agents."),
                },
            },
        },
    },
    {
        "name": "governance_stats",
        "description": (
            "Get validation statistics including total checks, "
            "violation counts, and compliance rate."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]

_GOVERNANCE_TOOL_NAMES: frozenset[str] = frozenset(t["name"] for t in _GOVERNANCE_TOOLS)
_AGENT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{1,128}$")


class GovernedMessages:
    """Governed wrapper around Anthropic's messages API."""

    def __init__(
        self,
        client: Any,
        engine: GovernanceEngine,
        agent_id: str,
    ) -> None:
        self._client = client
        self._engine = engine
        self._agent_id = agent_id

    def create(self, **kwargs: Any) -> Any:
        """Create a message with governance."""
        messages = kwargs.get("messages", [])

        # Validate last user message
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    self._engine.validate(content, agent_id=self._agent_id)
                elif isinstance(content, list):
                    # Anthropic supports content blocks
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            self._engine.validate(
                                block["text"],
                                agent_id=self._agent_id,
                            )
                break

        # Also validate system prompt if present
        system = kwargs.get("system", "")
        if isinstance(system, str) and system:
            old_strict = self._engine.strict
            self._engine.strict = False
            self._engine.validate(system, agent_id=f"{self._agent_id}:system")
            self._engine.strict = old_strict

        # Call Anthropic
        response = self._client.messages.create(**kwargs)

        # Validate output
        if hasattr(response, "content") and response.content:
            for block in response.content:
                if hasattr(block, "text") and block.text:
                    self._validate_output_text(block.text)
                elif (
                    hasattr(block, "type") and block.type == "tool_use" and hasattr(block, "input")
                ):
                    self._validate_tool_use(block)

        return response

    def _validate_output_text(self, text: str) -> None:
        """Validate a text output block against the constitution."""
        old_strict = self._engine.strict
        self._engine.strict = False
        result = self._engine.validate(text, agent_id=f"{self._agent_id}:output")
        self._engine.strict = old_strict

        if not result.valid:
            logger.warning(
                "Anthropic response violations: %s",
                [v.rule_id for v in result.violations],
            )

    def _validate_tool_use(self, block: Any) -> None:
        """Validate a tool_use output block.

        Tool use inputs can contain malicious content (SQL injection,
        secrets exfiltration, prompt injection, etc.) that needs
        governance checking. The block.input dict is serialized to
        JSON for validation.
        """
        tool_input = getattr(block, "input", None)
        if tool_input is None:
            return

        serialized = json.dumps(tool_input, sort_keys=True)
        tool_name = getattr(block, "name", "unknown_tool")

        old_strict = self._engine.strict
        self._engine.strict = False
        result = self._engine.validate(
            serialized,
            agent_id=f"{self._agent_id}:tool_use:{tool_name}",
        )
        self._engine.strict = old_strict

        if not result.valid:
            logger.warning(
                "Tool use '%s' violations: %s",
                tool_name,
                [v.rule_id for v in result.violations],
            )


class GovernedAnthropic:
    """Drop-in replacement for Anthropic() with constitutional governance.

    Usage::

        from acgs_lite.integrations.anthropic import GovernedAnthropic

        client = GovernedAnthropic()
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Hello!"}],
        )

    Governance tools (for tool_use self-governance)::

        client = GovernedAnthropic()
        tools = client.governance_tools()
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            tools=tools,
            messages=[{"role": "user", "content": "Check yourself"}],
        )

        # Process governance tool calls from the response
        for block in response.content:
            if block.type == "tool_use" and block.name in tools_by_name:
                result = client.handle_governance_tool(
                    block.name, block.input
                )
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        constitution: Constitution | None = None,
        agent_id: str = "anthropic-agent",
        strict: bool = True,
        **anthropic_kwargs: Any,
    ) -> None:
        if not ANTHROPIC_AVAILABLE:
            raise ImportError(
                "The 'anthropic' package is required. Install with: pip install acgs[anthropic]"
            )

        self._client = Anthropic(api_key=api_key, **anthropic_kwargs)
        self.constitution = constitution or Constitution.default()
        self.audit_log = AuditLog()
        self.engine = GovernanceEngine(
            self.constitution,
            audit_log=self.audit_log,
            strict=strict,
            audit_mode="full",
        )
        self.agent_id = agent_id
        self.messages = GovernedMessages(self._client, self.engine, agent_id)

    @classmethod
    def governance_tools(cls) -> list[dict[str, Any]]:
        """Return Anthropic-format tool definitions for governance tools.

        These let Claude call governance tools on itself via tool_use,
        matching what the ACGS MCP server exposes. Include these in
        the ``tools`` parameter of ``messages.create()`` to enable
        self-governance.

        Returns:
            List of tool definitions in Anthropic tool_use format.
        """
        # Return a deep copy so callers cannot mutate the canonical defs
        return copy.deepcopy(_GOVERNANCE_TOOLS)

    def handle_governance_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Process a governance tool_use call and return the result.

        This handles calls to the 5 ACGS governance tools that Claude
        may invoke via tool_use. The caller feeds the result back as a
        ``tool_result`` message.

        Args:
            tool_name: Name of the governance tool being called.
            tool_input: The input dict from the tool_use block.

        Returns:
            Result dict suitable for serialization into a tool_result.

        Raises:
            ValueError: If tool_name is not a known governance tool.
        """
        if tool_name not in _GOVERNANCE_TOOL_NAMES:
            raise ValueError(
                f"Unknown governance tool: {tool_name!r}. "
                f"Known tools: {sorted(_GOVERNANCE_TOOL_NAMES)}"
            )

        if tool_name == "validate_action":
            return self._handle_validate_action(tool_input)
        if tool_name == "check_compliance":
            return self._handle_check_compliance(tool_input)
        if tool_name == "get_constitution":
            return self._handle_get_constitution()
        if tool_name == "get_audit_log":
            return self._handle_get_audit_log(tool_input)
        if tool_name == "governance_stats":
            return self._handle_governance_stats()

        # Unreachable due to the membership check above, but satisfies
        # exhaustiveness for static analysis.
        raise ValueError(f"Unhandled governance tool: {tool_name!r}")

    def _handle_validate_action(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Handle the validate_action governance tool."""
        text = tool_input.get("text", "")
        if not text or not text.strip():
            return {"error": "text parameter is required and must not be empty"}

        agent_id = tool_input.get("agent_id", "self")
        if not isinstance(agent_id, str) or not _AGENT_ID_PATTERN.match(agent_id):
            return {"error": f"Invalid agent_id format: {agent_id!r}"}

        old_strict = self.engine.strict
        self.engine.strict = False
        result = self.engine.validate(text, agent_id=f"{self.agent_id}:{agent_id}")
        self.engine.strict = old_strict

        return {
            "valid": result.valid,
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "rule_text": v.rule_text,
                    "severity": str(v.severity),
                    "matched_content": v.matched_content,
                    "category": v.category,
                }
                for v in result.violations
            ],
            "rules_checked": result.rules_checked,
            "constitutional_hash": result.constitutional_hash,
        }

    def _handle_check_compliance(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Handle the check_compliance governance tool."""
        text = tool_input.get("text", "")
        if not text or not text.strip():
            return {"error": "text parameter is required and must not be empty"}

        old_strict = self.engine.strict
        self.engine.strict = False
        result = self.engine.validate(
            text,
            agent_id=f"{self.agent_id}:compliance_check",
        )
        self.engine.strict = old_strict

        return {
            "compliant": result.valid,
            "violation_count": len(result.violations),
        }

    def _handle_get_constitution(self) -> dict[str, Any]:
        """Handle the get_constitution governance tool."""
        rules = [
            {
                "id": rule.id,
                "text": rule.text,
                "severity": str(rule.severity),
                "category": rule.category,
                "keywords": rule.keywords,
                "enabled": rule.enabled,
            }
            for rule in self.constitution.rules
            if rule.enabled
        ]
        return {
            "rules": rules,
            "rule_count": len(rules),
            "constitutional_hash": self.constitution.hash,
        }

    def _handle_get_audit_log(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Handle the get_audit_log governance tool."""
        raw_limit = tool_input.get("limit", 20)
        limit = max(1, min(int(raw_limit), 1000))
        agent_id = tool_input.get("agent_id")
        if agent_id is not None and (
            not isinstance(agent_id, str) or not _AGENT_ID_PATTERN.match(agent_id)
        ):
            return {"error": f"Invalid agent_id format: {agent_id!r}"}

        entries = self.audit_log.query(
            agent_id=agent_id,
            limit=limit,
        )
        return {
            "entries": [entry.to_dict() for entry in entries],
            "count": len(entries),
            "chain_valid": self.audit_log.verify_chain(),
        }

    def _handle_governance_stats(self) -> dict[str, Any]:
        """Handle the governance_stats governance tool."""
        return {
            **self.engine.stats,
            "agent_id": self.agent_id,
            "audit_chain_valid": self.audit_log.verify_chain(),
            "compliance_rate": self.audit_log.compliance_rate,
        }

    @property
    def stats(self) -> dict[str, Any]:
        """Return governance statistics for this client."""
        return {
            **self.engine.stats,
            "agent_id": self.agent_id,
            "audit_chain_valid": self.audit_log.verify_chain(),
        }
