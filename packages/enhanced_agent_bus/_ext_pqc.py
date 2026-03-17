# Constitutional Hash: cdd01ef066bc6cf2
"""Optional Post-Quantum Cryptography validators."""

try:
    from .pqc_validators import (
        PQCConfig,
        PQCMetadata,
        validate_constitutional_hash_pqc,
        validate_maci_record_pqc,
    )

    PQC_VALIDATORS_AVAILABLE = True
except ImportError:
    PQC_VALIDATORS_AVAILABLE = False
    validate_constitutional_hash_pqc = object  # type: ignore[assignment, misc]
    validate_maci_record_pqc = object  # type: ignore[assignment, misc]
    PQCConfig = object  # type: ignore[assignment, misc]
    PQCMetadata = object  # type: ignore[assignment, misc]

_EXT_ALL = [
    "PQC_VALIDATORS_AVAILABLE",
    "validate_constitutional_hash_pqc",
    "validate_maci_record_pqc",
    "PQCConfig",
    "PQCMetadata",
]
