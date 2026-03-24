/// Constitutional hash computation.
///
/// Produces the same SHA-256 hash as `Constitution.model_post_init()` in Python:
///   canonical = "|".join(f"{r.id}:{r.text}:{r.severity}:{kw1,kw2,...}" for r in sorted(rules))
///   hash = sha256(canonical.encode()).hexdigest()[:16]
///
/// Constitutional Hash: cdd01ef066bc6cf2

use sha2::{Digest, Sha256};

/// Compute the constitutional hash from rule data.
///
/// `rules` is a list of `(rule_id, rule_text, severity_value, sorted_keywords)`.
/// Rules are sorted by rule_id before hashing (matching Python behavior).
/// This function does not mutate the input — it clones and sorts internally.
pub fn compute_constitutional_hash(
    rules: &[(String, String, String, Vec<String>)],
) -> String {
    let mut sorted: Vec<_> = rules.to_vec();
    sorted.sort_by(|a, b| a.0.cmp(&b.0));

    let canonical: String = sorted
        .iter()
        .map(|(id, text, severity, keywords)| {
            let mut kws = keywords.clone();
            kws.sort();
            format!("{}:{}:{}:{}", id, text, severity, kws.join(","))
        })
        .collect::<Vec<_>>()
        .join("|");

    let mut hasher = Sha256::new();
    hasher.update(canonical.as_bytes());
    let digest = hasher.finalize();
    hex::encode(digest)[..16].to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_empty_rules() {
        let rules: Vec<(String, String, String, Vec<String>)> = vec![];
        let hash = compute_constitutional_hash(&rules);
        assert_eq!(hash.len(), 16);
    }

    #[test]
    fn test_deterministic() {
        let rules = vec![(
            "R1".into(),
            "Test rule".into(),
            "high".into(),
            vec!["keyword".to_string()],
        )];
        assert_eq!(
            compute_constitutional_hash(&rules),
            compute_constitutional_hash(&rules),
        );
    }

    #[test]
    fn test_sort_order_invariant() {
        let rules_a = vec![
            ("B".into(), "rule b".into(), "high".into(), vec![]),
            ("A".into(), "rule a".into(), "low".into(), vec![]),
        ];
        let rules_b = vec![
            ("A".into(), "rule a".into(), "low".into(), vec![]),
            ("B".into(), "rule b".into(), "high".into(), vec![]),
        ];
        assert_eq!(
            compute_constitutional_hash(&rules_a),
            compute_constitutional_hash(&rules_b),
        );
    }
}
