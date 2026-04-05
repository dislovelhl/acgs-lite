/// Core hot-path governance validator.
///
/// Implements keyword-scan + anchor-dispatch + regex validation using
/// Aho-Corasick automaton for O(N) multi-pattern matching.
///
/// Constitutional Hash: 608508a9bd224290

use aho_corasick::{AhoCorasick, MatchKind};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};
use regex::Regex;
use std::collections::{HashMap, HashSet};

use crate::context::{self, ContextRule};
use crate::result::{RustDecision, RustViolation};
use crate::severity::{self, Severity};

/// Payload carried by each Aho-Corasick pattern.
#[derive(Clone)]
enum AcPayload {
    Keyword(Vec<(usize, bool)>),
    Anchor(usize),
    Both {
        kw_data: Vec<(usize, bool)>,
        anchor_idx: usize,
    },
}

struct AnchorEntry {
    patterns: Vec<(usize, Regex)>,
}

#[derive(Clone)]
struct RuleData {
    rule_id: String,
    rule_text: String,
    severity: String,
    severity_enum: Severity,
    category: String,
    is_critical: bool,
}

/// The core hot-path validator exposed to Python.
#[pyclass]
pub struct GovernanceValidator {
    automaton: AhoCorasick,
    payloads: Vec<AcPayload>,
    anchor_dispatch: Vec<AnchorEntry>,
    no_anchor_pats: Vec<(usize, Regex)>,
    rule_data: Vec<RuleData>,
    positive_verbs: HashSet<String>,
    strict: bool,
    context_rules: Vec<ContextRule>,
    const_hash: String,
}

#[pymethods]
impl GovernanceValidator {
    /// Constructor.
    ///
    /// kw_to_idxs: {keyword_str: [(rule_idx: int, kw_has_neg: bool)]}
    /// anchor_dispatch_py: [(anchor_str, [(rule_idx: int, pattern_str: str)])]
    /// no_anchor_pats_py: [(rule_idx: int, pattern_str: str)]
    /// rule_data_py: [(rule_id, rule_text, severity_str, category, is_critical)]
    /// positive_verbs_py: [str]
    /// strict: bool
    /// context_rules_py: optional [(rule_id, rule_text, severity, category, [kw_lower], [patterns], enabled)]
    /// const_hash: optional str
    #[new]
    #[pyo3(signature = (kw_to_idxs, anchor_dispatch_py, no_anchor_pats_py, rule_data_py, positive_verbs_py, strict, context_rules_py=None, const_hash=None))]
    fn new(
        kw_to_idxs: &Bound<'_, PyDict>,
        anchor_dispatch_py: &Bound<'_, PyList>,
        no_anchor_pats_py: &Bound<'_, PyList>,
        rule_data_py: &Bound<'_, PyList>,
        positive_verbs_py: &Bound<'_, PyList>,
        strict: bool,
        context_rules_py: Option<&Bound<'_, PyList>>,
        const_hash: Option<String>,
    ) -> PyResult<Self> {
        // Build anchor_to_idx and anchor_dispatch
        let mut anchor_to_idx: HashMap<String, usize> = HashMap::new();
        let mut anchor_dispatch: Vec<AnchorEntry> = Vec::new();
        for (ai, item) in anchor_dispatch_py.iter().enumerate() {
            let tuple = item.downcast::<PyTuple>()?;
            let anchor: String = tuple.get_item(0)?.extract()?;
            let pats_py = tuple.get_item(1)?.downcast_into::<PyList>()?;
            let mut patterns: Vec<(usize, Regex)> = Vec::with_capacity(pats_py.len());
            for pat_item in pats_py.iter() {
                let pt = pat_item.downcast::<PyTuple>()?;
                let rule_idx: usize = pt.get_item(0)?.extract()?;
                let pat_str: String = pt.get_item(1)?.extract()?;
                let re = Regex::new(&pat_str).map_err(|e| {
                    PyValueError::new_err(format!("Bad regex '{}': {}", pat_str, e))
                })?;
                patterns.push((rule_idx, re));
            }
            anchor_to_idx.insert(anchor, ai);
            anchor_dispatch.push(AnchorEntry { patterns });
        }

        // Build kw_map
        let mut kw_map: HashMap<String, Vec<(usize, bool)>> = HashMap::new();
        for (key, val) in kw_to_idxs.iter() {
            let kw: String = key.extract()?;
            let idxs_py = val.downcast::<PyList>()?;
            let mut idxs: Vec<(usize, bool)> = Vec::with_capacity(idxs_py.len());
            for item in idxs_py.iter() {
                let t = item.downcast::<PyTuple>()?;
                let rule_idx: usize = t.get_item(0)?.extract()?;
                let has_neg: bool = t.get_item(1)?.extract()?;
                idxs.push((rule_idx, has_neg));
            }
            kw_map.insert(kw, idxs);
        }

        // Collect all words and build payloads
        let mut all_words: Vec<String> = Vec::new();
        let mut payloads: Vec<AcPayload> = Vec::new();
        for (kw, idxs) in &kw_map {
            if let Some(&ai) = anchor_to_idx.get(kw) {
                all_words.push(kw.clone());
                payloads.push(AcPayload::Both {
                    kw_data: idxs.clone(),
                    anchor_idx: ai,
                });
            } else {
                all_words.push(kw.clone());
                payloads.push(AcPayload::Keyword(idxs.clone()));
            }
        }
        for (anchor, &ai) in &anchor_to_idx {
            if !kw_map.contains_key(anchor) {
                all_words.push(anchor.clone());
                payloads.push(AcPayload::Anchor(ai));
            }
        }

        // No-anchor patterns
        let mut no_anchor_pats: Vec<(usize, Regex)> = Vec::new();
        for item in no_anchor_pats_py.iter() {
            let t = item.downcast::<PyTuple>()?;
            let rule_idx: usize = t.get_item(0)?.extract()?;
            let pat_str: String = t.get_item(1)?.extract()?;
            let re = Regex::new(&pat_str).map_err(|e| {
                PyValueError::new_err(format!("Bad regex '{}': {}", pat_str, e))
            })?;
            no_anchor_pats.push((rule_idx, re));
        }

        // Rule data
        let mut rule_data: Vec<RuleData> = Vec::with_capacity(rule_data_py.len());
        for item in rule_data_py.iter() {
            let t = item.downcast::<PyTuple>()?;
            let sev_str: String = t.get_item(2)?.extract()?;
            rule_data.push(RuleData {
                rule_id: t.get_item(0)?.extract()?,
                rule_text: t.get_item(1)?.extract()?,
                severity_enum: Severity::from_str(&sev_str),
                severity: sev_str,
                category: t.get_item(3)?.extract()?,
                is_critical: t.get_item(4)?.extract()?,
            });
        }

        // Positive verbs set
        let mut positive_verbs: HashSet<String> = HashSet::new();
        for item in positive_verbs_py.iter() {
            positive_verbs.insert(item.extract()?);
        }

        // Context rules (optional, for validate_full)
        let context_rules = if let Some(cr_py) = context_rules_py {
            let mut rules = Vec::with_capacity(cr_py.len());
            for item in cr_py.iter() {
                let t = item.downcast::<PyTuple>()?;
                let rule_id: String = t.get_item(0)?.extract()?;
                let rule_text: String = t.get_item(1)?.extract()?;
                let sev_str: String = t.get_item(2)?.extract()?;
                let category: String = t.get_item(3)?.extract()?;
                let kws_py = t.get_item(4)?.downcast_into::<PyList>()?;
                let pats_py = t.get_item(5)?.downcast_into::<PyList>()?;
                let enabled: bool = t.get_item(6)?.extract()?;

                let keywords_lower: Vec<String> = kws_py
                    .iter()
                    .map(|k| k.extract::<String>())
                    .collect::<PyResult<_>>()?;

                let compiled_patterns: Vec<Regex> = pats_py
                    .iter()
                    .map(|p| {
                        let s: String = p.extract()?;
                        Regex::new(&format!("(?i){}", s)).map_err(|e| {
                            PyValueError::new_err(format!("Bad context regex '{}': {}", s, e))
                        })
                    })
                    .collect::<PyResult<_>>()?;

                rules.push(ContextRule {
                    rule_id,
                    rule_text,
                    severity: Severity::from_str(&sev_str),
                    category,
                    keywords_lower,
                    compiled_patterns,
                    enabled,
                });
            }
            rules
        } else {
            Vec::new()
        };

        // Build Aho-Corasick automaton
        let automaton = AhoCorasick::builder()
            .match_kind(MatchKind::Standard)
            .build(&all_words)
            .map_err(|e| PyValueError::new_err(format!("AC build error: {}", e)))?;

        // Guard: bitmask deduplication uses u64 — max 63 rules/anchors
        if rule_data.len() > 63 {
            return Err(PyValueError::new_err(format!(
                "GovernanceValidator: rule count {} exceeds 63 (u64 bitmask limit)",
                rule_data.len()
            )));
        }
        if anchor_dispatch.len() > 63 {
            return Err(PyValueError::new_err(format!(
                "GovernanceValidator: anchor count {} exceeds 63 (u64 bitmask limit)",
                anchor_dispatch.len()
            )));
        }

        Ok(GovernanceValidator {
            automaton,
            payloads,
            anchor_dispatch,
            no_anchor_pats,
            rule_data,
            positive_verbs,
            strict,
            context_rules,
            const_hash: const_hash.unwrap_or_default(),
        })
    }

    /// Legacy hot-path validation — minimal Python object creation.
    ///
    /// Returns: (decision: int, data: int)
    ///   (ALLOW=0, 0)              — no violations
    ///   (DENY_CRITICAL=1, rule_idx) — critical violation
    ///   (DENY=2, fired_bitmask)   — non-critical violations
    fn validate_hot(&self, text_lower: &str) -> PyResult<(i32, i64)> {
        let decision = self.scan(text_lower);
        Ok(decision.to_legacy_tuple())
    }

    /// Full validation with structured violation data.
    ///
    /// Returns: (decision: int, violations: [(rule_id, rule_text, severity, matched_content, category)], blocking: bool)
    ///
    /// context_pairs: optional list of (key, value) from the context dict
    #[pyo3(signature = (text_lower, context_pairs=None))]
    fn validate_full(
        &self,
        text_lower: &str,
        context_pairs: Option<Vec<(String, String)>>,
    ) -> PyResult<(i32, Vec<(String, String, String, String, String)>, bool)> {
        let decision = self.scan(text_lower);

        match decision {
            RustDecision::Allow => {
                // Check context if provided
                if let Some(ref pairs) = context_pairs {
                    if !pairs.is_empty() && !self.context_rules.is_empty() {
                        let ctx_violations =
                            context::process_context(pairs, &self.context_rules);
                        if !ctx_violations.is_empty() {
                            let has_blocking =
                                ctx_violations.iter().any(|v| v.severity.blocks());
                            let tuples: Vec<_> = ctx_violations
                                .into_iter()
                                .map(|v| {
                                    (
                                        v.rule_id,
                                        v.rule_text,
                                        v.severity.as_str().to_string(),
                                        v.matched_content,
                                        v.category,
                                    )
                                })
                                .collect();
                            return Ok((severity::DENY, tuples, has_blocking));
                        }
                    }
                }
                Ok((severity::ALLOW, Vec::new(), false))
            }
            RustDecision::DenyCritical { rule_idx } => {
                let rd = &self.rule_data[rule_idx];
                let tuples = vec![(
                    rd.rule_id.clone(),
                    rd.rule_text.clone(),
                    rd.severity.clone(),
                    String::new(),
                    rd.category.clone(),
                )];
                Ok((severity::DENY_CRITICAL, tuples, true))
            }
            RustDecision::Deny {
                mut violations,
                has_blocking,
            } => {
                // Also process context if provided
                if let Some(ref pairs) = context_pairs {
                    if !pairs.is_empty() && !self.context_rules.is_empty() {
                        let ctx_violations =
                            context::process_context(pairs, &self.context_rules);
                        violations.extend(ctx_violations);
                    }
                }
                let blocking =
                    has_blocking || violations.iter().any(|v| v.severity.blocks());
                let tuples: Vec<_> = violations
                    .into_iter()
                    .map(|v| {
                        (
                            v.rule_id,
                            v.rule_text,
                            v.severity.as_str().to_string(),
                            v.matched_content,
                            v.category,
                        )
                    })
                    .collect();
                Ok((severity::DENY, tuples, blocking))
            }
        }
    }

    /// Get the constitutional hash stored during construction.
    #[getter]
    fn const_hash(&self) -> &str {
        &self.const_hash
    }
}

impl GovernanceValidator {
    /// Core scan logic — shared between validate_hot and validate_full.
    fn scan(&self, text_lower: &str) -> RustDecision {
        let first_word = match text_lower.find(' ') {
            Some(i) => &text_lower[..i],
            None => text_lower,
        };
        let is_pos_verb = self.positive_verbs.contains(first_word);

        let mut fired: u64 = 0;
        let mut hit_anchors: u64 = 0;
        let mut violations: Vec<RustViolation> = Vec::new();

        // AC scan — overlapping mode finds all matches
        for mat in self.automaton.find_overlapping_iter(text_lower) {
            match &self.payloads[mat.pattern().as_usize()] {
                AcPayload::Keyword(kw_data) => {
                    for &(rule_idx, kw_has_neg) in kw_data {
                        if is_pos_verb && !kw_has_neg {
                            continue;
                        }
                        let bit = 1u64 << rule_idx;
                        if fired & bit != 0 {
                            continue;
                        }
                        fired |= bit;
                        let rd = &self.rule_data[rule_idx];
                        if self.strict && rd.is_critical {
                            return RustDecision::DenyCritical { rule_idx };
                        }
                        violations.push(RustViolation {
                            rule_idx,
                            rule_id: rd.rule_id.clone(),
                            rule_text: rd.rule_text.clone(),
                            severity: rd.severity_enum,
                            matched_content: String::new(),
                            category: rd.category.clone(),
                        });
                    }
                }
                AcPayload::Anchor(ai) => {
                    hit_anchors |= 1u64 << ai;
                }
                AcPayload::Both {
                    kw_data,
                    anchor_idx,
                } => {
                    hit_anchors |= 1u64 << anchor_idx;
                    for &(rule_idx, kw_has_neg) in kw_data {
                        if is_pos_verb && !kw_has_neg {
                            continue;
                        }
                        let bit = 1u64 << rule_idx;
                        if fired & bit != 0 {
                            continue;
                        }
                        fired |= bit;
                        let rd = &self.rule_data[rule_idx];
                        if self.strict && rd.is_critical {
                            return RustDecision::DenyCritical { rule_idx };
                        }
                        violations.push(RustViolation {
                            rule_idx,
                            rule_id: rd.rule_id.clone(),
                            rule_text: rd.rule_text.clone(),
                            severity: rd.severity_enum,
                            matched_content: String::new(),
                            category: rd.category.clone(),
                        });
                    }
                }
            }
        }

        // Anchor dispatch (regex patterns)
        if hit_anchors != 0 || !self.no_anchor_pats.is_empty() {
            if hit_anchors != 0 {
                let mut tmp = hit_anchors;
                while tmp != 0 {
                    let lsb = tmp & tmp.wrapping_neg();
                    let ai = lsb.trailing_zeros() as usize;
                    tmp ^= lsb;
                    if ai < self.anchor_dispatch.len() {
                        for (rule_idx, re) in &self.anchor_dispatch[ai].patterns {
                            let bit = 1u64 << rule_idx;
                            if fired & bit == 0 && re.is_match(text_lower) {
                                fired |= bit;
                                let rd = &self.rule_data[*rule_idx];
                                if self.strict && rd.is_critical {
                                    return RustDecision::DenyCritical {
                                        rule_idx: *rule_idx,
                                    };
                                }
                                violations.push(RustViolation {
                                    rule_idx: *rule_idx,
                                    rule_id: rd.rule_id.clone(),
                                    rule_text: rd.rule_text.clone(),
                                    severity: rd.severity_enum,
                                    matched_content: String::new(),
                                    category: rd.category.clone(),
                                });
                            }
                        }
                    }
                }
            }
            for (rule_idx, re) in &self.no_anchor_pats {
                let bit = 1u64 << rule_idx;
                if fired & bit == 0 && re.is_match(text_lower) {
                    fired |= bit;
                    let rd = &self.rule_data[*rule_idx];
                    if self.strict && rd.is_critical {
                        return RustDecision::DenyCritical {
                            rule_idx: *rule_idx,
                        };
                    }
                    violations.push(RustViolation {
                        rule_idx: *rule_idx,
                        rule_id: rd.rule_id.clone(),
                        rule_text: rd.rule_text.clone(),
                        severity: rd.severity_enum,
                        matched_content: String::new(),
                        category: rd.category.clone(),
                    });
                }
            }
        }

        if violations.is_empty() {
            RustDecision::Allow
        } else {
            let has_blocking = violations.iter().any(|v| v.severity.blocks());
            RustDecision::Deny {
                violations,
                has_blocking,
            }
        }
    }
}
