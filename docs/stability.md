# API Stability Tiers

`acgs-lite` classifies every public export into one of three stability tiers.
Use `acgs_lite.stability(name)` or the `API_STABILITY` dict to check a symbol's
tier at runtime.

## Tiers

### stable

Covered by semantic versioning. Breaking changes only happen on major version bumps
(e.g., v2 → v3). Safe to depend on in production without version pinning beyond
the major version.

**Examples:** `Constitution`, `GovernanceEngine`, `GovernedAgent`, `MACIEnforcer`,
`AuditLog`, `ConstitutionalViolationError`.

### beta

Feature-complete, but signatures or behavior may shift in minor releases.
Pin to at least `~= 2.x` if you depend on these. We publish migration notes
in the CHANGELOG before making breaking changes.

**Examples:** `ConstitutionBundle`, `ConstitutionLifecycle`, `BundleStore`,
`PostgresBundleStore`, `SQLiteBundleStore`, `SpotCheckAuditor`, `TrustScoreManager`.

### experimental

May change or be removed without a deprecation cycle. Treat these as previews.
Useful for exploration, but do not build production features directly on them
without expecting to absorb churn.

**Examples:** `Z3VerificationGate`, `LeanstralVerifier`, `RedisGovernanceStateBackend`,
all `acgs_lite.openshell.*` symbols.

## Checking at runtime

```python
import acgs_lite

# Check a specific symbol
print(acgs_lite.stability("GovernanceEngine"))    # "stable"
print(acgs_lite.stability("PostgresBundleStore")) # "beta"
print(acgs_lite.stability("Z3VerificationGate"))  # "experimental"

# Inspect the full map
from acgs_lite import API_STABILITY
stable_symbols = [k for k, v in API_STABILITY.items() if v == "stable"]
```

## Unclassified symbols

Anything not in `API_STABILITY` defaults to `"experimental"`. Use `stability(name)`
to check — it returns `"experimental"` for unknown names rather than raising.

## Optional extras and stability

Symbols backed by optional extras (`z3-solver`, `psycopg`, etc.) are at most
`"experimental"` or `"beta"`. If the extra is not installed, importing them
raises `ImportError` with an install hint rather than crashing the whole module.

## Engine import compatibility

The public `acgs_lite.engine` package keeps legacy imports stable even though the
implementation is split across focused modules such as `engine.core`,
`engine.models`, `engine.audit_runtime`, and `engine.batch`.

```python
from acgs_lite.engine import GovernanceEngine, ValidationResult
```

Those imports remain supported. Reach into deeper engine submodules only when
you specifically need implementation details or narrower test seams.
