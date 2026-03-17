/// Validation result types for the governance engine.
///
/// These are internal Rust types used within the crate. They are converted
/// to Python-compatible tuples at the FFI boundary in the validator.
///
/// Constitutional Hash: cdd01ef066bc6cf2

use crate::severity::Severity;

/// A single rule violation detected during validation.
#[derive(Debug, Clone)]
pub struct RustViolation {
    pub rule_idx: usize,
    pub rule_id: String,
    pub rule_text: String,
    pub severity: Severity,
    pub matched_content: String,
    pub category: String,
}

/// The decision made by the validator.
#[derive(Debug)]
pub enum RustDecision {
    /// No violations found — action is allowed.
    Allow,
    /// A CRITICAL violation found in strict mode — must raise immediately.
    DenyCritical { rule_idx: usize },
    /// Non-critical violations found — action may be escalated or denied.
    Deny {
        violations: Vec<RustViolation>,
        has_blocking: bool,
    },
}

impl RustDecision {
    /// Convert to the legacy (decision_code, data) tuple format for backward compat.
    pub fn to_legacy_tuple(&self) -> (i32, i64) {
        match self {
            RustDecision::Allow => (crate::severity::ALLOW, 0),
            RustDecision::DenyCritical { rule_idx } => {
                (crate::severity::DENY_CRITICAL, *rule_idx as i64)
            }
            RustDecision::Deny { violations, .. } => {
                let mut bitmask: u64 = 0;
                for v in violations {
                    bitmask |= 1u64 << v.rule_idx;
                }
                (crate::severity::DENY, bitmask as i64)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::severity;

    #[test]
    fn test_allow_legacy() {
        let d = RustDecision::Allow;
        assert_eq!(d.to_legacy_tuple(), (severity::ALLOW, 0));
    }

    #[test]
    fn test_deny_critical_legacy() {
        let d = RustDecision::DenyCritical { rule_idx: 3 };
        assert_eq!(d.to_legacy_tuple(), (severity::DENY_CRITICAL, 3));
    }

    #[test]
    fn test_deny_bitmask() {
        let d = RustDecision::Deny {
            violations: vec![
                RustViolation {
                    rule_idx: 0,
                    rule_id: "R1".into(),
                    rule_text: "test".into(),
                    severity: Severity::Medium,
                    matched_content: "x".into(),
                    category: "c".into(),
                },
                RustViolation {
                    rule_idx: 2,
                    rule_id: "R3".into(),
                    rule_text: "test".into(),
                    severity: Severity::High,
                    matched_content: "y".into(),
                    category: "c".into(),
                },
            ],
            has_blocking: true,
        };
        let (code, mask) = d.to_legacy_tuple();
        assert_eq!(code, severity::DENY);
        assert_eq!(mask, 0b101); // bits 0 and 2
    }
}
