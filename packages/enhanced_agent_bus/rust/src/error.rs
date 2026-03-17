//! ACGS-2 Enhanced Agent Bus - Error Types
//! Constitutional Hash: cdd01ef066bc6cf2
//!
//! Structured error handling with proper categorization for governance operations.

use thiserror::Error;

use crate::crypto::CONSTITUTIONAL_HASH;

/// Primary error type for ACGS-2 governance operations
#[derive(Error, Debug)]
pub enum AcgsError {
    /// Constitutional validation failures - always fail-closed
    #[error("Constitutional violation: {message} [hash: {hash}]")]
    ConstitutionalViolation {
        message: String,
        hash: String,
        #[source]
        source: Option<Box<dyn std::error::Error + Send + Sync>>,
    },

    /// Hash mismatch between expected and actual constitutional hash
    #[error("Constitutional hash mismatch: expected {expected}, got {actual}")]
    HashMismatch { expected: String, actual: String },

    /// Policy evaluation failures
    #[error("Policy evaluation failed: {0}")]
    PolicyEvaluation(String),

    /// OPA client errors
    #[error("OPA error: {message} (fail_closed: {fail_closed})")]
    OpaError {
        message: String,
        fail_closed: bool,
        #[source]
        source: Option<Box<dyn std::error::Error + Send + Sync>>,
    },

    /// Cryptographic operation failures
    #[error("Cryptographic error: {0}")]
    CryptoError(String),

    /// Signature verification failures
    #[error("Signature verification failed: {0}")]
    SignatureVerification(String),

    /// Message validation errors
    #[error("Message validation failed: {0}")]
    MessageValidation(String),

    /// Prompt injection detected
    #[error("Prompt injection detected: pattern '{pattern}'")]
    PromptInjection { pattern: String, content_hash: String },

    /// Serialization/deserialization errors
    #[error("Serialization error: {0}")]
    Serialization(#[from] serde_json::Error),

    /// Network/HTTP errors
    #[error("Network error: {0}")]
    Network(String),

    /// Cache errors
    #[error("Cache error: {0}")]
    Cache(String),

    /// Timeout errors
    #[error("Operation timeout: {operation} after {timeout_ms}ms")]
    Timeout { operation: String, timeout_ms: u64 },

    /// Rate limiting
    #[error("Rate limit exceeded for agent {agent_id}: {requests}/{limit} in window")]
    RateLimitExceeded {
        agent_id: String,
        requests: u64,
        limit: u64,
    },

    /// Internal error with optional source
    #[error("Internal error: {0}")]
    Internal(String),
}

impl AcgsError {
    /// Create a constitutional violation error
    pub fn constitutional(message: impl Into<String>) -> Self {
        Self::ConstitutionalViolation {
            message: message.into(),
            hash: CONSTITUTIONAL_HASH.to_string(),
            source: None,
        }
    }

    /// Create a hash mismatch error
    pub fn hash_mismatch(actual: impl Into<String>) -> Self {
        Self::HashMismatch {
            expected: CONSTITUTIONAL_HASH.to_string(),
            actual: actual.into(),
        }
    }

    /// Create an OPA error with fail-closed semantics
    pub fn opa_fail_closed(message: impl Into<String>) -> Self {
        Self::OpaError {
            message: message.into(),
            fail_closed: true,
            source: None,
        }
    }

    /// Create an OPA error with fail-open semantics
    pub fn opa_fail_open(message: impl Into<String>) -> Self {
        Self::OpaError {
            message: message.into(),
            fail_closed: false,
            source: None,
        }
    }

    /// Returns true if this is a critical security error requiring fail-closed behavior
    pub fn is_critical(&self) -> bool {
        matches!(
            self,
            Self::ConstitutionalViolation { .. }
                | Self::HashMismatch { .. }
                | Self::PromptInjection { .. }
                | Self::SignatureVerification(_)
        )
    }

    /// Returns true if the operation should be retried
    pub fn is_retryable(&self) -> bool {
        matches!(
            self,
            Self::Network(_) | Self::Timeout { .. } | Self::Cache(_)
        )
    }

    /// Get error code for structured logging
    pub fn code(&self) -> &'static str {
        match self {
            Self::ConstitutionalViolation { .. } => "ACGS_E001",
            Self::HashMismatch { .. } => "ACGS_E002",
            Self::PolicyEvaluation(_) => "ACGS_E003",
            Self::OpaError { .. } => "ACGS_E004",
            Self::CryptoError(_) => "ACGS_E005",
            Self::SignatureVerification(_) => "ACGS_E006",
            Self::MessageValidation(_) => "ACGS_E007",
            Self::PromptInjection { .. } => "ACGS_E008",
            Self::Serialization(_) => "ACGS_E009",
            Self::Network(_) => "ACGS_E010",
            Self::Cache(_) => "ACGS_E011",
            Self::Timeout { .. } => "ACGS_E012",
            Self::RateLimitExceeded { .. } => "ACGS_E013",
            Self::Internal(_) => "ACGS_E999",
        }
    }
}

/// Result type alias for ACGS operations
pub type AcgsResult<T> = std::result::Result<T, AcgsError>;

/// Extension trait for adding constitutional context to errors
pub trait ConstitutionalContext<T> {
    /// Add constitutional context to an error
    fn with_constitutional_context(self, message: &str) -> AcgsResult<T>;
}

impl<T, E: std::error::Error + Send + Sync + 'static> ConstitutionalContext<T>
    for std::result::Result<T, E>
{
    fn with_constitutional_context(self, message: &str) -> AcgsResult<T> {
        self.map_err(|e| AcgsError::ConstitutionalViolation {
            message: message.to_string(),
            hash: CONSTITUTIONAL_HASH.to_string(),
            source: Some(Box::new(e)),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_error_codes() {
        let err = AcgsError::hash_mismatch("wrong_hash");
        assert_eq!(err.code(), "ACGS_E002");
        assert!(err.is_critical());
        assert!(!err.is_retryable());
    }

    #[test]
    fn test_retryable_errors() {
        let err = AcgsError::Network("connection refused".to_string());
        assert!(!err.is_critical());
        assert!(err.is_retryable());
    }

    #[test]
    fn test_constitutional_violation() {
        let err = AcgsError::constitutional("Invalid governance action");
        assert!(err.is_critical());
        assert!(err.to_string().contains(CONSTITUTIONAL_HASH));
    }
}
