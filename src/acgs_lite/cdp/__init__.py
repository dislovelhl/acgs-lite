"""Constitutional Decision Provenance (CDP) — unified immutable governance record.

CDP ties every governance decision to a verifiable, tamper-evident artifact:
- What was decided (verdict, rules matched/violated)
- Why (reasoning, confidence, risk score)
- Which rules governed it (constitutional hash, policy IDs)
- Who in the MACI chain acted (proposer, validator, executor, observer)
- What was prevented (violations, interventions)

Constitutional Hash: 608508a9bd224290
"""

from acgs_lite.cdp.assembler import assemble_cdp_record
from acgs_lite.cdp.record import (
    CDPRecordV1,
    ComplianceEvidenceRef,
    InterventionOutcome,
    MACIStep,
)
from acgs_lite.cdp.store import CDPBackend, InMemoryCDPBackend

__all__ = [
    "CDPRecordV1",
    "CDPBackend",
    "ComplianceEvidenceRef",
    "InMemoryCDPBackend",
    "InterventionOutcome",
    "MACIStep",
    "assemble_cdp_record",
]
