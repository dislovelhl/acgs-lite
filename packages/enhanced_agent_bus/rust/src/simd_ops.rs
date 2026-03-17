//! ACGS-2 Enhanced Agent Bus - SIMD Operations
//! Constitutional Hash: cdd01ef066bc6cf2
//!
//! Vectorized operations for high-performance numeric processing.
//! Uses multiversion for automatic SIMD dispatch across CPU architectures.

use multiversion::multiversion;


/// Error type for SIMD operations
#[derive(Debug, Clone, PartialEq)]
pub enum SimdError {
    LengthMismatch { expected: usize, actual: usize },
    OutputTooSmall { needed: usize, available: usize },
    EmptyInput,
}

impl std::fmt::Display for SimdError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            SimdError::LengthMismatch { expected, actual } => {
                write!(f, "Length mismatch: expected {}, got {}", expected, actual)
            }
            SimdError::OutputTooSmall { needed, available } => {
                write!(
                    f,
                    "Output buffer too small: need {}, have {}",
                    needed, available
                )
            }
            SimdError::EmptyInput => write!(f, "Empty input not allowed"),
        }
    }
}

impl std::error::Error for SimdError {}

/// Result type for SIMD operations
pub type Result<T> = std::result::Result<T, SimdError>;

/// Validate input lengths match and output is sufficient
#[inline]
fn validate_lengths(a_len: usize, b_len: usize, out_len: usize) -> Result<()> {
    if a_len == 0 {
        return Err(SimdError::EmptyInput);
    }
    if a_len != b_len {
        return Err(SimdError::LengthMismatch {
            expected: a_len,
            actual: b_len,
        });
    }
    if out_len < a_len {
        return Err(SimdError::OutputTooSmall {
            needed: a_len,
            available: out_len,
        });
    }
    Ok(())
}

/// SIMD-accelerated vector addition
#[multiversion(targets("x86_64+avx2", "x86_64+avx", "x86_64+sse4.1", "x86_64+sse2", "aarch64+neon"))]
pub fn vec_add_simd(a: &[f32], b: &[f32], out: &mut [f32]) -> Result<()> {
    validate_lengths(a.len(), b.len(), out.len())?;

    for i in 0..a.len() {
        out[i] = a[i] + b[i];
    }
    Ok(())
}

/// SIMD-accelerated vector subtraction
#[multiversion(targets("x86_64+avx2", "x86_64+avx", "x86_64+sse4.1", "x86_64+sse2", "aarch64+neon"))]
pub fn vec_sub_simd(a: &[f32], b: &[f32], out: &mut [f32]) -> Result<()> {
    validate_lengths(a.len(), b.len(), out.len())?;

    for i in 0..a.len() {
        out[i] = a[i] - b[i];
    }
    Ok(())
}

/// SIMD-accelerated vector multiplication (element-wise)
#[multiversion(targets("x86_64+avx2", "x86_64+avx", "x86_64+sse4.1", "x86_64+sse2", "aarch64+neon"))]
pub fn vec_mul_simd(a: &[f32], b: &[f32], out: &mut [f32]) -> Result<()> {
    validate_lengths(a.len(), b.len(), out.len())?;

    for i in 0..a.len() {
        out[i] = a[i] * b[i];
    }
    Ok(())
}

/// SIMD-accelerated dot product
#[multiversion(targets("x86_64+avx2", "x86_64+avx", "x86_64+sse4.1", "x86_64+sse2", "aarch64+neon"))]
pub fn vec_dot_simd(a: &[f32], b: &[f32]) -> Result<f32> {
    if a.is_empty() {
        return Err(SimdError::EmptyInput);
    }
    if a.len() != b.len() {
        return Err(SimdError::LengthMismatch {
            expected: a.len(),
            actual: b.len(),
        });
    }

    let mut sum = 0.0f32;
    for i in 0..a.len() {
        sum += a[i] * b[i];
    }
    Ok(sum)
}

/// SIMD-accelerated vector sum
#[multiversion(targets("x86_64+avx2", "x86_64+avx", "x86_64+sse4.1", "x86_64+sse2", "aarch64+neon"))]
pub fn vec_sum_simd(a: &[f32]) -> Result<f32> {
    if a.is_empty() {
        return Err(SimdError::EmptyInput);
    }

    let mut sum = 0.0f32;
    for &val in a {
        sum += val;
    }
    Ok(sum)
}

/// SIMD-accelerated vector max
#[multiversion(targets("x86_64+avx2", "x86_64+avx", "x86_64+sse4.1", "x86_64+sse2", "aarch64+neon"))]
pub fn vec_max_simd(a: &[f32]) -> Result<f32> {
    if a.is_empty() {
        return Err(SimdError::EmptyInput);
    }

    let mut max = f32::NEG_INFINITY;
    for &val in a {
        if val > max {
            max = val;
        }
    }
    Ok(max)
}

/// SIMD-accelerated vector min
#[multiversion(targets("x86_64+avx2", "x86_64+avx", "x86_64+sse4.1", "x86_64+sse2", "aarch64+neon"))]
pub fn vec_min_simd(a: &[f32]) -> Result<f32> {
    if a.is_empty() {
        return Err(SimdError::EmptyInput);
    }

    let mut min = f32::INFINITY;
    for &val in a {
        if val < min {
            min = val;
        }
    }
    Ok(min)
}

/// SIMD-accelerated L2 norm (Euclidean length)
#[multiversion(targets("x86_64+avx2", "x86_64+avx", "x86_64+sse4.1", "x86_64+sse2", "aarch64+neon"))]
pub fn vec_l2_norm_simd(a: &[f32]) -> Result<f32> {
    if a.is_empty() {
        return Err(SimdError::EmptyInput);
    }

    let mut sum = 0.0f32;
    for &val in a {
        sum += val * val;
    }
    Ok(sum.sqrt())
}

/// SIMD-accelerated cosine similarity
#[multiversion(targets("x86_64+avx2", "x86_64+avx", "x86_64+sse4.1", "x86_64+sse2", "aarch64+neon"))]
pub fn vec_cosine_similarity_simd(a: &[f32], b: &[f32]) -> Result<f32> {
    if a.is_empty() {
        return Err(SimdError::EmptyInput);
    }
    if a.len() != b.len() {
        return Err(SimdError::LengthMismatch {
            expected: a.len(),
            actual: b.len(),
        });
    }

    let mut dot = 0.0f32;
    let mut norm_a = 0.0f32;
    let mut norm_b = 0.0f32;

    for i in 0..a.len() {
        dot += a[i] * b[i];
        norm_a += a[i] * a[i];
        norm_b += b[i] * b[i];
    }

    let denom = (norm_a.sqrt() * norm_b.sqrt()).max(1e-10);
    Ok(dot / denom)
}

/// SIMD-accelerated softmax
#[multiversion(targets("x86_64+avx2", "x86_64+avx", "x86_64+sse4.1", "x86_64+sse2", "aarch64+neon"))]
pub fn vec_softmax_simd(a: &[f32], out: &mut [f32]) -> Result<()> {
    if a.is_empty() {
        return Err(SimdError::EmptyInput);
    }
    if out.len() < a.len() {
        return Err(SimdError::OutputTooSmall {
            needed: a.len(),
            available: out.len(),
        });
    }

    // Find max for numerical stability
    let max = vec_max_simd(a)?;

    // Compute exp(x - max)
    let mut sum = 0.0f32;
    for i in 0..a.len() {
        out[i] = (a[i] - max).exp();
        sum += out[i];
    }

    // Normalize
    let sum_inv = 1.0 / sum.max(1e-10);
    for out_val in out.iter_mut().take(a.len()) {
        *out_val *= sum_inv;
    }

    Ok(())
}

/// SIMD-accelerated ReLU activation
#[multiversion(targets("x86_64+avx2", "x86_64+avx", "x86_64+sse4.1", "x86_64+sse2", "aarch64+neon"))]
pub fn vec_relu_simd(a: &[f32], out: &mut [f32]) -> Result<()> {
    if a.is_empty() {
        return Err(SimdError::EmptyInput);
    }
    if out.len() < a.len() {
        return Err(SimdError::OutputTooSmall {
            needed: a.len(),
            available: out.len(),
        });
    }

    for i in 0..a.len() {
        out[i] = a[i].max(0.0);
    }
    Ok(())
}

/// SIMD-accelerated vector normalization (in-place)
#[multiversion(targets("x86_64+avx2", "x86_64+avx", "x86_64+sse4.1", "x86_64+sse2", "aarch64+neon"))]
pub fn vec_normalize_simd(a: &mut [f32]) -> Result<()> {
    if a.is_empty() {
        return Err(SimdError::EmptyInput);
    }

    let norm = vec_l2_norm_simd(a)?;
    if norm < 1e-10 {
        return Ok(()); // Don't normalize near-zero vectors
    }

    let norm_inv = 1.0 / norm;
    for val in a.iter_mut() {
        *val *= norm_inv;
    }
    Ok(())
}

/// Scalar fallback for vector addition
pub fn vec_add_scalar(a: &[f32], b: &[f32], out: &mut [f32]) -> Result<()> {
    validate_lengths(a.len(), b.len(), out.len())?;

    for i in 0..a.len() {
        out[i] = a[i] + b[i];
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_vec_add_basic() {
        let a = [1.0, 2.0, 3.0, 4.0];
        let b = [5.0, 6.0, 7.0, 8.0];
        let mut out = [0.0; 4];

        vec_add_simd(&a, &b, &mut out).expect("Unexpected error");
        assert_eq!(out, [6.0, 8.0, 10.0, 12.0]);
    }

    #[test]
    fn test_vec_add_length_mismatch() {
        let a = [1.0, 2.0, 3.0];
        let b = [4.0, 5.0];
        let mut out = [0.0; 3];

        let result = vec_add_simd(&a, &b, &mut out);
        assert!(matches!(result, Err(SimdError::LengthMismatch { .. })));
    }

    #[test]
    fn test_vec_add_output_too_small() {
        let a = [1.0, 2.0, 3.0];
        let b = [4.0, 5.0, 6.0];
        let mut out = [0.0; 2];

        let result = vec_add_simd(&a, &b, &mut out);
        assert!(matches!(result, Err(SimdError::OutputTooSmall { .. })));
    }

    #[test]
    fn test_vec_add_empty() {
        let a: [f32; 0] = [];
        let b: [f32; 0] = [];
        let mut out: [f32; 0] = [];

        let result = vec_add_simd(&a, &b, &mut out);
        assert!(matches!(result, Err(SimdError::EmptyInput)));
    }

    #[test]
    fn test_vec_dot() {
        let a = [1.0, 2.0, 3.0, 4.0];
        let b = [5.0, 6.0, 7.0, 8.0];

        let dot = vec_dot_simd(&a, &b).expect("Unexpected error");
        assert!((dot - 70.0).abs() < 0.001);
    }

    #[test]
    fn test_vec_cosine_similarity() {
        let a = [1.0, 0.0, 0.0];
        let b = [1.0, 0.0, 0.0];

        let sim = vec_cosine_similarity_simd(&a, &b).expect("Unexpected error");
        assert!((sim - 1.0).abs() < 0.001);

        let c = [0.0, 1.0, 0.0];
        let sim2 = vec_cosine_similarity_simd(&a, &c).expect("Unexpected error");
        assert!(sim2.abs() < 0.001);
    }

    #[test]
    fn test_vec_softmax() {
        let a = [1.0, 2.0, 3.0];
        let mut out = [0.0; 3];

        vec_softmax_simd(&a, &mut out).expect("Unexpected error");

        // Sum should be 1.0
        let sum: f32 = out.iter().sum();
        assert!((sum - 1.0).abs() < 0.001);

        // Values should be in increasing order
        assert!(out[0] < out[1] && out[1] < out[2]);
    }

    #[test]
    fn test_vec_relu() {
        let a = [-1.0, 0.0, 1.0, -0.5, 2.0];
        let mut out = [0.0; 5];

        vec_relu_simd(&a, &mut out).expect("Unexpected error");
        assert_eq!(out, [0.0, 0.0, 1.0, 0.0, 2.0]);
    }

    #[test]
    fn test_vec_normalize() {
        let mut a = [3.0, 4.0];

        vec_normalize_simd(&mut a).expect("Unexpected error");

        let norm = vec_l2_norm_simd(&a).expect("Unexpected error");
        assert!((norm - 1.0).abs() < 0.001);
    }

    #[test]
    fn test_vec_l2_norm() {
        let a = [3.0, 4.0];
        let norm = vec_l2_norm_simd(&a).expect("Unexpected error");
        assert!((norm - 5.0).abs() < 0.001);
    }
}
