/// acgs_lite_rust — PyO3 native extension for the ACGS-2 governance engine.
///
/// Provides high-performance governance validation by implementing the core
/// algorithm in Rust: Aho-Corasick keyword scan, anchor-dispatch, regex
/// pattern matching, context processing, and constitutional hash verification.
///
/// The Python `engine.py` calls into this crate via PyO3. When the Rust
/// extension is not available, Python falls back to its own implementation.
///
/// Constitutional Hash: 608508a9bd224290

pub mod context;
pub mod hash;
pub mod result;
pub mod severity;
pub mod validator;
pub mod verbs;

use pyo3::prelude::*;

pub use severity::{ALLOW, DENY, DENY_CRITICAL};
pub use validator::GovernanceValidator;

#[pymodule]
fn acgs_lite_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<GovernanceValidator>()?;
    m.add("ALLOW", ALLOW)?;
    m.add("DENY_CRITICAL", DENY_CRITICAL)?;
    m.add("DENY", DENY)?;
    Ok(())
}
