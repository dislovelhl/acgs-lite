/// Severity levels for governance rules.
///
/// Mirrors `constitution.Severity` in Python.
/// Constitutional Hash: cdd01ef066bc6cf2

/// Decision codes returned by the validator.
pub const ALLOW: i32 = 0;
pub const DENY_CRITICAL: i32 = 1;
pub const DENY: i32 = 2;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Severity {
    Critical,
    High,
    Medium,
    Low,
}

impl Severity {
    /// Parse from the Python severity string value.
    pub fn from_str(s: &str) -> Self {
        match s {
            "critical" => Severity::Critical,
            "high" => Severity::High,
            "medium" => Severity::Medium,
            "low" => Severity::Low,
            _ => Severity::Medium, // safe default
        }
    }

    /// Whether this severity blocks action execution.
    pub fn blocks(&self) -> bool {
        matches!(self, Severity::Critical | Severity::High)
    }

    /// Return the Python string value.
    pub fn as_str(&self) -> &'static str {
        match self {
            Severity::Critical => "critical",
            Severity::High => "high",
            Severity::Medium => "medium",
            Severity::Low => "low",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_from_str() {
        assert_eq!(Severity::from_str("critical"), Severity::Critical);
        assert_eq!(Severity::from_str("high"), Severity::High);
        assert_eq!(Severity::from_str("medium"), Severity::Medium);
        assert_eq!(Severity::from_str("low"), Severity::Low);
        assert_eq!(Severity::from_str("unknown"), Severity::Medium);
    }

    #[test]
    fn test_blocks() {
        assert!(Severity::Critical.blocks());
        assert!(Severity::High.blocks());
        assert!(!Severity::Medium.blocks());
        assert!(!Severity::Low.blocks());
    }
}
