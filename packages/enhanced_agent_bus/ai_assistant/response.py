"""
ACGS-2 AI Assistant - Response Generation
Constitutional Hash: 608508a9bd224290

Intelligent response generation with template-based and LLM-powered
options, personality application, and constitutional validation.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone

# Import centralized constitutional hash with fallback
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .context import ConversationContext
from .nlu import Sentiment

logger = get_logger(__name__)
LLM_GENERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
)


@dataclass
class PersonalityConfig:
    """Configuration for assistant personality."""

    name: str = "Assistant"
    description: str = "A helpful AI assistant"
    tone: str = "professional"  # professional, friendly, casual, formal
    verbosity: str = "normal"  # brief, normal, detailed
    use_emojis: bool = False
    use_markdown: bool = False
    traits: list[str] = field(default_factory=lambda: ["helpful", "polite"])

    def to_dict(self) -> JSONDict:
        return {
            "name": self.name,
            "description": self.description,
            "tone": self.tone,
            "verbosity": self.verbosity,
            "use_emojis": self.use_emojis,
            "use_markdown": self.use_markdown,
            "traits": self.traits,
        }


@dataclass
class ResponseConfig:
    """Configuration for response generation system."""

    max_response_length: int = 2000
    min_response_length: int = 10
    default_personality: PersonalityConfig = field(default_factory=PersonalityConfig)
    enable_fallback: bool = True
    fallback_response: str = "I apologize, but I'm unable to assist with that request."
    enable_constitutional_validation: bool = True
    enable_caching: bool = True
    cache_ttl_seconds: int = 3600
    timeout_seconds: float = 30.0
    retry_count: int = 3
    constitutional_hash: str = field(default_factory=lambda: CONSTITUTIONAL_HASH)

    def to_dict(self) -> JSONDict:
        return {
            "max_response_length": self.max_response_length,
            "min_response_length": self.min_response_length,
            "default_personality": self.default_personality.to_dict(),
            "enable_fallback": self.enable_fallback,
            "fallback_response": self.fallback_response,
            "enable_constitutional_validation": self.enable_constitutional_validation,
            "enable_caching": self.enable_caching,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "timeout_seconds": self.timeout_seconds,
            "retry_count": self.retry_count,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class ResponseTemplate:
    """Template for generating responses."""

    id: str
    intent: str
    templates: list[str]
    conditions: JSONDict = field(default_factory=dict)
    sentiment_variants: dict[str, list[str]] = field(default_factory=dict)
    priority: int = 0

    def get_template(self, sentiment: Sentiment | None = None) -> str:
        """Get a template, optionally based on sentiment."""
        if sentiment and sentiment.name in self.sentiment_variants:
            templates = self.sentiment_variants[sentiment.name]
        else:
            templates = self.templates

        import secrets

        return secrets.choice(templates) if templates else ""


class ResponseGenerator(ABC):
    """Abstract base class for response generation."""

    @abstractmethod
    async def generate(
        self,
        intent: str,
        context: ConversationContext,
        data: JSONDict,
    ) -> str:
        """Generate a response."""
        pass


class TemplateResponseGenerator(ResponseGenerator):
    """
    Template-based response generator.

    Uses predefined templates with variable substitution
    and sentiment-aware variants.
    """

    def __init__(
        self,
        templates: list[ResponseTemplate] | None = None,
        personality: PersonalityConfig | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        config: "ResponseConfig" | None = None,
    ):
        # Use config if provided, otherwise use individual params
        if config is not None:
            self.personality = config.default_personality
            self.constitutional_hash = config.constitutional_hash
            self._config = config
        else:
            self.personality = personality or PersonalityConfig()
            self.constitutional_hash = constitutional_hash
            self._config = None
        self.templates = {t.intent: t for t in (templates or [])}
        self._load_default_templates()

    def _load_default_templates(self) -> None:
        """Load default response templates."""
        defaults = [
            ResponseTemplate(
                id="greeting",
                intent="greeting",
                templates=[
                    "Hello! How can I help you today?",
                    "Hi there! What can I do for you?",
                    "Welcome! How may I assist you?",
                ],
                sentiment_variants={
                    "POSITIVE": ["Hi! Great to hear from you! How can I help?"],
                    "NEGATIVE": ["Hello. I'm here to help. What's going on?"],
                },
            ),
            ResponseTemplate(
                id="farewell",
                intent="farewell",
                templates=[
                    "Goodbye! Have a great day!",
                    "Take care! Feel free to reach out anytime.",
                    "Bye! It was nice helping you.",
                ],
            ),
            ResponseTemplate(
                id="help",
                intent="help",
                templates=[
                    "I can help you with orders, account questions, and general inquiries. "
                    "What do you need?",
                    "Here are some things I can assist with: checking order status, "
                    "answering questions, and providing information.",
                ],
            ),
            ResponseTemplate(
                id="clarification",
                intent="clarification",
                templates=[
                    "I'm not sure I understand. Could you rephrase that?",
                    "Could you provide more details?",
                    "I didn't quite catch that. Can you say it differently?",
                ],
            ),
            ResponseTemplate(
                id="confirmation",
                intent="confirmation",
                templates=[
                    "Got it! I'll proceed with that.",
                    "Perfect, processing your request now.",
                    "Understood. Let me take care of that.",
                ],
            ),
            ResponseTemplate(
                id="error",
                intent="error",
                templates=[
                    "I apologize, but I encountered an issue. Please try again.",
                    "Something went wrong on my end. Let me try that again.",
                ],
            ),
            ResponseTemplate(
                id="escalation",
                intent="escalation",
                templates=[
                    "I understand this needs special attention. Let me connect you with "
                    "someone who can help.",
                    "This requires additional assistance. I'm transferring you to a specialist.",
                ],
                sentiment_variants={
                    "VERY_NEGATIVE": [
                        "I'm truly sorry for the frustration. Let me get you immediate help.",
                    ],
                },
            ),
        ]

        for template in defaults:
            if template.intent not in self.templates:
                self.templates[template.intent] = template

    async def generate(
        self,
        intent: str,
        context: ConversationContext,
        data: JSONDict,
    ) -> str:
        """Generate response from template."""
        # Get template for intent
        template = self.templates.get(intent)
        if not template:
            template = self.templates.get("clarification")

        if not template:
            return "I'm not sure how to respond to that."

        # Get sentiment from data
        sentiment = data.get("sentiment")
        if isinstance(sentiment, str):
            sentiment = Sentiment[sentiment] if sentiment in Sentiment.__members__ else None

        # Get base template
        response = template.get_template(sentiment)

        # Substitute variables
        response = self._substitute_variables(response, context, data)

        # Apply personality
        response = self._apply_personality(response, context)

        # Validate response
        response = self._validate_response(response)

        return response

    def _substitute_variables(
        self,
        template: str,
        context: ConversationContext,
        data: JSONDict,
    ) -> str:
        """Substitute variables in template."""
        # Substitute data variables
        for key, value in data.items():
            placeholder = f"{{{key}}}"
            if placeholder in template:
                template = template.replace(placeholder, str(value))

        # Substitute context variables
        if context.user_profile:
            template = template.replace("{user_name}", context.user_id)

        # Substitute entity variables
        for entity_type, entity_data in context.entities.items():
            placeholder = f"{{{entity_type}}}"
            if placeholder in template:
                template = template.replace(placeholder, str(entity_data.get("value", "")))

        # Substitute slot variables
        for slot_name, slot_data in context.slots.items():
            placeholder = f"{{{slot_name}}}"
            if placeholder in template:
                template = template.replace(placeholder, str(slot_data.get("value", "")))

        return template

    def _apply_personality(
        self,
        response: str,
        context: ConversationContext,
    ) -> str:
        """Apply personality traits to response."""
        # Add greeting prefix based on time
        if self.personality.tone == "friendly":
            greetings = self._get_time_greeting()
            if response.startswith("Hello"):
                response = response.replace("Hello", greetings, 1)

        # Adjust verbosity
        if self.personality.verbosity == "brief":
            response = self._make_concise(response)
        elif self.personality.verbosity == "detailed":
            response = self._add_details(response)

        # Add emojis if enabled
        if self.personality.use_emojis:
            response = self._add_emojis(response)

        # Apply formatting if markdown enabled
        if self.personality.use_markdown:
            response = self._apply_markdown(response)

        # Adjust based on user preferences
        user_prefs = context.user_profile.preferences if context.user_profile else {}
        if user_prefs.get("prefers_brief", False):
            response = self._make_concise(response)

        return response

    def _get_time_greeting(self) -> str:
        """Get greeting based on time of day."""
        hour = datetime.now(UTC).hour
        if hour < 12:
            return "Good morning"
        elif hour < 17:
            return "Good afternoon"
        else:
            return "Good evening"

    def _make_concise(self, response: str) -> str:
        """Make response more concise."""
        # Remove filler phrases
        fillers = [
            "I can help you with that. ",
            "Certainly! ",
            "Of course! ",
            "Sure thing! ",
        ]
        for filler in fillers:
            response = response.replace(filler, "")
        return response.strip()

    def _add_details(self, response: str) -> str:
        """Add more detail to response."""
        # This would be more sophisticated in production
        return response

    def _add_emojis(self, response: str) -> str:
        """Add appropriate emojis to response."""
        emoji_map = {
            "Hello": "Hello! 👋",
            "Thank you": "Thank you! 🙏",
            "Sorry": "Sorry 😔",
            "Great": "Great! 🎉",
            "Done": "Done! ✅",
        }
        for phrase, with_emoji in emoji_map.items():
            if phrase in response:
                response = response.replace(phrase, with_emoji, 1)
                break
        return response

    def _apply_markdown(self, response: str) -> str:
        """Apply markdown formatting."""
        # Simple markdown application
        # Would be more sophisticated in production
        return response

    def _validate_response(self, response: str) -> str:
        """Validate and sanitize response."""
        # Remove any unfilled placeholders
        import re

        response = re.sub(r"\{[^}]+\}", "", response)

        # Ensure response is not empty
        if not response.strip():
            response = "I'm here to help."

        # Remove extra whitespace
        response = " ".join(response.split())

        return response

    def add_template(self, template: ResponseTemplate) -> None:
        """Add or update a response template."""
        self.templates[template.intent] = template

    def remove_template(self, intent: str) -> None:
        """Remove a response template."""
        self.templates.pop(intent, None)


class LLMResponseGenerator(ResponseGenerator):
    """
    LLM-powered response generator.

    Uses a language model for dynamic, context-aware responses.
    Integrates with constitutional governance for validation.
    """

    def __init__(
        self,
        llm_client: object | None = None,
        personality: PersonalityConfig | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        max_tokens: int = 150,
        temperature: float = 0.7,
    ):
        self.llm_client = llm_client
        self.personality = personality or PersonalityConfig()
        self.constitutional_hash = constitutional_hash
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._fallback_generator = TemplateResponseGenerator(
            personality=personality,
            constitutional_hash=constitutional_hash,
        )

    async def generate(
        self,
        intent: str,
        context: ConversationContext,
        data: JSONDict,
    ) -> str:
        """Generate response using LLM."""
        if not self.llm_client:
            # Fallback to template-based generation
            return await self._fallback_generator.generate(intent, context, data)

        try:
            # Build prompt
            prompt = self._build_prompt(intent, context, data)

            # Get LLM response
            response = await self._call_llm(prompt)

            # Post-process response
            response = self._post_process(response, context)

            # Validate response
            if self._validate_response(response):
                return response
            else:
                # Fallback on validation failure
                return await self._fallback_generator.generate(intent, context, data)

        except LLM_GENERATION_ERRORS as e:
            logger.warning(f"LLM generation failed: {e}, using fallback")
            return await self._fallback_generator.generate(intent, context, data)

    def _build_prompt(
        self,
        intent: str,
        context: ConversationContext,
        data: JSONDict,
    ) -> str:
        """Build prompt for LLM."""
        # Format conversation history
        history = self._format_conversation_history(context)

        # Build system prompt
        system_prompt = f"""You are {self.personality.name}, {self.personality.description}.

Personality traits: {", ".join(self.personality.traits)}
Tone: {self.personality.tone}
Verbosity: {self.personality.verbosity}

Guidelines:
1. Be helpful and address the user's needs directly
2. Keep responses concise unless asked for detail
3. Maintain conversation continuity
4. Use information from context appropriately
5. Never mention internal systems or constitutional validation

Current user intent: {intent}"""

        # Build user context
        user_context = ""
        if context.entities:
            entity_info = ", ".join(f"{k}={v.get('value')}" for k, v in context.entities.items())
            user_context += f"Known information: {entity_info}\n"

        if data:
            relevant_data = {k: v for k, v in data.items() if k != "sentiment"}
            if relevant_data:
                user_context += f"Relevant data: {relevant_data}\n"

        # Combine into full prompt
        prompt = f"""{system_prompt}

Conversation history:
{history}

{user_context}
Generate a helpful, natural response:"""

        return prompt

    def _format_conversation_history(
        self,
        context: ConversationContext,
        max_messages: int = 5,
    ) -> str:
        """Format recent conversation history for prompt."""
        recent = context.get_recent_messages(max_messages)
        formatted = []

        for msg in recent:
            role = "User" if msg.role == "user" else "Assistant"
            formatted.append(f"{role}: {msg.content}")

        return "\n".join(formatted) if formatted else "No previous messages"

    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM with the prompt."""
        # This is a placeholder for actual LLM integration
        # In production, this would call OpenAI, Anthropic, or local model

        if hasattr(self.llm_client, "complete"):
            response = await self.llm_client.complete(
                prompt=prompt,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            return response.text if hasattr(response, "text") else str(response)

        elif hasattr(self.llm_client, "generate"):
            response = await self.llm_client.generate(
                prompt,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            return response  # type: ignore[no-any-return]

        else:
            raise ValueError("LLM client does not have expected methods")

    def _post_process(self, response: str, context: ConversationContext) -> str:
        """Post-process LLM response."""
        # Clean up response
        response = response.strip()

        # Remove any role prefixes
        prefixes = ["Assistant:", "AI:", "Bot:"]
        for prefix in prefixes:
            if response.startswith(prefix):
                response = response[len(prefix) :].strip()

        # Ensure response doesn't end mid-sentence
        if not response.endswith((".", "!", "?")):
            # Try to find last complete sentence
            for punct in [".", "!", "?"]:
                last_punct = response.rfind(punct)
                if last_punct > 0:
                    response = response[: last_punct + 1]
                    break

        return response

    def _validate_response(self, response: str) -> bool:
        """Validate LLM response for safety and appropriateness."""
        if not response or len(response) < 3:
            return False

        # Check for inappropriate content (placeholder)
        blocked_patterns = [
            "I cannot",
            "I'm sorry, but I cannot",
            "As an AI",
            "constitutional hash",
            "internal system",
        ]

        return all(pattern.lower() not in response.lower() for pattern in blocked_patterns)


class HybridResponseGenerator(ResponseGenerator):
    """
    Hybrid response generator combining template and LLM approaches.

    Uses templates for common intents and LLM for complex or novel situations.
    """

    def __init__(
        self,
        llm_client: object | None = None,
        templates: list[ResponseTemplate] | None = None,
        personality: PersonalityConfig | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        llm_intents: list[str] | None = None,
    ):
        self.template_generator = TemplateResponseGenerator(
            templates=templates,
            personality=personality,
            constitutional_hash=constitutional_hash,
        )
        self.llm_generator = LLMResponseGenerator(
            llm_client=llm_client,
            personality=personality,
            constitutional_hash=constitutional_hash,
        )
        self.llm_intents = llm_intents or [
            "question",
            "request_info",
            "complex_query",
            "open_ended",
        ]
        self.constitutional_hash = constitutional_hash

    async def generate(
        self,
        intent: str,
        context: ConversationContext,
        data: JSONDict,
    ) -> str:
        """Generate response using appropriate method."""
        # Use LLM for specified intents or complex situations
        use_llm = (
            intent in self.llm_intents
            or data.get("requires_llm", False)
            or len(context.messages) > 10  # Complex conversation
        )

        if use_llm and self.llm_generator.llm_client:
            return await self.llm_generator.generate(intent, context, data)
        else:
            return await self.template_generator.generate(intent, context, data)

    def set_llm_client(self, llm_client: object) -> None:
        """set the LLM client."""
        self.llm_generator.llm_client = llm_client

    def add_template(self, template: ResponseTemplate) -> None:
        """Add a response template."""
        self.template_generator.add_template(template)

    def add_llm_intent(self, intent: str) -> None:
        """Add an intent to be handled by LLM."""
        if intent not in self.llm_intents:
            self.llm_intents.append(intent)
