from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from typing import Any

from enhanced_agent_bus.config import BusConfiguration

from .conversation import MessageRole
from .pacar_manager import PACARManager

sys.modules.setdefault("enhanced_agent_bus.sdpc.pacar_verifier", sys.modules[__name__])


class _DefaultAssistant:
    async def analyze_message_impact(self, content: str) -> dict[str, Any]:
        return {
            "risk_level": "low",
            "confidence": 0.8,
            "reasoning": ["default_review"],
            "mitigations": ["none"],
        }

    async def ainvoke_multi_turn(
        self, content: str, history: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "recommended_decision": "approve",
            "risk_level": "low",
            "confidence": 0.8,
            "reasoning": ["default_multi_turn_review"],
            "mitigations": ["none"],
        }


def get_llm_assistant() -> Any:
    return _DefaultAssistant()


class PACARVerifier:
    def __init__(self, config: BusConfiguration | None = None) -> None:
        self.config = config or BusConfiguration()
        self.assistant = get_llm_assistant()
        self.manager = PACARManager(config=self.config)
        self.redis_client: Any | None = None
        self.audit_client: Any | None = None

    async def verify(self, content: str, original_intent: str) -> dict[str, Any]:
        analysis = await self.assistant.analyze_message_impact(content)
        return {
            "is_valid": analysis.get("risk_level") != "high",
            "confidence": analysis.get("confidence", 0.0),
            "reasoning": analysis.get("reasoning", []),
            "mitigations": analysis.get("mitigations", []),
            "consensus_reached": analysis.get("risk_level") != "high",
            "critique": analysis.get("reasoning", []),
        }

    async def verify_with_context(
        self,
        content: str,
        original_intent: str,
        session_id: str,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        redis_key = f"pacar:session:{session_id}"
        conversation: dict[str, Any]
        if self.redis_client is not None:
            existing = await self.redis_client.get(redis_key)
            conversation = (
                json.loads(existing)
                if existing
                else {
                    "session_id": session_id,
                    "tenant_id": tenant_id,
                    "messages": [],
                    "created_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            )
        else:
            state = await self.manager.get_state(session_id)
            if hasattr(state, "model_dump") and callable(state.model_dump):
                dumped = state.model_dump()
                conversation = dumped if isinstance(dumped, dict) else {}
            else:
                conversation = {}
            if not conversation:
                conversation = {
                    "session_id": session_id,
                    "tenant_id": tenant_id,
                    "messages": [
                        msg.model_dump() if hasattr(msg, "model_dump") else msg
                        for msg in getattr(state, "messages", [])
                    ],
                }
            conversation.setdefault("tenant_id", tenant_id)

        multi_turn = await self.assistant.ainvoke_multi_turn(
            content, conversation.get("messages", [])
        )
        verification_result = {
            "is_valid": multi_turn.get("recommended_decision", "approve") == "approve",
            "confidence": multi_turn.get("confidence", 0.0),
        }
        entry = {
            "role": "user",
            "content": content,
            "timestamp": datetime.now(UTC).isoformat(),
            "intent": original_intent,
            "verification_result": verification_result,
        }
        conversation.setdefault("messages", []).append(entry)
        if len(conversation["messages"]) > 50:
            conversation["messages"] = conversation["messages"][-50:]
        conversation["session_id"] = session_id
        conversation["tenant_id"] = tenant_id or conversation.get("tenant_id")
        conversation["updated_at"] = datetime.now(UTC).isoformat()

        if self.redis_client is not None:
            await self.redis_client.setex(redis_key, 3600, json.dumps(conversation))

        if self.manager is not None:
            await self.manager.add_message(
                session_id, MessageRole.USER, content, {"intent": original_intent}
            )
            await self.manager.add_message(
                session_id,
                MessageRole.ASSISTANT,
                "\n".join(multi_turn.get("reasoning", [])),
                {"phase": "critique"},
            )
            await self.manager.add_message(
                session_id,
                MessageRole.SYSTEM,
                multi_turn.get("recommended_decision", "approve"),
                {"phase": "decision"},
            )

        result = {
            "is_valid": verification_result["is_valid"],
            "confidence": verification_result["confidence"],
            "reasoning": multi_turn.get("reasoning", []),
            "mitigations": multi_turn.get("mitigations", []),
            "recommended_decision": multi_turn.get("recommended_decision", "approve"),
            "consensus_reached": multi_turn.get("recommended_decision", "approve") == "approve",
            "session_id": session_id,
            "message_count": len(conversation["messages"]),
        }
        if self.audit_client is not None and hasattr(self.audit_client, "report_decision"):
            await self.audit_client.report_decision(result)
        return result
