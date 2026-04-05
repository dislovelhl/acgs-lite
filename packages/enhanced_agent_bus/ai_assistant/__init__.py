"""
ACGS-2 AI Assistant Module
Constitutional Hash: 608508a9bd224290

Provides conversational AI assistant capabilities with NLU, dialog management,
response generation, and Agent Bus integration for governance compliance.
"""

from enhanced_agent_bus.observability.structured_logging import get_logger

# Core orchestrator
# Context management
from .context import (
    ContextManager,
    ConversationContext,
    ConversationState,
    Message,
    MessageRole,
    UserProfile,
)
from .core import (
    AIAssistant,
    AssistantConfig,
    AssistantState,
    ConversationListener,
    ProcessingResult,
    create_assistant,
)

# Dialog management
from .dialog import (
    ActionType,
    ConversationFlow,
    DialogAction,
    DialogManager,
    DialogPolicy,
    FlowNode,
    RuleBasedDialogPolicy,
)

# Agent Bus integration
from .integration import AgentBusIntegration, GovernanceDecision, IntegrationConfig

# NLU components
from .nlu import (
    BasicSentimentAnalyzer,
    EntityExtractor,
    IntentClassifier,
    NLUEngine,
    NLUResult,
    PatternEntityExtractor,
    RuleBasedIntentClassifier,
    SentimentAnalyzer,
)

# Response generation
from .response import (
    HybridResponseGenerator,
    LLMResponseGenerator,
    PersonalityConfig,
    ResponseConfig,
    ResponseGenerator,
    TemplateResponseGenerator,
)

logger = get_logger(__name__)
"""
ACGS-2 AI Assistant Framework
Constitutional Hash: 608508a9bd224290

Production-ready AI assistant with constitutional governance integration.
Provides NLU, dialog management, and response generation with constitutional validation.

Example usage:
    from enhanced_agent_bus.ai_assistant import AIAssistant, create_assistant

    # Quick start
    assistant = await create_assistant(name="My Assistant")
    result = await assistant.process_message(
        user_id="user123",
        message="What is my order status?"
    )
    logging.info(result.response_text)

    # Full control
    from enhanced_agent_bus.ai_assistant import (
        AIAssistant,
        AssistantConfig,
        NLUEngine,
        DialogManager,
        ResponseGenerator,
    )

    config = AssistantConfig(
        name="Custom Assistant",
        enable_governance=True,
    )
    assistant = AIAssistant(config=config)
    await assistant.initialize()
"""

# Import centralized constitutional hash with fallback
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

__version__ = "1.0.0"
__constitutional_hash__ = CONSTITUTIONAL_HASH

__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    # Core
    "AIAssistant",
    "ActionType",
    # Integration
    "AgentBusIntegration",
    "AssistantConfig",
    "AssistantState",
    "BasicSentimentAnalyzer",
    "ContextManager",
    # Context
    "ConversationContext",
    "ConversationFlow",
    "ConversationListener",
    "ConversationState",
    "DialogAction",
    # Dialog
    "DialogManager",
    "DialogPolicy",
    "EntityExtractor",
    "FlowNode",
    "GovernanceDecision",
    "HybridResponseGenerator",
    "IntegrationConfig",
    "IntentClassifier",
    "LLMResponseGenerator",
    "Message",
    "MessageRole",
    # NLU
    "NLUEngine",
    "NLUResult",
    "PatternEntityExtractor",
    "PersonalityConfig",
    "ProcessingResult",
    "ResponseConfig",
    # Response
    "ResponseGenerator",
    "RuleBasedDialogPolicy",
    "RuleBasedIntentClassifier",
    "SentimentAnalyzer",
    "TemplateResponseGenerator",
    "UserProfile",
    "create_assistant",
]
