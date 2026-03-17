use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc, Duration, Timelike};
use crate::{AgentMessage, MessagePriority, MessageType};
use dashmap::DashMap;
use atomic_float::AtomicF32;
use std::sync::atomic::Ordering;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoringConfig {
    pub semantic_weight: f32,
    pub permission_weight: f32,
    pub volume_weight: f32,
    pub context_weight: f32,
    pub drift_weight: f32,
    pub priority_weight: f32,
    pub type_weight: f32,
    pub critical_priority_boost: f32,
    pub high_semantic_boost: f32,
}

impl Default for ScoringConfig {
    fn default() -> Self {
        Self {
            semantic_weight: 0.30,
            permission_weight: 0.20,
            volume_weight: 0.10,
            context_weight: 0.10,
            drift_weight: 0.15,
            priority_weight: 0.10,
            type_weight: 0.05,
            critical_priority_boost: 0.9,
            high_semantic_boost: 0.8,
        }
    }
}

pub struct ImpactScorer {
    pub config: ScoringConfig,
    #[cfg(feature = "ort")]
    onnx_session: Option<ort::session::Session>,
    #[allow(dead_code)]
    tokenizer: Option<tokenizers::Tokenizer>,
    agent_request_rates: DashMap<String, Vec<DateTime<Utc>>>,
    agent_impact_history: DashMap<String, Vec<f32>>,
    high_impact_keywords: Vec<&'static str>,
}

impl ImpactScorer {
    pub fn new(config: Option<ScoringConfig>, _onnx_path: Option<&str>) -> Self {
        let config = config.unwrap_or_default();

        #[cfg(feature = "ort")]
        let (_session, _tokenizer) = if let Some(path) = _onnx_path {
            let session = ort::session::Session::builder()
                .expect("Unexpected error")
                .commit_from_file(path)
                .ok();
            let tokenizer = tokenizers::Tokenizer::from_pretrained("distilbert-base-uncased", None).ok();
            (session, tokenizer)
        } else {
            (None, None)
        };

        #[cfg(not(feature = "ort"))]
        let _tokenizer: Option<tokenizers::Tokenizer> = None;

        Self {
            config,
            #[cfg(feature = "ort")]
            onnx_session: _session,
            tokenizer: _tokenizer,
            agent_request_rates: DashMap::new(),
            agent_impact_history: DashMap::new(),
            high_impact_keywords: vec![
                "critical", "emergency", "security", "breach", "violation", "danger",
                "risk", "threat", "attack", "exploit", "vulnerability", "compromise",
                "governance", "policy", "regulation", "compliance", "legal", "audit",
                "financial", "transaction", "payment", "transfer", "blockchain", "consensus",
                "unauthorized", "abnormal", "suspicious", "alert"
            ],
        }
    }

    pub fn calculate_impact_score(&self, message: &AgentMessage) -> f32 {
        let mut score = 0.0;

        // 1. Semantic Score
        let semantic_score = self.calculate_semantic_score(message);
        score += semantic_score * self.config.semantic_weight;

        // 2. Permission Score
        let permission_score = self.calculate_permission_score(message);
        score += permission_score * self.config.permission_weight;

        // 3. Volume Score
        let volume_score = self.calculate_volume_score(&message.from_agent);
        score += volume_score * self.config.volume_weight;

        // 4. Context Score
        let context_score = self.calculate_context_score(message);
        score += context_score * self.config.context_weight;

        // 5. Drift Score
        let drift_score = self.calculate_drift_score(&message.from_agent, context_score);
        score += drift_score * self.config.drift_weight;

        // 6. Priority Factor
        let priority_factor = match message.priority {
            MessagePriority::Critical => 1.0,
            MessagePriority::High => 0.7,
            MessagePriority::Normal => 0.3,
            MessagePriority::Low => 0.1,
        };
        score += priority_factor * self.config.priority_weight;

        // 7. Type Factor
        let type_factor = match message.message_type {
            MessageType::GovernanceRequest | MessageType::ConstitutionalValidation => 0.8,
            MessageType::TaskRequest => 0.5,
            _ => 0.2,
        };
        score += type_factor * self.config.type_weight;

        // Normalize
        let total_weight = self.config.semantic_weight + self.config.permission_weight +
                          self.config.volume_weight + self.config.context_weight +
                          self.config.drift_weight + self.config.priority_weight +
                          self.config.type_weight;

        if total_weight > 0.0 {
            score /= total_weight;
        }

        // Boosts
        if priority_factor >= 1.0 {
            score = score.max(self.config.critical_priority_boost);
        }
        if semantic_score > 0.8 {
            score = score.max(self.config.high_semantic_boost);
        }

        score.clamp(0.0, 1.0)
    }

    fn calculate_semantic_score(&self, message: &AgentMessage) -> f32 {
        #[cfg(feature = "ort")]
        if let (Some(_session), Some(_tokenizer)) = (&self.onnx_session, &self.tokenizer) {
            // Full BERT implementation would go here
            // For now, fallback to keyword matching if ONNX fails or is not fully implemented
            self.keyword_semantic_score(message)
        } else {
            self.keyword_semantic_score(message)
        }

        #[cfg(not(feature = "ort"))]
        self.keyword_semantic_score(message)
    }

    fn keyword_semantic_score(&self, message: &AgentMessage) -> f32 {
        let mut hits = 0;
        for value in message.content.values() {
            let lower_val = value.to_lowercase();
            for kw in &self.high_impact_keywords {
                if lower_val.contains(kw) {
                    hits += 1;
                }
            }
        }
        (hits as f32 * 0.3).min(0.9)
    }

    fn calculate_permission_score(&self, message: &AgentMessage) -> f32 {
        // Check for high-risk tools in payload or content
        let high_risk_tools = ["admin", "delete", "transfer", "execute", "blockchain", "payment"];
        let mut max_risk = 0.1;

        for value in message.content.values() {
            let lower_val = value.to_lowercase();
            if high_risk_tools.iter().any(|&tool| lower_val.contains(tool)) {
                max_risk = 0.9;
                break;
            }
        }
        max_risk
    }

    fn calculate_volume_score(&self, agent_id: &str) -> f32 {
        let now = Utc::now();
        let window = Duration::seconds(60);

        let mut rates = self.agent_request_rates.entry(agent_id.to_string()).or_default();
        rates.push(now);
        rates.retain(|&t| now - t < window);

        let count = rates.len();
        if count < 10 { 0.1 }
        else if count < 50 { 0.4 }
        else if count < 100 { 0.7 }
        else { 1.0 }
    }

    fn calculate_context_score(&self, message: &AgentMessage) -> f32 {
        let now = Utc::now();
        let mut score: f32 = 0.2;

        // Night time anomaly (1 AM to 5 AM)
        if now.hour() >= 1 && now.hour() <= 5 {
            score += 0.3;
        }

        // Check for large amounts in payload
        if let Some(amount_str) = message.payload.get("amount") {
            if let Ok(amount) = amount_str.parse::<f64>() {
                if amount > 10000.0 {
                    score += 0.4;
                }
            }
        }

        score.min(1.0)
    }

    fn calculate_drift_score(&self, agent_id: &str, current_impact: f32) -> f32 {
        let mut history = self.agent_impact_history.entry(agent_id.to_string()).or_default();

        if history.is_empty() {
            history.push(current_impact);
            return 0.0;
        }

        let mean: f32 = history.iter().sum::<f32>() / history.len() as f32;
        let deviation = (current_impact - mean).abs();

        history.push(current_impact);
        if history.len() > 20 {
            history.remove(0);
        }

        if deviation > 0.3 {
            (deviation / 0.3 * 0.5).min(1.0)
        } else {
            0.0
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RoutingDecision {
    pub lane: String,
    pub impact_score: f32,
    pub requires_deliberation: bool,
}

pub struct AdaptiveRouter {
    pub impact_threshold: AtomicF32,
    pub routing_history: DashMap<String, RoutingDecision>,
}

impl AdaptiveRouter {
    pub fn new(threshold: f32) -> Self {
        Self {
            impact_threshold: AtomicF32::new(threshold),
            routing_history: DashMap::new(),
        }
    }

    pub fn route(&self, message: &AgentMessage) -> RoutingDecision {
        let impact_score = message.impact_score.unwrap_or(0.0);
        let threshold = self.impact_threshold.load(Ordering::Relaxed);

        let decision = if impact_score >= threshold {
            RoutingDecision {
                lane: "deliberation".to_string(),
                impact_score,
                requires_deliberation: true,
            }
        } else {
            RoutingDecision {
                lane: "fast".to_string(),
                impact_score,
                requires_deliberation: false,
            }
        };

        self.routing_history.insert(message.message_id.clone(), decision.clone());
        decision
    }

    #[allow(dead_code)]
    pub fn update_threshold(&self, fp_rate: f32, fn_rate: f32) {
        let mut adjustment = 0.0;
        if fp_rate > 0.3 {
            adjustment = 0.05;
        } else if fn_rate > 0.1 {
            adjustment = -0.05;
        }

        if adjustment != 0.0 {
            let current = self.impact_threshold.load(Ordering::Relaxed);
            self.impact_threshold.store((current + adjustment).clamp(0.1, 0.95), Ordering::Relaxed);
        }
    }
}
