/// acgs-validator-core — Pure Rust governance validation engine.
///
/// No FFI dependencies. Targets: native, WASM, PyO3 wrapper.
///
/// Provides high-performance governance validation: Aho-Corasick keyword scan,
/// anchor-dispatch, regex pattern matching, context processing, and
/// constitutional hash verification.
///
/// Constitutional Hash: cdd01ef066bc6cf2

pub mod context;
pub mod hash;
pub mod result;
pub mod severity;
pub mod validator;
pub mod verbs;

pub use context::ContextRule;
pub use hash::compute_constitutional_hash;
pub use result::{Decision, ValidationResult, Violation, ViolationRecord};
pub use severity::{Severity, ALLOW, DENY, DENY_CRITICAL};
pub use validator::{BuildError, GovernanceValidator, ValidatorConfig};
