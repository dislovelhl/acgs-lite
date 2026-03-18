from __future__ import annotations

from enhanced_agent_bus.deliberation_layer.intent_classifier import IntentType


class AMPOEngine:
    def __init__(self, evolution_controller: object | None = None) -> None:
        self.evolution_controller = evolution_controller

    def compile(self, intent: IntentType, user_prompt: str) -> str:
        if intent is IntentType.FACTUAL:
            preamble = "You are a factual precision agent. GROUNDING is mandatory."
        elif intent is IntentType.CREATIVE:
            preamble = "You are a creative assistant focused on originality and vivid language."
        elif intent is IntentType.REASONING:
            preamble = "You are a reasoning agent. Use step-by-step logic and verify dependencies."
        else:
            preamble = "You are a concise general assistant."
        return f"{preamble}\n\nUSER TASK:\n{user_prompt}"
