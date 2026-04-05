"""
ChatOps Executor Agent
Constitutional Hash: 608508a9bd224290

Responsible for executing parsed ChatOps commands from the github_app service.
Adheres strictly to the MACI Executor role, operating on validated inputs.
"""

import os

try:
    from src.core.services.enterprise.compliance import questionnaire_responder
except ImportError:
    questionnaire_responder = None

from enhanced_agent_bus.core_models import AgentMessage, MessageType
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

OPEN_AWARE_SERVER_URL = os.getenv("OPEN_AWARE_MCP_URL", "https://open-aware.qodo.ai/mcp")
REVIEW_DISPATCH_ERRORS = (
    ConnectionError,
    ImportError,
    OSError,
    RuntimeError,
    TimeoutError,
    ValueError,
)


async def handle_chatops_command(msg: AgentMessage) -> AgentMessage | None:
    """
    Executes ChatOps commands parsed from GitHub issue comments.
    """
    if msg.to_agent != "chatops_executor" or msg.message_type != MessageType.COMMAND:
        return None

    command_data = msg.content
    if not isinstance(command_data, dict):
        return None

    command_body = command_data.get("command_body", "")
    command_name = command_body.split(maxsplit=1)[0] if command_body else ""
    author = command_data.get("author", "unknown")
    issue_number = command_data.get("issue_number")

    logger.info(
        "Executing ChatOps command",
        extra={"command": command_name, "author": author, "issue_number": issue_number},
    )

    # Dispatch routing logic for ChatOps
    if command_body.startswith("/acgs-build-fix"):
        logger.info("Dispatching to Build Fix agent swarm")
        return _dispatch_build_fix(issue_number, author, command_body)
    elif command_body.startswith("/acgs-review"):
        logger.info("Dispatching to Review agent swarm with open-aware context")
        return await _dispatch_review(issue_number)
    elif command_body.startswith("/acgs-compliance-ingest"):
        return await _dispatch_compliance_ingest(command_body, author)
    else:
        logger.warning(f"Unrecognized ChatOps command: {command_name}")

    return msg


def _dispatch_build_fix(issue_number: int | None, author: str, command_body: str) -> AgentMessage:
    """Route build-fix requests using the canonical swarm contract."""
    return AgentMessage(
        from_agent="chatops_executor",
        to_agent="build_fix_swarm",
        message_type=MessageType.TASK_REQUEST,
        content={
            "action": "execute_build_fix",
            "issue_number": issue_number,
            "author": author,
            "command_body": command_body,
            "project_path": os.getcwd(),
        },
    )


async def _dispatch_compliance_ingest(command_body: str, author: str) -> AgentMessage | None:
    """Dispatch a compliance questionnaire ingestion command."""
    if questionnaire_responder is None:
        logger.error("Compliance ingestion unavailable", extra={"reason": "missing dependency"})
        return None

    parts = command_body.split()
    if len(parts) < 3:
        logger.warning("Invalid compliance ingest command: %s", command_body)
        return None

    filename = parts[1]
    tenant_id = parts[2]

    try:
        result = questionnaire_responder.ingest_questionnaire(
            filename=filename,
            tenant_id=tenant_id,
        )
        logger.info("Compliance ingestion successful: %s", result["job_id"])
        return AgentMessage(
            from_agent="chatops_executor",
            to_agent="github_app_proposer",
            message_type=MessageType.RESPONSE,
            content={
                "status": "success",
                "message": f"Successfully started ingestion for {filename}. Job ID: {result['job_id']}",
                "job_id": result["job_id"],
                "author": author,
            },
        )
    except ValueError as e:
        logger.error("Compliance ingestion failed: %s", e)
        return None


async def _dispatch_review(issue_number: int | None) -> AgentMessage | None:
    """Dispatch a review command via open-aware MCP context."""
    try:
        from src.core.integrations.nemo_agent_toolkit.mcp_bridge import ACGS2MCPClient

        mcp_client = ACGS2MCPClient(server_url=OPEN_AWARE_SERVER_URL)
        await mcp_client.connect()
        try:
            context_result = await mcp_client.call_tool(
                name="deep_research",
                arguments={
                    "query": f"Analyze recent code changes and patterns for issue {issue_number}",
                    "repositories": ["acgs2"],
                },
            )

            logger.info("Open Aware context retrieved", extra={"success": context_result.success})
            return AgentMessage(
                from_agent="chatops_executor",
                to_agent="review_swarm",
                message_type=MessageType.TASK_REQUEST,
                content={
                    "action": "execute_code_review",
                    "issue_number": issue_number,
                    "open_aware_context": context_result.data if context_result.success else None,
                },
            )
        finally:
            await mcp_client.disconnect()
    except REVIEW_DISPATCH_ERRORS as e:
        logger.error("Failed to retrieve open-aware context", extra={"error": str(e)})
        return None
    except Exception as e:
        logger.error("Failed to retrieve open-aware context", extra={"error": str(e)})
        return None
