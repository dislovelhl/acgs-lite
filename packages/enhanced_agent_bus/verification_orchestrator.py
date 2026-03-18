"""
ACGS-2 Enhanced Agent Bus - Verification Orchestrator
Constitutional Hash: cdd01ef066bc6cf2

Coordinates SDPC (Semantic Data Processing Chain) verification and
PQC (Post-Quantum Cryptographic) constitutional validation in parallel.

Extracted from MessageProcessor to provide a single-responsibility
verification coordinator.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Literal

try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .config import BusConfiguration
from .models import AgentMessage, MessageType
from .performance_monitor import timed
from .validators import ValidationResult

logger = get_logger(__name__)
PQC_OPERATION_ERRORS = (
    AttributeError,
    OSError,
    RuntimeError,
    TimeoutError,
    TypeError,
    ValueError,
)


@dataclass
class VerificationResult:
    """Result of combined SDPC + PQC verification.

    Attributes:
        sdpc_metadata: Dict of SDPC verification data (intents,
            ASC results, graph grounding, PACAR confidence, etc.).
        pqc_result: ``None`` when PQC is disabled or passed; a
            ``ValidationResult`` when PQC validation failed.
    """

    sdpc_metadata: JSONDict = field(default_factory=dict)
    pqc_result: ValidationResult | None = None
    pqc_metadata: JSONDict = field(default_factory=dict)


class VerificationOrchestrator:
    """Parallel SDPC + PQC verification coordinator.

    Initialises all SDPC verifiers (IntentClassifier, ASCVerifier,
    GraphCheckVerifier, PACARVerifier, EvolutionController, AMPOEngine)
    and optionally the PQC crypto service.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        config: BusConfiguration,
        enable_pqc: bool = False,
    ) -> None:
        self._config = config
        self._enable_pqc = enable_pqc

        # --- SDPC verifiers ---
        try:
            from enhanced_agent_bus.deliberation_layer.intent_classifier import (
                IntentClassifier,
                IntentType,
            )
            from enhanced_agent_bus.sdpc.ampo_engine import AMPOEngine
            from enhanced_agent_bus.sdpc.asc_verifier import ASCVerifier
            from enhanced_agent_bus.sdpc.evolution_controller import (
                EvolutionController,
            )
            from enhanced_agent_bus.sdpc.graph_check import (
                GraphCheckVerifier,
            )
            from enhanced_agent_bus.sdpc.pacar_verifier import (
                PACARVerifier,
            )

            self.intent_classifier = IntentClassifier(config=config)
            self.asc_verifier = ASCVerifier()
            self.graph_check = GraphCheckVerifier()
            self.pacar_verifier = PACARVerifier(config=config)
            self.evolution_controller = EvolutionController()
            self.ampo_engine = AMPOEngine(evolution_controller=self.evolution_controller)
            self._IntentType = IntentType
        except ImportError as exc:
            logger.warning("SDPC dependencies unavailable (%s); using no-op verifier stubs.", exc)

            class _IntentValue:
                def __init__(self, value: str):
                    self.value = value

            class _IntentType:
                FACTUAL = _IntentValue("factual")
                REASONING = _IntentValue("reasoning")
                UNKNOWN = _IntentValue("unknown")

            class _NoOpIntentClassifier:
                def __init__(self, config: BusConfiguration):
                    self.config = config

                async def classify_async(self, content_str: str) -> _IntentValue:
                    _ = content_str
                    return _IntentType.UNKNOWN

            class _NoOpVerifier:
                async def verify(self, *args: object, **kwargs: object) -> JSONDict:
                    _ = (args, kwargs)
                    return {"is_valid": True, "confidence": 1.0, "results": []}

                async def verify_entities(self, *args: object, **kwargs: object) -> JSONDict:
                    _ = (args, kwargs)
                    return {"is_valid": True, "results": []}

            class _NoOpEvolutionController:
                def record_feedback(self, intent: object, verifications: JSONDict) -> None:
                    _ = (intent, verifications)

            class _NoOpAMPOEngine:
                def __init__(self, evolution_controller: _NoOpEvolutionController):
                    self.evolution_controller = evolution_controller

            self.intent_classifier = _NoOpIntentClassifier(config=config)
            self.asc_verifier = _NoOpVerifier()
            self.graph_check = _NoOpVerifier()
            self.pacar_verifier = _NoOpVerifier()
            self.evolution_controller = _NoOpEvolutionController()
            self.ampo_engine = _NoOpAMPOEngine(evolution_controller=self.evolution_controller)
            self._IntentType = _IntentType

        # --- PQC service (graceful degradation) ---
        self._pqc_config = None
        self._pqc_service = None
        if self._enable_pqc:
            self._init_pqc(config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @timed("verification_orchestrate")
    async def verify(
        self,
        msg: AgentMessage,
        content_str: str,
    ) -> VerificationResult:
        """Run SDPC and PQC verification in parallel.

        Args:
            msg: The agent message.
            content_str: String representation of message content.

        Returns:
            A :class:`VerificationResult` with SDPC metadata and
            optional PQC failure result.
        """
        sdpc_task = self._perform_sdpc(msg, content_str)
        pqc_task = self.verify_pqc(msg)

        (sdpc_metadata, _), (pqc_result, pqc_metadata) = await asyncio.gather(sdpc_task, pqc_task)
        return VerificationResult(
            sdpc_metadata=sdpc_metadata,
            pqc_result=pqc_result,
            pqc_metadata=pqc_metadata,
        )

    async def verify_pqc(self, msg: AgentMessage) -> tuple[ValidationResult | None, JSONDict]:
        """Run PQC verification and return validation result plus success metadata."""
        return await self._perform_pqc(msg)

    # ------------------------------------------------------------------
    # SDPC verification
    # ------------------------------------------------------------------

    @timed("sdpc_verification")
    async def _perform_sdpc(
        self,
        msg: AgentMessage,
        content_str: str,
    ) -> tuple[JSONDict, JSONDict]:
        """Perform SDPC (intent → ASC/graph/PACAR) verification."""
        sdpc_metadata: JSONDict = {}
        verifications: JSONDict = {}

        intent = await self.intent_classifier.classify_async(content_str)
        impact_score = getattr(msg, "impact_score", 0.0)
        if impact_score is None:
            impact_score = 0.0

        needs_asc_graph = (
            intent.value
            in [
                self._IntentType.FACTUAL.value,
                self._IntentType.REASONING.value,
            ]
            or impact_score >= 0.8
        )
        needs_pacar = impact_score > 0.8 or msg.message_type == MessageType.TASK_REQUEST

        tasks = []
        task_names: list[str] = []

        if needs_asc_graph:
            tasks.append(self.asc_verifier.verify(content_str, intent))
            task_names.append("asc")
            tasks.append(self.graph_check.verify_entities(content_str))
            task_names.append("graph")

        if needs_pacar:
            tasks.append(
                self.pacar_verifier.verify(
                    content_str,
                    intent.value,
                    session_id=getattr(msg, "session_id", None),
                )
            )
            task_names.append("pacar")

        if tasks:
            results = await asyncio.gather(*tasks)
            for name, result in zip(task_names, results, strict=True):
                if name == "asc":
                    sdpc_metadata["sdpc_intent"] = intent.value
                    sdpc_metadata["sdpc_asc_valid"] = result.get("is_valid", False)
                    sdpc_metadata["sdpc_asc_confidence"] = result.get("confidence", 0.0)
                    verifications["asc"] = sdpc_metadata["sdpc_asc_valid"]
                elif name == "graph":
                    sdpc_metadata["sdpc_graph_grounded"] = result.get("is_valid", False)
                    sdpc_metadata["sdpc_graph_results"] = result.get("results", [])
                    verifications["graph"] = sdpc_metadata["sdpc_graph_grounded"]
                elif name == "pacar":
                    sdpc_metadata["sdpc_pacar_valid"] = result.get("is_valid", False)
                    sdpc_metadata["sdpc_pacar_confidence"] = result.get("confidence", 0.0)
                    verifications["pacar"] = sdpc_metadata["sdpc_pacar_valid"]
                    if "critique" in result:
                        sdpc_metadata["sdpc_pacar_critique"] = result["critique"]

        if verifications:
            self.evolution_controller.record_feedback(intent, verifications)

        return sdpc_metadata, verifications

    # ------------------------------------------------------------------
    # PQC validation
    # ------------------------------------------------------------------

    @timed("pqc_validation")
    async def _perform_pqc(
        self,
        msg: AgentMessage,
    ) -> tuple[ValidationResult | None, JSONDict]:
        """Perform PQC constitutional validation."""
        if not self._enable_pqc or not self._pqc_config:
            return None, {}

        try:
            from .models import CONSTITUTIONAL_HASH
            from .pqc_validators import validate_constitutional_hash_pqc

            message_data: JSONDict = {
                "constitutional_hash": msg.constitutional_hash,
                "content": msg.content,
                "message_id": msg.message_id,
                "from_agent": msg.from_agent,
                "tenant_id": msg.tenant_id,
                "created_at": (
                    msg.created_at.isoformat()
                    if hasattr(msg.created_at, "isoformat")
                    else str(msg.created_at)
                ),
            }

            if hasattr(msg, "signature") and msg.signature:  # type: ignore[attr-defined]
                message_data["signature"] = msg.signature  # type: ignore[attr-defined]

            pqc_result = await validate_constitutional_hash_pqc(
                data=message_data,
                expected_hash=CONSTITUTIONAL_HASH,
                pqc_config=self._pqc_config,
            )

            if not pqc_result.valid:
                return (
                    ValidationResult(
                        is_valid=False,
                        errors=pqc_result.errors,
                        metadata={
                            "rejection_reason": "pqc_validation_failed",
                            "pqc_metadata": (
                                pqc_result.pqc_metadata.to_dict()
                                if pqc_result.pqc_metadata
                                else None
                            ),
                            "validation_duration_ms": (pqc_result.validation_duration_ms),
                        },
                    ),
                    {},
                )

            success_metadata: JSONDict = {}
            if pqc_result.pqc_metadata:
                success_metadata["pqc_enabled"] = True
                success_metadata["pqc_algorithm"] = pqc_result.pqc_metadata.pqc_algorithm
                success_metadata["pqc_verification_mode"] = (
                    pqc_result.pqc_metadata.verification_mode
                )
                success_metadata["classical_verified"] = pqc_result.pqc_metadata.classical_verified
                success_metadata["pqc_verified"] = pqc_result.pqc_metadata.pqc_verified
                if pqc_result.classical_verification_ms:
                    success_metadata["classical_verification_ms"] = (
                        pqc_result.classical_verification_ms
                    )
                if pqc_result.pqc_verification_ms:
                    success_metadata["pqc_verification_ms"] = pqc_result.pqc_verification_ms

            return None, success_metadata

        except ImportError:
            logger.warning("PQC validators not available. Skipping PQC validation.")
        except PQC_OPERATION_ERRORS as exc:
            logger.error("PQC validation error: %s", exc, exc_info=True)
            if self._pqc_config and self._pqc_config.pqc_mode == "pqc_only":
                return (
                    ValidationResult(
                        is_valid=False,
                        errors=[f"PQC validation error: {exc!s}"],
                        metadata={
                            "rejection_reason": "pqc_validation_error",
                        },
                    ),
                    {},
                )
            logger.warning(
                "PQC validation failed, continuing with standard validation: %s",
                exc,
            )

        return None, {}

    # ------------------------------------------------------------------
    # PQC initialisation
    # ------------------------------------------------------------------

    def _init_pqc(self, config: BusConfiguration) -> None:
        """Initialise PQC crypto service with graceful degradation."""
        try:
            import importlib

            from .pqc_validators import PQCConfig

            PQCCryptoService = (
                importlib.import_module(
                    "src.core.services.policy_registry.app.services.pqc_crypto_service"
                )
            ).PQCCryptoService

            pqc_mode: Literal["classical_only", "hybrid", "pqc_only"] = "classical_only"
            if config.pqc_mode in (
                "classical_only",
                "hybrid",
                "pqc_only",
            ):
                pqc_mode = config.pqc_mode  # type: ignore[assignment]

            verification_mode: Literal["strict", "classical_only", "pqc_only"] = "strict"
            if config.pqc_verification_mode in (
                "strict",
                "classical_only",
                "pqc_only",
            ):
                verification_mode = config.pqc_verification_mode  # type: ignore[assignment]

            migration_phase: Literal[
                "phase_0",
                "phase_1",
                "phase_2",
                "phase_3",
                "phase_4",
                "phase_5",
            ] = "phase_0"
            phase_str = str(config.pqc_migration_phase) if config.pqc_migration_phase else "phase_0"
            if phase_str.startswith("phase_"):
                migration_phase = phase_str  # type: ignore[assignment]

            self._pqc_config = PQCConfig(
                pqc_enabled=True,
                pqc_mode=pqc_mode,
                verification_mode=verification_mode,
                kem_algorithm=(
                    config.pqc_key_algorithm if hasattr(config, "pqc_key_algorithm") else "kyber768"
                ),  # type: ignore[arg-type]
                migration_phase=migration_phase,
            )
            self._pqc_service = PQCCryptoService(config=self._pqc_config)
            logger.info(
                "PQC enabled: mode=%s, verification=%s, phase=%s",
                config.pqc_mode,
                config.pqc_verification_mode,
                config.pqc_migration_phase,
            )
        except ImportError as exc:
            logger.warning(
                "PQC libraries not available: %s. PQC validation disabled.",
                exc,
            )
            self._enable_pqc = False
        except PQC_OPERATION_ERRORS as exc:
            logger.error(
                "Failed to initialize PQC service: %s. PQC validation disabled.",
                exc,
            )
            self._enable_pqc = False
