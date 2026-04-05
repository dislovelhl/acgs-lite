"""Leanstral formal verification — Lean 4 proof certificates for governance rules.

Uses Mistral's Leanstral model to auto-formalize constitutional rules into
Lean 4 predicates, generate proofs, and verify them against the Lean kernel.
The LLM generates; the kernel verifies. The trust boundary is the Lean type
checker, not the language model.

Architecture::

    ACGS Rule (natural language)
        → Leanstral auto-formalizes to Lean 4 predicate
            → Leanstral generates proof attempt
                → Lean kernel type-checks (TRUST BOUNDARY)
                    → if error: feed back to Leanstral, retry
                    → if ok: ProofCertificate attached to AuditEntry

Architecture position:
    Layer 1:  GovernanceEngine (keyword rules, ~443ns)
    Layer 2:  ConstitutionalImpactScorer (semantic risk, ~1ms)
    Layer 3a: Z3ConstraintVerifier (SMT, ~50-500ms, decidable fragments)
    Layer 3b: LeanstralVerifier (ITP, ~1-30s, inductive/dependent types, this module)

Use Layer 3b when:
    - Constraints require inductive reasoning (role hierarchies, recursive rules)
    - You need machine-verifiable proof certificates for compliance audits
    - Z3 returns 'unknown' and you need a proof witness
    - Proving rule consistency (no two Rules contradict)
    - Proving audit chain integrity (hash-chain verification in Lean)

Usage::

    from acgs_lite.lean_verify import LeanstralVerifier, ProofCertificate

    verifier = LeanstralVerifier(api_key="your-mistral-key")

    # Verify an action against rules
    result = verifier.verify(
        action="promote agent to validator role",
        rules=[
            {"id": "MACI-1", "text": "No agent may validate its own proposals"},
            {"id": "MACI-2", "text": "Role promotion requires judicial approval"},
        ],
        context={"agent_role": "executive", "target_role": "validator"},
    )

    if result.proved:
        # Proof was verified by the Lean kernel
        print(result.certificate.lean_proof)
        # Attach to audit entry
        audit_log.record(entry, proof_certificate=result.certificate)

Installation::

    pip install acgs-lite[mistral]  # Mistral SDK for Leanstral
    elan install                     # Lean 4 toolchain (optional but recommended)

    # Without Lean installed, proofs are generated but NOT kernel-verified.
    # The result will have kernel_verified=False.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

try:
    from mistralai import Mistral

    MISTRAL_AVAILABLE = True
except ImportError:
    MISTRAL_AVAILABLE = False
    Mistral = None  # type: ignore[assignment,misc]

# Lean 4 toolchain detection
LEAN_AVAILABLE = shutil.which("lean") is not None

# Model ID for Leanstral (Mistral's Lean 4 proof model)
_LEANSTRAL_MODEL = "leanstral"
_FALLBACK_MODEL = "codestral-latest"

# Iteration limits
_MAX_PROOF_ATTEMPTS = 3
_MAX_TOKENS = 4096
_LEAN_TIMEOUT_S = 30
_DEFAULT_API_TIMEOUT_S = 60


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProofCertificate:
    """Machine-verifiable proof certificate for a governance decision.

    Attach to AuditEntry for compliance-grade evidence that an action
    satisfies constitutional constraints.
    """

    lean_statement: str
    """The Lean 4 theorem statement (what was proved)."""

    lean_proof: str
    """The Lean 4 proof term (the proof itself)."""

    kernel_verified: bool
    """True if the Lean kernel type-checked this proof.
    False if Lean is not installed (proof generated but not verified)."""

    rules_formalized: dict[str, str]
    """Map of rule_id → Lean 4 predicate for each governance rule."""

    proof_hash: str
    """SHA-256 of the complete Lean source for tamper detection."""

    model_used: str
    """Which model generated the proof."""

    verification_time_ms: float
    """Total wall-clock time including kernel verification."""

    def to_audit_dict(self) -> dict[str, Any]:
        """Serialize for inclusion in an AuditEntry."""
        return {
            "type": "lean4_proof_certificate",
            "kernel_verified": self.kernel_verified,
            "proof_hash": self.proof_hash,
            "lean_statement": self.lean_statement,
            "lean_proof": self.lean_proof,
            "rules_formalized": self.rules_formalized,
            "model_used": self.model_used,
            "verification_time_ms": self.verification_time_ms,
        }


@dataclass(frozen=True, slots=True)
class LeanVerifyResult:
    """Result of Leanstral formal verification."""

    proved: bool
    """True if proof was generated (and kernel-verified if Lean is available)."""

    verified: bool
    """True if the verification pipeline ran. False if deps missing or errored."""

    certificate: ProofCertificate | None
    """Proof certificate, or None if verification failed."""

    counterexample: str | None
    """Why the proof failed, or None if proved."""

    lean_errors: list[str]
    """Lean kernel error messages from failed attempts (for debugging)."""

    attempts: int
    """Number of proof attempts (1 = first try, >1 = iterated with feedback)."""

    model_used: str
    """Model that generated the proof."""

    verification_time_ms: float
    """Total wall-clock time."""

    error: str | None = None
    """Error message if verification could not run at all."""


# ---------------------------------------------------------------------------
# Lean 4 templates
# ---------------------------------------------------------------------------

_LEAN_PRELUDE = """\
-- Auto-generated by acgs-lite LeanstralVerifier
-- Constitutional Hash: 608508a9bd224290
-- Do not edit manually.

"""


def _build_formalization_prompt(
    rules: list[dict[str, str]],
    context: dict[str, Any] | None = None,
) -> str:
    """Ask Leanstral to auto-formalize governance rules into Lean 4 predicates."""
    rules_block = "\n".join(f"- Rule {r['id']}: {r['text']}" for r in rules)
    context_block = ""
    if context:
        context_block = "\nContext:\n" + "\n".join(f"- {k}: {v}" for k, v in context.items())

    return f"""You are a Lean 4 formalization expert. Convert these governance rules
into Lean 4 predicates that can be used in theorem statements.

Rules:
{rules_block}
{context_block}

Output a JSON object mapping rule_id to its Lean 4 predicate definition.
Each predicate should be a `def` or `abbrev` that takes an action context
and returns `Prop`. Use simple types — `String`, `Bool`, `Nat` for now.

Example output:
```json
{{
  "prelude": "structure ActionCtx where\\n  agentRole : String\\n  targetRole : String\\n  action : String",
  "predicates": {{
    "MACI-1": "def maci1_satisfied (ctx : ActionCtx) : Prop :=\\n  ctx.agentRole ≠ \\"validator\\" ∨ ctx.action ≠ \\"validate_own\\""
  }}
}}
```

Output ONLY valid JSON, no markdown fences."""


def _build_proof_prompt(
    action: str,
    lean_source: str,
    theorem_statement: str,
    previous_errors: list[str] | None = None,
) -> str:
    """Ask Leanstral to generate a proof for the formalized theorem."""
    error_block = ""
    if previous_errors:
        error_block = "\n\nPrevious attempt failed with these Lean errors:\n"
        error_block += "\n".join(f"  {e}" for e in previous_errors[-3:])
        error_block += "\n\nFix the proof to address these errors."

    return f"""You are a Lean 4 proof engineer. Given this Lean source and theorem,
generate a proof.

```lean
{lean_source}

{theorem_statement}
```
{error_block}

Output ONLY the proof body (the `by` tactic block or term-mode proof).
No markdown fences, no explanation. Just the Lean 4 proof."""


# ---------------------------------------------------------------------------
# Lean kernel interaction
# ---------------------------------------------------------------------------


def _run_lean_check(lean_source: str, timeout_s: int = _LEAN_TIMEOUT_S) -> tuple[bool, list[str]]:
    """Run the Lean 4 kernel on source code. Returns (success, errors).

    This is the TRUST BOUNDARY. If this returns True, the proof is
    machine-verified — not LLM-generated-and-hoped-for.
    """
    if not LEAN_AVAILABLE:
        return False, ["lean not installed — proof not kernel-verified"]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".lean", delete=False) as f:
        f.write(lean_source)
        f.flush()
        lean_file = Path(f.name)

    try:
        result = subprocess.run(
            ["lean", str(lean_file)],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        errors = []
        if result.returncode != 0:
            # Extract error lines
            for line in result.stderr.splitlines():
                if "error" in line.lower() or ":" in line:
                    errors.append(line.strip())
            if not errors and result.stderr.strip():
                errors.append(result.stderr.strip()[:500])
        return result.returncode == 0, errors
    except subprocess.TimeoutExpired:
        return False, [f"Lean kernel timed out after {timeout_s}s"]
    except Exception as exc:
        return False, [f"Lean execution error: {exc}"]
    finally:
        lean_file.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_json_response(raw: str | None) -> dict[str, Any]:
    """Extract JSON from model response, handling markdown fences."""
    if not raw:
        return {}

    text = raw.strip()
    if text.startswith("```"):
        first_newline = text.index("\n") if "\n" in text else len(text)
        text = text[first_newline + 1 :]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].rstrip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        _log.warning("Failed to parse Leanstral response as JSON")
        return {}


# ---------------------------------------------------------------------------
# Main verifier
# ---------------------------------------------------------------------------


class LeanstralVerifier:
    """Formal verification of constitutional rules via Leanstral + Lean 4 kernel.

    Two-phase architecture:
    1. Leanstral (LLM) auto-formalizes rules and generates proof attempts
    2. Lean kernel (compiler) type-checks the proof (trust boundary)

    If Lean is not installed, proofs are generated but NOT kernel-verified.
    The result will clearly indicate `kernel_verified=False`.

    Args:
        api_key: Mistral API key. Falls back to MISTRAL_API_KEY env var.
        model: Model to use. Defaults to 'leanstral', falls back to 'codestral-latest'.
        max_attempts: Max proof generation attempts with feedback loop.
        lean_timeout_s: Timeout for Lean kernel verification.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_attempts: int = _MAX_PROOF_ATTEMPTS,
        lean_timeout_s: int = _LEAN_TIMEOUT_S,
    ) -> None:
        self._api_key = api_key
        self._model = model or _LEANSTRAL_MODEL
        self._max_attempts = max_attempts
        self._lean_timeout_s = lean_timeout_s
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy-init the Mistral client."""
        if self._client is not None:
            return self._client

        if not MISTRAL_AVAILABLE:
            raise ImportError(
                "mistralai package not installed. Install with: pip install acgs-lite[mistral]"
            )

        import os

        api_key = self._api_key or os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            raise ValueError(
                "MISTRAL_API_KEY not configured. "
                "Pass api_key= or set MISTRAL_API_KEY environment variable."
            )

        self._client = Mistral(api_key=api_key)
        return self._client

    @property
    def available(self) -> bool:
        """True if mistralai is installed."""
        return MISTRAL_AVAILABLE

    @property
    def kernel_available(self) -> bool:
        """True if Lean 4 kernel is installed for proof verification."""
        return LEAN_AVAILABLE

    def _chat(self, system: str, user: str) -> str | None:
        """Send a chat completion request to Leanstral."""
        client = self._get_client()
        response = client.chat.complete(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=_MAX_TOKENS,
            temperature=0.0,
        )
        return response.choices[0].message.content

    def _formalize_rules(
        self,
        rules: list[dict[str, str]],
        context: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, str]]:
        """Auto-formalize governance rules into Lean 4 predicates.

        Returns (lean_prelude_source, {rule_id: predicate_source}).
        """
        prompt = _build_formalization_prompt(rules, context)
        raw = self._chat(
            system=(
                "You are a Lean 4 formalization expert specializing in "
                "AI governance policy. Output valid JSON only."
            ),
            user=prompt,
        )

        data = _parse_json_response(raw)
        prelude = data.get("prelude", "-- no prelude generated")
        predicates = data.get("predicates", {})

        # Build Lean source
        source = _LEAN_PRELUDE + prelude + "\n\n"
        for rule_id, pred in predicates.items():
            source += f"-- Rule {rule_id}\n{pred}\n\n"

        return source, predicates

    def _generate_and_verify_proof(
        self,
        action: str,
        lean_source: str,
        theorem_statement: str,
    ) -> tuple[bool, str | None, list[str], int]:
        """Iterative proof generation with Lean kernel feedback.

        Returns (proved, proof_body, all_errors, attempts).
        """
        all_errors: list[str] = []
        proof_body: str | None = None

        for attempt in range(1, self._max_attempts + 1):
            # Generate proof
            prompt = _build_proof_prompt(
                action,
                lean_source,
                theorem_statement,
                previous_errors=all_errors if attempt > 1 else None,
            )
            raw_proof = self._chat(
                system=(
                    "You are a Lean 4 proof engineer. You write correct, "
                    "kernel-checkable proofs. Output only Lean 4 code."
                ),
                user=prompt,
            )

            if not raw_proof:
                all_errors.append(f"Attempt {attempt}: empty response from model")
                continue

            # Clean up the proof
            proof_body = raw_proof.strip()
            if proof_body.startswith("```"):
                lines = proof_body.split("\n")
                proof_body = "\n".join(lines[1:])
                if proof_body.rstrip().endswith("```"):
                    proof_body = proof_body.rstrip()[:-3].rstrip()

            # Assemble full source with proof
            full_source = lean_source + "\n" + theorem_statement + " := " + proof_body + "\n"

            # Verify with Lean kernel (TRUST BOUNDARY)
            if LEAN_AVAILABLE:
                ok, errors = _run_lean_check(full_source, self._lean_timeout_s)
                if ok:
                    return True, proof_body, all_errors, attempt
                all_errors.extend(errors)
                _log.info(
                    "Lean proof attempt %d/%d failed: %s",
                    attempt,
                    self._max_attempts,
                    errors[:2],
                )
            else:
                # No kernel — accept the generated proof but mark as unverified
                _log.info("Lean not installed — proof generated but not kernel-verified")
                return True, proof_body, ["lean not installed"], attempt

        return False, proof_body, all_errors, self._max_attempts

    def verify(
        self,
        action: str,
        rules: list[dict[str, str]],
        context: dict[str, Any] | None = None,
    ) -> LeanVerifyResult:
        """Verify an action against constitutional rules using Lean 4 proofs.

        Pipeline:
        1. Auto-formalize rules into Lean 4 predicates (via Leanstral)
        2. Generate theorem statement
        3. Generate proof (via Leanstral)
        4. Verify proof (via Lean kernel) — iterate on failure
        5. Package as ProofCertificate

        Args:
            action: The agent action to verify.
            rules: List of rule dicts with 'id' and 'text' keys.
            context: Optional context dict (agent role, environment, etc.).

        Returns:
            LeanVerifyResult with proof certificate if successful.
        """
        if not MISTRAL_AVAILABLE:
            return LeanVerifyResult(
                proved=False,
                verified=False,
                certificate=None,
                counterexample=None,
                lean_errors=[],
                attempts=0,
                model_used=self._model,
                verification_time_ms=0.0,
                error="mistralai not installed",
            )

        start = time.perf_counter()

        try:
            # Phase 1: Auto-formalize rules
            lean_source, predicates = self._formalize_rules(rules, context)

            if not predicates:
                elapsed = (time.perf_counter() - start) * 1000
                return LeanVerifyResult(
                    proved=False,
                    verified=True,
                    certificate=None,
                    counterexample="Failed to formalize rules into Lean 4",
                    lean_errors=[],
                    attempts=0,
                    model_used=self._model,
                    verification_time_ms=elapsed,
                )

            # Phase 2: Build theorem statement
            rule_ids = list(predicates.keys())
            conj_parts = " ∧ ".join(f"{_lean_safe_name(rid)}_satisfied ctx" for rid in rule_ids)
            theorem = (
                f"theorem action_compliant (ctx : ActionCtx) "
                f'(h_action : ctx.action = "{_lean_escape(action)}") : '
                f"{conj_parts}"
            )

            # Phase 3-4: Generate proof with kernel feedback loop
            proved, proof_body, errors, attempts = self._generate_and_verify_proof(
                action,
                lean_source,
                theorem,
            )

            elapsed = (time.perf_counter() - start) * 1000

            if proved and proof_body:
                full_source = lean_source + "\n" + theorem + " := " + proof_body
                certificate = ProofCertificate(
                    lean_statement=theorem,
                    lean_proof=proof_body,
                    kernel_verified=LEAN_AVAILABLE and "lean not installed" not in " ".join(errors),
                    rules_formalized=predicates,
                    proof_hash=hashlib.sha256(full_source.encode()).hexdigest(),
                    model_used=self._model,
                    verification_time_ms=elapsed,
                )
                return LeanVerifyResult(
                    proved=True,
                    verified=True,
                    certificate=certificate,
                    counterexample=None,
                    lean_errors=errors,
                    attempts=attempts,
                    model_used=self._model,
                    verification_time_ms=elapsed,
                )
            else:
                return LeanVerifyResult(
                    proved=False,
                    verified=True,
                    certificate=None,
                    counterexample=f"Proof failed after {attempts} attempts",
                    lean_errors=errors,
                    attempts=attempts,
                    model_used=self._model,
                    verification_time_ms=elapsed,
                )

        except (ImportError, ValueError) as exc:
            elapsed = (time.perf_counter() - start) * 1000
            return LeanVerifyResult(
                proved=False,
                verified=False,
                certificate=None,
                counterexample=None,
                lean_errors=[],
                attempts=0,
                model_used=self._model,
                verification_time_ms=elapsed,
                error=str(exc),
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            _log.warning("Leanstral verification error: %s", exc)
            return LeanVerifyResult(
                proved=False,
                verified=False,
                certificate=None,
                counterexample=None,
                lean_errors=[str(exc)],
                attempts=0,
                model_used=self._model,
                verification_time_ms=elapsed,
                error=f"{type(exc).__name__}: {exc}",
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lean_safe_name(rule_id: str) -> str:
    """Convert a rule ID to a valid Lean 4 identifier."""
    return rule_id.lower().replace("-", "_").replace(" ", "_")


def _lean_escape(s: str) -> str:
    """Escape a string for Lean 4 string literals."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
