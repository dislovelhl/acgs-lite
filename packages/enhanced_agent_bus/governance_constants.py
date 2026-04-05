"""
ACGS-2 Enhanced Agent Bus — Governance Constants

Central registry for magic numbers used across the governance pipeline.
Consolidating these prevents silent divergence between modules that
share the same logical threshold.

Constitutional Hash: 608508a9bd224290
"""

# ---------------------------------------------------------------------------
# Impact Scoring — controls deliberation/fast-lane routing
# ---------------------------------------------------------------------------

# Messages at or above this score are routed to the deliberation layer
IMPACT_DELIBERATION_THRESHOLD: float = 0.8

# Minimum final score for critical-priority messages (forces deliberation)
IMPACT_CRITICAL_FLOOR: float = 0.95

# Minimum final score when semantic analysis returns high confidence (>=0.9)
IMPACT_HIGH_SEMANTIC_FLOOR: float = 0.75

# Scoring formula weights (must sum to 1.0)
IMPACT_WEIGHT_SEMANTIC: float = 0.6
IMPACT_WEIGHT_PERMISSION: float = 0.1
IMPACT_WEIGHT_VOLUME: float = 0.05
IMPACT_WEIGHT_CONTEXT: float = 0.2
IMPACT_WEIGHT_DRIFT: float = 0.05

# Pro2Guard DTMC trajectory risk — 6th scoring dimension (Sprint 3).
# Additive bias applied on top of the 5-weight formula above.
# Set to 0.0 by default so existing behaviour is preserved when no
# DTMCLearner is wired in; operators can raise it (e.g. 0.15) once the
# DTMC model has been trained on sufficient trajectory data.
IMPACT_WEIGHT_TRAJECTORY: float = 0.0

# ---------------------------------------------------------------------------
# Deliberation / Consensus
# ---------------------------------------------------------------------------

# Default minimum votes required for a consensus decision
DEFAULT_REQUIRED_VOTES: int = 3

# Quorum threshold (fraction of agreeing votes to total)
DEFAULT_CONSENSUS_THRESHOLD: float = 0.66

# Default timeout for a deliberation session (seconds)
DEFAULT_DELIBERATION_TIMEOUT_SECONDS: int = 300

# ---------------------------------------------------------------------------
# MACI Role Confidence Thresholds
# ---------------------------------------------------------------------------

# Executive Agent — proposes governance decisions
MACI_EXECUTIVE_CONFIDENCE: float = 0.8

# Constitutional Interpreter — interprets rules
MACI_INTERPRETER_CONFIDENCE: float = 0.9

# Constitutional Validator — validates compliance
MACI_VALIDATOR_CONFIDENCE: float = 0.85

# ---------------------------------------------------------------------------
# Cache Sizes & TTLs
# ---------------------------------------------------------------------------

# Standard in-memory LRU cache size (enterprise-scale default)
DEFAULT_LRU_CACHE_SIZE: int = 10_000

# Standard cache TTL in seconds (5 minutes)
DEFAULT_CACHE_TTL_SECONDS: int = 300

# ---------------------------------------------------------------------------
# Circuit Breaker Defaults
# ---------------------------------------------------------------------------

# Number of consecutive failures before the circuit opens
DEFAULT_CB_FAIL_MAX: int = 5

# Seconds before attempting to half-open the circuit
DEFAULT_CB_RESET_TIMEOUT: int = 30

# Maximum retries for buffered messages
DEFAULT_MAX_RETRIES: int = 5

# ---------------------------------------------------------------------------
# Adaptive Governance Engine
# ---------------------------------------------------------------------------

# Learning window for feedback analysis (seconds)
GOVERNANCE_FEEDBACK_WINDOW_SECONDS: int = 3600

# Target accuracy for constitutional compliance
GOVERNANCE_PERFORMANCE_TARGET: float = 0.95

# Risk score thresholds for impact level classification
GOVERNANCE_RISK_CRITICAL: float = 0.9
GOVERNANCE_RISK_HIGH: float = 0.7
GOVERNANCE_RISK_MEDIUM: float = 0.4
GOVERNANCE_RISK_LOW: float = 0.2

# Exponential moving average weight for response time updates
GOVERNANCE_EMA_ALPHA: float = 0.1

# Maximum decision history length before trimming
GOVERNANCE_HISTORY_MAX: int = 100

# Trim target for decision history (keep most recent N)
GOVERNANCE_HISTORY_TRIM: int = 50

# Minimum compliance score for compliant classification
GOVERNANCE_COMPLIANCE_THRESHOLD: float = 0.8

# Background learning cycle interval (seconds)
GOVERNANCE_LEARNING_CYCLE_SECONDS: int = 300

# Backoff sleep on learning loop errors (seconds)
GOVERNANCE_BACKOFF_SECONDS: int = 60

# Maximum trend data points to retain
GOVERNANCE_MAX_TREND_LENGTH: int = 100

# Retrain trigger: minimum history before checking modulus
GOVERNANCE_RETRAIN_HISTORY_MIN: int = 1000

# Retrain trigger: check every N decisions
GOVERNANCE_RETRAIN_CHECK_MODULUS: int = 500

# Fallback confidence when governance evaluation fails
GOVERNANCE_FALLBACK_CONFIDENCE: float = 0.9

# Default recommended threshold for governance decisions
GOVERNANCE_RECOMMENDED_THRESHOLD: float = 0.8

# ---------------------------------------------------------------------------
# Rollback Engine
# ---------------------------------------------------------------------------

# Monitoring interval for automatic rollback detection (seconds)
ROLLBACK_MONITORING_INTERVAL_SECONDS: int = 300

# Minimum confidence score for auto-approved rollbacks
ROLLBACK_MIN_CONFIDENCE: float = 0.7

# HTTP client timeout for rollback operations (seconds)
ROLLBACK_HTTP_TIMEOUT_SECONDS: float = 30.0

# Timeout for degradation detection step (seconds)
ROLLBACK_DETECT_TIMEOUT_SECONDS: int = 60

# Timeout for standard rollback saga steps (seconds)
ROLLBACK_STEP_TIMEOUT_SECONDS: int = 30

# ---------------------------------------------------------------------------
# MACI Verifier
# ---------------------------------------------------------------------------

# Base risk score for executive decision assessment
VERIFIER_BASE_RISK_SCORE: float = 0.2

# Risk increments for context flags
VERIFIER_RISK_SENSITIVE_DATA: float = 0.3
VERIFIER_RISK_CROSS_JURISDICTION: float = 0.2
VERIFIER_RISK_HIGH_IMPACT: float = 0.2
VERIFIER_RISK_HUMAN_APPROVAL: float = 0.1

# Default confidence threshold for judicial agent
VERIFIER_JUDICIAL_CONFIDENCE_THRESHOLD: float = 0.7

# Legislative confidence formula: min(cap, base + count * increment)
VERIFIER_LEGISLATIVE_CONFIDENCE_CAP: float = 0.95
VERIFIER_LEGISLATIVE_CONFIDENCE_BASE: float = 0.6
VERIFIER_LEGISLATIVE_CONFIDENCE_PER_RULE: float = 0.1

# ---------------------------------------------------------------------------
# LLM Circuit Breaker Defaults
# ---------------------------------------------------------------------------

# Standard defaults for most providers
LLM_CB_DEFAULT_FAILURE_THRESHOLD: int = 5
LLM_CB_DEFAULT_TIMEOUT_SECONDS: float = 30.0
LLM_CB_DEFAULT_HALF_OPEN_REQUESTS: int = 3
LLM_CB_DEFAULT_FALLBACK_TTL_SECONDS: int = 60

# ---------------------------------------------------------------------------
# Saga Orchestration
# ---------------------------------------------------------------------------

# TTL for saga state in Redis (30 days)
SAGA_DEFAULT_TTL_SECONDS: int = 60 * 60 * 24 * 30
