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
        # Append dynamic mutations from evolution controller
        mutations_block = ""
        if self.evolution_controller is not None:
            from enhanced_agent_bus.sdpc.evolution_controller import EvolutionController

            if isinstance(self.evolution_controller, EvolutionController):
                mutations = self.evolution_controller.get_mutations(intent)
                if mutations:
                    mutations_block = "\n" + "\n".join(mutations) + "\n"

        return f"{preamble}{mutations_block}\n\nUSER TASK:\n{user_prompt}"
