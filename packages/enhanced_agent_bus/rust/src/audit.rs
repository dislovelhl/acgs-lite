use serde::{Deserialize, Serialize};
use crate::{AgentMessage, ValidationResult};

#[derive(Debug, Serialize, Deserialize)]
pub struct DecisionLog {
    pub trace_id: String,
    pub agent_id: String,
    pub risk_score: f32,
    pub decision: String,
    pub timestamp: String,
}

#[derive(Clone)]
pub struct AuditClient {
    pub _service_url: String,
    tx: tokio::sync::mpsc::Sender<DecisionLog>,
}

impl AuditClient {
    pub fn new(service_url: String) -> Self {
        let (tx, mut rx) = tokio::sync::mpsc::channel::<DecisionLog>(1000);
        let client = reqwest::Client::new();
        let url = service_url.clone();

        // Background task for non-blocking audit reporting
        tokio::spawn(async move {
            while let Some(log) = rx.recv().await {
                let _ = client.post(&url)
                    .json(&log)
                    .send()
                    .await;
            }
        });

        Self {
            _service_url: service_url,
            tx,
        }
    }

    pub async fn log_decision(&self, message: &AgentMessage, result: &ValidationResult) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let log = DecisionLog {
            trace_id: message.message_id.clone(),
            agent_id: message.from_agent.clone(),
            risk_score: message.impact_score.unwrap_or(0.0),
            decision: if result.is_valid { "ALLOW".to_string() } else { "DENY".to_string() },
            timestamp: chrono::Utc::now().to_rfc3339(),
        };

        // Non-blocking send to background task
        let _ = self.tx.try_send(log);

        Ok(())
    }
}
