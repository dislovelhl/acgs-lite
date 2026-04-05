try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

"""
Dafny Formal Verification Adapter for ACGS-2
Constitutional Hash: 608508a9bd224290

Provides a bridge between Python governance cycles and Dafny formal proofs.
"""

import asyncio
import os
from dataclasses import dataclass

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
DAFNY_VERIFICATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    OSError,
    asyncio.TimeoutError,
)


@dataclass
class DafnyVerificationResult:
    is_valid: bool
    output: str
    error: str | None = None
    verification_time_ms: float = 0.0
    constitutional_hash: str = CONSTITUTIONAL_HASH


class DafnyAdapter:
    """
    Adapter for invoking the Dafny verifier on formal specifications.

    This adapter enables ACGS-2 to leverage co-inductive proofs and
    hardware-level guarantees defined in Dafny.
    """

    def __init__(self, dafny_path: str = "dafny"):
        self.dafny_path = dafny_path
        self.constitutional_hash = CONSTITUTIONAL_HASH

    async def verify_file(self, file_path: str) -> DafnyVerificationResult:
        """
        Verify a Dafny source file.
        """
        if not os.path.exists(file_path):
            return DafnyVerificationResult(
                is_valid=False, output="", error=f"File not found: {file_path}"
            )

        loop = asyncio.get_running_loop()
        start_time = loop.time()

        try:
            # Command to verify only (no compilation)
            cmd = [self.dafny_path, "verify", file_path]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            end_time = loop.time()
            duration_ms = (end_time - start_time) * 1000

            output = stdout.decode().strip()
            error = stderr.decode().strip()

            # Dafny verification success usually contains '0 errors'
            is_valid = process.returncode == 0 and "0 errors" in output

            return DafnyVerificationResult(
                is_valid=is_valid,
                output=output,
                error=error if error else None,
                verification_time_ms=duration_ms,
            )

        except DAFNY_VERIFICATION_ERRORS as e:
            logger.error(f"Dafny verification failed: {e}")
            return DafnyVerificationResult(
                is_valid=False,
                output="",
                error=str(e),
                verification_time_ms=(loop.time() - start_time) * 1000,
            )

    async def check_hardware_guarantees(self) -> DafnyVerificationResult:
        """
        Specific check for hardware resource guarantees.
        """
        # Path to the hardware guarantees proof
        proof_path = os.path.join(
            os.path.dirname(__file__), "../../shared/policy/experimental/hardware_guarantees.dfy"
        )
        return await self.verify_file(proof_path)
