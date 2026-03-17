use serde::{Deserialize, Serialize};
use crate::{AgentMessage, ValidationResult};
use std::time::Duration;
use moka::future::Cache;
use reqwest::Client;
use dashmap::DashMap;
use std::sync::Arc;
use tracing::{error, warn, debug};
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};

#[derive(Debug, Serialize, Deserialize)]
pub struct OpaInput<T> {
    pub input: T,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ConstitutionalInput {
    pub message: AgentMessage,
    pub constitutional_hash: String,
    pub timestamp: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct OpaResponse {
    pub result: Option<serde_json::Value>,
}

#[derive(Debug, Clone)]
pub struct OpaClient {
    endpoint: String,
    client: Client,
    cache: Cache<String, ValidationResult>,
    policy_index: Arc<DashMap<String, ValidationResult>>,
    fail_closed: bool,
}

impl OpaClient {
    pub fn new(endpoint: String) -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(5))
            .pool_idle_timeout(Duration::from_secs(90))
            .build()
            .unwrap_or_default();

        // Optimized cache for ACGS-2: 100,000 entries to support Spec 007
        let cache = Cache::builder()
            .max_capacity(100_000)
            .time_to_live(Duration::from_secs(300)) // 5 minutes
            .build();

        Self {
            endpoint: endpoint.trim_end_matches('/').to_string(),
            client,
            cache,
            policy_index: Arc::new(DashMap::new()),
            fail_closed: true,
        }
    }

    pub fn with_fail_closed(mut self, fail_closed: bool) -> Self {
        self.fail_closed = fail_closed;
        self
    }

    pub async fn validate_constitutional(&self, message: &AgentMessage) -> Result<ValidationResult, Box<dyn std::error::Error + Send + Sync>> {
        // Optimized Canonical Cache Key (Spec 007)
        let mut hasher = DefaultHasher::new();
        message.constitutional_hash.hash(&mut hasher);
        message.tenant_id.hash(&mut hasher);
        // We exclude message_id to ensure same content hits the cache
        for (k, v) in &message.content {
            k.hash(&mut hasher);
            v.hash(&mut hasher);
        }
        let input_hash = hasher.finish();
        let cache_key = format!("constitutional:{:x}", input_hash);

        if let Some(cached) = self.cache.get(&cache_key).await {
            debug!("OPA Cache Hit (Constitutional): {}", cache_key);
            return Ok(cached);
        }

        let input = ConstitutionalInput {
            message: message.clone(),
            constitutional_hash: message.constitutional_hash.clone(),
            timestamp: chrono::Utc::now().to_rfc3339(),
        };

        let result = self.evaluate_policy("acgs/constitutional/validate", &input).await?;

        self.cache.insert(cache_key, result.clone()).await;
        Ok(result)
    }

    async fn evaluate_policy<T: Serialize>(&self, policy_path: &str, input: &T) -> Result<ValidationResult, Box<dyn std::error::Error + Send + Sync>> {
        let url = format!("{}/v1/data/{}", self.endpoint, policy_path);

        let opa_input = OpaInput { input };

        let response = match self.client.post(&url)
            .json(&opa_input)
            .send()
            .await {
                Ok(resp) => resp,
                Err(e) => {
                    error!("OPA connection error: {}", e);
                    return Ok(self.handle_fallback(format!("OPA connection error: {}", e)));
                }
            };

        if !response.status().is_success() {
            let status = response.status();
            error!("OPA returned error status: {}", status);
            return Ok(self.handle_fallback(format!("OPA error status: {}", status)));
        }

        let opa_resp: OpaResponse = match response.json().await {
            Ok(data) => data,
            Err(e) => {
                error!("Failed to parse OPA response: {}", e);
                return Ok(self.handle_fallback(format!("Failed to parse OPA response: {}", e)));
            }
        };

        let mut validation_result = ValidationResult::new();

        match opa_resp.result {
            Some(serde_json::Value::Bool(allowed)) => {
                validation_result.is_valid = allowed;
                if !allowed {
                    validation_result.add_error("Policy denied by OPA".to_string());
                }
            }
            Some(serde_json::Value::Object(obj)) => {
                let allowed = obj.get("allow").and_then(|v| v.as_bool()).unwrap_or(false);
                validation_result.is_valid = allowed;
                if !allowed {
                    let reason = obj.get("reason").and_then(|v| v.as_str()).unwrap_or("Policy denied by OPA");
                    validation_result.add_error(reason.to_string());
                }
                if let Some(metadata) = obj.get("metadata").and_then(|v| v.as_object()) {
                    for (k, v) in metadata {
                        validation_result.metadata.insert(k.clone(), v.to_string());
                    }
                }
            }
            _ => {
                warn!("Unexpected OPA result format for policy {}", policy_path);
                return Ok(self.handle_fallback("Unexpected OPA result format".to_string()));
            }
        }

        Ok(validation_result)
    }

    fn handle_fallback(&self, error_msg: String) -> ValidationResult {
        let mut result = ValidationResult::new();
        if self.fail_closed {
            result.is_valid = false;
            result.decision = "DENY".to_string();
            result.add_error(format!("OPA Failure (Fail-Closed): {}", error_msg));
        } else {
            result.is_valid = true;
            result.decision = "ALLOW".to_string();
            result.add_warning(format!("OPA Failure (Fail-Open): {}", error_msg));
        }
        result
    }

    pub async fn validate(&self, message: &AgentMessage) -> Result<ValidationResult, Box<dyn std::error::Error + Send + Sync>> {
        // 1. Check O(1) Policy Index (Spec 007 Optimization)
        // We use the constitutional hash as the primary lookup key for high-frequency policies
        if let Some(result) = self.policy_index.get(&message.constitutional_hash) {
            return Ok(result.clone());
        }

        // 2. Canonical Cache & OPA Fallback
        self.validate_constitutional(message).await
    }

    /// Add a policy result to the local O(1) index (Spec 007)
    pub fn update_index(&self, policy_path: String, result: ValidationResult) {
        self.policy_index.insert(policy_path, result);
    }

    /// Populate mock policies for scale benchmarking (Spec 007)
    pub fn populate_mock_policies(&self, count: usize) {
        for i in 0..count {
            let mut result = ValidationResult::new();
            result.is_valid = true;
            result.decision = "ALLOW".to_string();
            result.metadata.insert("mock".to_string(), "true".to_string());
            result.metadata.insert("index".to_string(), i.to_string());
            // Use index as a pseudo-hash for benchmarking
            self.update_index(format!("mock_hash_{}", i), result);
        }
    }

    /// Optimized evaluation with local index fallback
    #[allow(dead_code)]
    pub async fn evaluate_with_index<T: Serialize + Hash>(&self, policy_path: &str, input: &T) -> Result<ValidationResult, Box<dyn std::error::Error + Send + Sync>> {
        // 1. Check O(1) Policy Index
        if let Some(result) = self.policy_index.get(policy_path) {
            return Ok(result.clone());
        }

        // 2. Canonical Cache Check
        let mut hasher = DefaultHasher::new();
        policy_path.hash(&mut hasher);
        input.hash(&mut hasher);
        let cache_key = format!("eval:{:x}", hasher.finish());

        if let Some(cached) = self.cache.get(&cache_key).await {
            return Ok(cached);
        }

        // 3. Fallback to OPA
        let result = self.evaluate_policy(policy_path, input).await?;
        self.cache.insert(cache_key, result.clone()).await;
        Ok(result)
    }

    pub fn clear_cache(&self) {
        self.cache.invalidate_all();
        self.policy_index.clear();
    }

    pub async fn health_check(&self) -> serde_json::Value {
        let url = format!("{}/health", self.endpoint);
        match self.client.get(&url).send().await {
            Ok(resp) if resp.status().is_success() => {
                serde_json::json!({"status": "healthy", "mode": "http", "cache_size": self.cache.entry_count()})
            }
            Ok(resp) => {
                serde_json::json!({"status": "unhealthy", "code": resp.status().as_u16()})
            }
            Err(e) => {
                serde_json::json!({"status": "unhealthy", "error": e.to_string()})
            }
        }
    }
}
