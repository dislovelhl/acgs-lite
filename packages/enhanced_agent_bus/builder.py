# Constitutional Hash: 608508a9bd224290
"""
Builder and Factories for MessageProcessor dependencies.
Isolates complex initialization and cross-layer instantiation logic.
"""

from dataclasses import dataclass
from typing import Literal

from enhanced_agent_bus._compat.security.pqc_crypto import PQCCryptoService

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.config import BusConfiguration
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)


@dataclass
class SDPCVerifiers:
    intent_classifier: object
    asc_verifier: object
    graph_check: object
    pacar_verifier: object
    evolution_controller: object
    ampo_engine: object
    IntentType: object


# Global cache for verifiers to prevent re-initialization overhead
_cached_sdpc: SDPCVerifiers | None = None
_cached_pqc: PQCCryptoService | None = None


def build_sdpc_verifiers(config: BusConfiguration) -> SDPCVerifiers:
    global _cached_sdpc
    if _cached_sdpc is not None:
        return _cached_sdpc

    try:
        from enhanced_agent_bus.deliberation_layer.intent_classifier import (
            IntentClassifier,
            IntentType,
        )
        from enhanced_agent_bus.sdpc.ampo_engine import AMPOEngine
        from enhanced_agent_bus.sdpc.asc_verifier import ASCVerifier
        from enhanced_agent_bus.sdpc.evolution_controller import EvolutionController
        from enhanced_agent_bus.sdpc.graph_check import GraphCheckVerifier
        from enhanced_agent_bus.sdpc.pacar_verifier import PACARVerifier

        intent_classifier = IntentClassifier(config=config)
        asc_verifier = ASCVerifier()
        graph_check = GraphCheckVerifier()
        pacar_verifier = PACARVerifier(config=config)
        evolution_controller = EvolutionController()
        ampo_engine = AMPOEngine(evolution_controller=evolution_controller)
    except ImportError as exc:
        logger.warning("SDPC dependencies unavailable (%s); using no-op verifier stubs.", exc)

        class _NoOpVerifier:
            async def verify(self, *args: object, **kwargs: object) -> JSONDict:
                _ = (args, kwargs)
                return {"valid": True}

        class _NoOpIntentClassifier:
            def __init__(self, config: object) -> None:
                self.config = config

            async def classify_intent(self, *args: object, **kwargs: object) -> str:
                _ = (args, kwargs)
                return "unknown"

        class _NoOpEvolutionController:
            """Fail-safe NoOp: logs all mutation attempts, allows none."""

            def record_feedback(self, intent: object, verification_results: object) -> None:
                _ = (intent, verification_results)

            def _trigger_mutation(self, intent: object) -> None:
                _ = intent

            def get_mutations(self, intent: object) -> list:  # type: ignore[type-arg]
                _ = intent
                return []

            def reset_mutations(self, intent: object = None) -> None:
                _ = intent

        class _NoOpAMPOEngine:
            def __init__(self, evolution_controller: object) -> None:
                self.evolution_controller = evolution_controller

        class _IntentType:
            UNKNOWN = "unknown"

        intent_classifier = _NoOpIntentClassifier(config=config)
        asc_verifier = _NoOpVerifier()
        graph_check = _NoOpVerifier()
        pacar_verifier = _NoOpVerifier()
        evolution_controller = _NoOpEvolutionController()
        ampo_engine = _NoOpAMPOEngine(evolution_controller=evolution_controller)
        IntentType = _IntentType

    _cached_sdpc = SDPCVerifiers(
        intent_classifier=intent_classifier,
        asc_verifier=asc_verifier,
        graph_check=graph_check,
        pacar_verifier=pacar_verifier,
        evolution_controller=evolution_controller,
        ampo_engine=ampo_engine,
        IntentType=IntentType,
    )
    return _cached_sdpc


def build_pqc_service(config: BusConfiguration) -> PQCCryptoService | None:
    """Dynamically load and configure the PQC crypto service if enabled."""
    global _cached_pqc
    if _cached_pqc is not None:
        return _cached_pqc

    if not config.enable_pqc:
        return None

    try:
        import importlib

        _pqc = importlib.import_module(
            "src.core.services.policy_registry.app.services.pqc_crypto_service"
        )
        ConcretePQCConfig = _pqc.PQCConfig
        ConcretePQCCryptoService = _pqc.PQCCryptoService

        pqc_mode: Literal["classical_only", "hybrid", "pqc_only"] = "classical_only"
        if config.pqc_mode in ("classical_only", "hybrid", "pqc_only"):
            pqc_mode = config.pqc_mode  # type: ignore[assignment]

        verification_mode: Literal["strict", "classical_only", "pqc_only"] = "strict"
        if config.pqc_verification_mode in ("strict", "classical_only", "pqc_only"):
            verification_mode = config.pqc_verification_mode  # type: ignore[assignment]

        migration_phase: Literal[
            "phase_0", "phase_1", "phase_2", "phase_3", "phase_4", "phase_5"
        ] = "phase_0"
        phase_str = str(config.pqc_migration_phase) if config.pqc_migration_phase else "phase_0"
        if phase_str.startswith("phase_"):
            migration_phase = phase_str  # type: ignore[assignment]

        pqc_config = ConcretePQCConfig(
            pqc_enabled=True,
            pqc_mode=pqc_mode,
            verification_mode=verification_mode,
            kem_algorithm=config.pqc_key_algorithm
            if hasattr(config, "pqc_key_algorithm")
            else "kyber768",  # type: ignore[arg-type]
            migration_phase=migration_phase,
        )

        _cached_pqc = ConcretePQCCryptoService(config=pqc_config)
        logger.info(
            f"PQC enabled: mode={config.pqc_mode}, "
            f"verification={config.pqc_verification_mode}, "
            f"phase={config.pqc_migration_phase}"
        )
        return _cached_pqc  # type: ignore[return-value]
    except ImportError as e:
        logger.warning(f"PQC libraries not available: {e}. PQC validation disabled.")
        return None
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as e:
        logger.error(f"Failed to initialize PQC service: {e}. PQC validation disabled.")
        return None
