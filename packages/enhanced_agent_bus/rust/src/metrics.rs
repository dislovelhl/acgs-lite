//! ACGS-2 Enhanced Agent Bus - Prometheus Metrics
//! Constitutional Hash: cdd01ef066bc6cf2
//!
//! High-performance metrics collection for governance observability.

use once_cell::sync::Lazy;
use parking_lot::RwLock;
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant};

use crate::crypto::CONSTITUTIONAL_HASH;

/// Atomic counter for thread-safe incrementing
#[derive(Debug, Default)]
pub struct Counter {
    value: AtomicU64,
}

impl Counter {
    pub fn new() -> Self {
        Self {
            value: AtomicU64::new(0),
        }
    }

    pub fn inc(&self) {
        self.value.fetch_add(1, Ordering::Relaxed);
    }

    pub fn inc_by(&self, n: u64) {
        self.value.fetch_add(n, Ordering::Relaxed);
    }

    pub fn get(&self) -> u64 {
        self.value.load(Ordering::Relaxed)
    }

    pub fn reset(&self) {
        self.value.store(0, Ordering::Relaxed);
    }
}

/// Histogram for latency measurements with predefined buckets
#[derive(Debug)]
pub struct Histogram {
    buckets: Vec<(f64, AtomicU64)>, // (upper_bound, count)
    sum: AtomicU64,                 // Sum in microseconds (for avg calculation)
    count: AtomicU64,
}

impl Histogram {
    /// Create a new histogram with default latency buckets (in milliseconds)
    pub fn new_latency() -> Self {
        // Buckets: 0.1ms, 0.5ms, 1ms, 2.5ms, 5ms, 10ms, 25ms, 50ms, 100ms, +Inf
        let bucket_bounds = vec![0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 25.0, 50.0, 100.0, f64::INFINITY];
        Self {
            buckets: bucket_bounds
                .into_iter()
                .map(|b| (b, AtomicU64::new(0)))
                .collect(),
            sum: AtomicU64::new(0),
            count: AtomicU64::new(0),
        }
    }

    /// Observe a latency value in milliseconds
    pub fn observe(&self, value_ms: f64) {
        // Increment bucket counters
        for (bound, counter) in &self.buckets {
            if value_ms <= *bound {
                counter.fetch_add(1, Ordering::Relaxed);
            }
        }

        // Update sum (store as microseconds for precision)
        let micros = (value_ms * 1000.0) as u64;
        self.sum.fetch_add(micros, Ordering::Relaxed);
        self.count.fetch_add(1, Ordering::Relaxed);
    }

    /// Observe duration directly
    pub fn observe_duration(&self, duration: Duration) {
        self.observe(duration.as_secs_f64() * 1000.0);
    }

    /// Get the average latency in milliseconds
    pub fn avg_ms(&self) -> f64 {
        let count = self.count.load(Ordering::Relaxed);
        if count == 0 {
            return 0.0;
        }
        let sum_micros = self.sum.load(Ordering::Relaxed);
        (sum_micros as f64 / count as f64) / 1000.0
    }

    /// Get approximate P99 latency (bucket-based estimation)
    pub fn p99_ms(&self) -> f64 {
        let total = self.count.load(Ordering::Relaxed);
        if total == 0 {
            return 0.0;
        }

        let target = (total as f64 * 0.99) as u64;
        for (bound, counter) in &self.buckets {
            if counter.load(Ordering::Relaxed) >= target {
                return *bound;
            }
        }
        100.0 // Max bucket
    }

    /// Export in Prometheus format
    pub fn to_prometheus(&self, name: &str, help: &str) -> String {
        let mut output = format!("# HELP {} {}\n", name, help);
        output.push_str(&format!("# TYPE {} histogram\n", name));

        for (bound, counter) in &self.buckets {
            let le = if *bound == f64::INFINITY {
                "+Inf".to_string()
            } else {
                format!("{:.3}", bound)
            };
            output.push_str(&format!(
                "{}_bucket{{le=\"{}\"}} {}\n",
                name,
                le,
                counter.load(Ordering::Relaxed)
            ));
        }

        output.push_str(&format!("{}_sum {}\n", name, self.sum.load(Ordering::Relaxed)));
        output.push_str(&format!(
            "{}_count {}\n",
            name,
            self.count.load(Ordering::Relaxed)
        ));

        output
    }
}

/// Global metrics registry for ACGS-2
pub struct MetricsRegistry {
    // Constitutional governance metrics
    pub constitutional_validations: Counter,
    pub constitutional_violations: Counter,
    pub constitutional_hash_mismatches: Counter,

    // Message processing metrics
    pub messages_processed: Counter,
    pub messages_failed: Counter,
    pub messages_in_deliberation: Counter,

    // Latency histograms
    pub message_processing_latency: Histogram,
    pub opa_evaluation_latency: Histogram,
    pub crypto_validation_latency: Histogram,
    pub impact_scoring_latency: Histogram,

    // Security metrics
    pub prompt_injections_blocked: Counter,
    pub signature_validations: Counter,
    pub signature_failures: Counter,

    // Cache metrics
    pub cache_hits: Counter,
    pub cache_misses: Counter,

    // Routing metrics
    pub fast_lane_messages: Counter,
    pub deliberation_lane_messages: Counter,

    // Labels for tenant-specific metrics
    tenant_counters: RwLock<HashMap<String, HashMap<String, Counter>>>,
}

impl MetricsRegistry {
    pub fn new() -> Self {
        Self {
            constitutional_validations: Counter::new(),
            constitutional_violations: Counter::new(),
            constitutional_hash_mismatches: Counter::new(),
            messages_processed: Counter::new(),
            messages_failed: Counter::new(),
            messages_in_deliberation: Counter::new(),
            message_processing_latency: Histogram::new_latency(),
            opa_evaluation_latency: Histogram::new_latency(),
            crypto_validation_latency: Histogram::new_latency(),
            impact_scoring_latency: Histogram::new_latency(),
            prompt_injections_blocked: Counter::new(),
            signature_validations: Counter::new(),
            signature_failures: Counter::new(),
            cache_hits: Counter::new(),
            cache_misses: Counter::new(),
            fast_lane_messages: Counter::new(),
            deliberation_lane_messages: Counter::new(),
            tenant_counters: RwLock::new(HashMap::new()),
        }
    }

    /// Get or create a tenant-specific counter
    pub fn tenant_counter(&self, tenant_id: &str, metric_name: &str) -> &Counter {
        // Note: This is a simplified implementation. In production, use dashmap.
        // The caller should cache the result to avoid repeated lookups.
        let counters = self.tenant_counters.read();
        if counters.contains_key(tenant_id) {
            // Safety: We're returning a reference to data that lives as long as self
            unsafe {
                let ptr = &*(counters.get(tenant_id).expect("Unexpected error") as *const HashMap<String, Counter>);
                if let Some(counter) = ptr.get(metric_name) {
                    return &*(counter as *const Counter);
                }
            }
        }
        drop(counters);

        // Create if not exists
        let mut counters = self.tenant_counters.write();
        counters
            .entry(tenant_id.to_string())
            .or_default()
            .entry(metric_name.to_string())
            .or_default();

        // Return reference (caller should cache)
        unsafe {
            let ptr = &*(counters.get(tenant_id).expect("Unexpected error") as *const HashMap<String, Counter>);
            &*(ptr.get(metric_name).expect("Unexpected error") as *const Counter)
        }
    }

    /// Export all metrics in Prometheus text format
    pub fn to_prometheus(&self) -> String {
        let mut output = String::new();

        // Constitutional governance
        output.push_str("# HELP acgs_constitutional_validations Total constitutional validations\n");
        output.push_str("# TYPE acgs_constitutional_validations counter\n");
        output.push_str(&format!(
            "acgs_constitutional_validations{{hash=\"{}\"}} {}\n",
            CONSTITUTIONAL_HASH,
            self.constitutional_validations.get()
        ));

        output.push_str("# HELP acgs_constitutional_violations Total constitutional violations\n");
        output.push_str("# TYPE acgs_constitutional_violations counter\n");
        output.push_str(&format!(
            "acgs_constitutional_violations {}\n",
            self.constitutional_violations.get()
        ));

        // Message processing
        output.push_str("# HELP acgs_messages_processed Total messages processed\n");
        output.push_str("# TYPE acgs_messages_processed counter\n");
        output.push_str(&format!(
            "acgs_messages_processed {}\n",
            self.messages_processed.get()
        ));

        // Latency histograms
        output.push_str(&self.message_processing_latency.to_prometheus(
            "acgs_message_processing_latency_ms",
            "Message processing latency in milliseconds",
        ));

        output.push_str(&self.opa_evaluation_latency.to_prometheus(
            "acgs_opa_evaluation_latency_ms",
            "OPA policy evaluation latency in milliseconds",
        ));

        // Security
        output.push_str("# HELP acgs_prompt_injections_blocked Total prompt injections blocked\n");
        output.push_str("# TYPE acgs_prompt_injections_blocked counter\n");
        output.push_str(&format!(
            "acgs_prompt_injections_blocked {}\n",
            self.prompt_injections_blocked.get()
        ));

        // Cache
        output.push_str("# HELP acgs_cache_hits Total cache hits\n");
        output.push_str("# TYPE acgs_cache_hits counter\n");
        output.push_str(&format!("acgs_cache_hits {}\n", self.cache_hits.get()));

        output.push_str("# HELP acgs_cache_misses Total cache misses\n");
        output.push_str("# TYPE acgs_cache_misses counter\n");
        output.push_str(&format!("acgs_cache_misses {}\n", self.cache_misses.get()));

        // Routing
        output.push_str("# HELP acgs_routing_lane_total Messages by routing lane\n");
        output.push_str("# TYPE acgs_routing_lane_total counter\n");
        output.push_str(&format!(
            "acgs_routing_lane_total{{lane=\"fast\"}} {}\n",
            self.fast_lane_messages.get()
        ));
        output.push_str(&format!(
            "acgs_routing_lane_total{{lane=\"deliberation\"}} {}\n",
            self.deliberation_lane_messages.get()
        ));

        output
    }

    /// Get summary statistics
    pub fn summary(&self) -> MetricsSummary {
        MetricsSummary {
            constitutional_hash: CONSTITUTIONAL_HASH.to_string(),
            total_validations: self.constitutional_validations.get(),
            total_violations: self.constitutional_violations.get(),
            messages_processed: self.messages_processed.get(),
            avg_latency_ms: self.message_processing_latency.avg_ms(),
            p99_latency_ms: self.message_processing_latency.p99_ms(),
            cache_hit_rate: {
                let hits = self.cache_hits.get() as f64;
                let total = hits + self.cache_misses.get() as f64;
                if total > 0.0 {
                    hits / total
                } else {
                    0.0
                }
            },
            prompt_injections_blocked: self.prompt_injections_blocked.get(),
        }
    }
}

impl Default for MetricsRegistry {
    fn default() -> Self {
        Self::new()
    }
}

/// Summary of key metrics
#[derive(Debug, Clone, serde::Serialize)]
pub struct MetricsSummary {
    pub constitutional_hash: String,
    pub total_validations: u64,
    pub total_violations: u64,
    pub messages_processed: u64,
    pub avg_latency_ms: f64,
    pub p99_latency_ms: f64,
    pub cache_hit_rate: f64,
    pub prompt_injections_blocked: u64,
}

/// Global metrics instance
pub static METRICS: Lazy<MetricsRegistry> = Lazy::new(MetricsRegistry::new);

/// Timer guard for automatic latency measurement
pub struct Timer<'a> {
    histogram: &'a Histogram,
    start: Instant,
}

impl<'a> Timer<'a> {
    pub fn new(histogram: &'a Histogram) -> Self {
        Self {
            histogram,
            start: Instant::now(),
        }
    }
}

impl<'a> Drop for Timer<'a> {
    fn drop(&mut self) {
        self.histogram.observe_duration(self.start.elapsed());
    }
}

/// Convenience macro for timing operations
#[macro_export]
macro_rules! time_operation {
    ($histogram:expr, $block:expr) => {{
        let _timer = $crate::metrics::Timer::new($histogram);
        $block
    }};
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_counter() {
        let counter = Counter::new();
        assert_eq!(counter.get(), 0);
        counter.inc();
        assert_eq!(counter.get(), 1);
        counter.inc_by(5);
        assert_eq!(counter.get(), 6);
    }

    #[test]
    fn test_histogram() {
        let hist = Histogram::new_latency();
        hist.observe(0.5);
        hist.observe(1.0);
        hist.observe(5.0);

        assert!(hist.avg_ms() > 0.0);
        assert!(hist.p99_ms() <= 100.0);
    }

    #[test]
    fn test_prometheus_export() {
        let registry = MetricsRegistry::new();
        registry.constitutional_validations.inc();
        registry.cache_hits.inc_by(100);
        registry.cache_misses.inc_by(10);

        let output = registry.to_prometheus();
        assert!(output.contains("acgs_constitutional_validations"));
        assert!(output.contains(CONSTITUTIONAL_HASH));
    }

    #[test]
    fn test_summary() {
        let registry = MetricsRegistry::new();
        registry.constitutional_validations.inc_by(1000);
        registry.constitutional_violations.inc_by(5);
        registry.cache_hits.inc_by(950);
        registry.cache_misses.inc_by(50);

        let summary = registry.summary();
        assert_eq!(summary.total_validations, 1000);
        assert!((summary.cache_hit_rate - 0.95).abs() < 0.01);
    }
}
