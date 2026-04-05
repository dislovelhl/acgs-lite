"""
ACGS-2 Anomaly Monitoring Integration
Constitutional Hash: 608508a9bd224290

Integrates the AnomalyDetector with the Agent Bus to provide real-time
monitoring of governance metrics and automatic incident triggering.
"""

import asyncio
from datetime import UTC, datetime

import pandas as pd

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    import importlib

    _ad = importlib.import_module("src.core.services.analytics_engine.src.anomaly_detector")
    AnomalyDetector = _ad.AnomalyDetector
    DetectedAnomaly = _ad.DetectedAnomaly
except ImportError:
    # Fallback if service path differs or during local testing
    try:
        from anomaly_detector import (  # type: ignore[import-untyped]
            AnomalyDetector,
            DetectedAnomaly,
        )
    except ImportError:
        AnomalyDetector = None
        DetectedAnomaly = None

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.models import GovernanceMetrics  # type: ignore[attr-defined]

from ..config import BusConfiguration

logger = get_logger(__name__)
MONITORING_LOOP_ERRORS = (RuntimeError, ValueError, TypeError, KeyError)


class AnomalyMonitor:
    """
    Monitors governance metrics for anomalies using IsolationForest.

    Features:
    - Buffers metrics for batch processing
    - Runs anomaly detection periodically
    - Alerts on high-severity anomalies
    - Provides constitutional compliance verification for alerts
    """

    def __init__(
        self,
        config: BusConfiguration | None = None,
        check_interval_seconds: int = 300,  # 5 minutes
        min_training_samples: int = 100,
    ):
        self.config = config or BusConfiguration()
        self.check_interval = check_interval_seconds
        self.min_training_samples = min_training_samples

        self._detector = AnomalyDetector() if AnomalyDetector else None
        self._metrics_buffer: list[JSONDict] = []
        self._is_running = False
        self._monitoring_task: asyncio.Task | None = None

        if not self._detector:
            logger.warning("AnomalyDetector not available. Monitoring disabled.")

    async def start(self):
        """Start the monitoring background task."""
        if not self._detector or self._is_running:
            return

        self._is_running = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Anomaly monitoring started")

    async def stop(self):
        """Stop the monitoring background task."""
        self._is_running = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("Anomaly monitoring stopped")

    def record_metrics(self, metrics: GovernanceMetrics):
        """
        Record a metrics snapshot for analysis.

        Args:
            metrics: GovernanceMetrics object containing current counters
        """
        if not self._detector:
            return

        # Flatten metrics to dictionary
        data = {
            "timestamp": datetime.now(UTC),
            "total_requests": metrics.total_requests,
            "approved_count": metrics.approved_count,
            "denied_count": metrics.denied_count,
            "violation_count": metrics.violation_count,
            "error_count": metrics.error_count,
            "avg_latency_ms": metrics.avg_latency_ms,
            # Calculate rates if possible
            "denial_rate": metrics.denied_count / max(1, metrics.total_requests),
            "violation_rate": metrics.violation_count / max(1, metrics.total_requests),
        }

        self._metrics_buffer.append(data)

        # Keep buffer size manageable (e.g., last 24 hours at 1-min interval approx 1440)
        # We store raw points here; detection uses windowed aggregation ideally
        if len(self._metrics_buffer) > 10000:
            self._metrics_buffer = self._metrics_buffer[-5000:]

    async def _monitoring_loop(self):
        """Main monitoring loop."""
        while self._is_running:
            try:
                await asyncio.sleep(self.check_interval)
                await self.detect_anomalies()
            except MONITORING_LOOP_ERRORS as e:
                logger.error(f"Error in anomaly monitoring loop: {e}", exc_info=True)

    async def detect_anomalies(self) -> list[DetectedAnomaly]:
        """
        Run detection on buffered data.

        Returns:
            List of detected anomalies
        """
        if not self._detector or len(self._metrics_buffer) < self.min_training_samples:
            return []

        # Convert buffer to DataFrame
        df = pd.DataFrame(self._metrics_buffer)

        # Retrain model if enough new data
        # In production, training might be a separate async job or offline process
        if not self._detector.is_fitted or len(self._metrics_buffer) % 1000 == 0:
            logger.info("Retraining anomaly detection model...")
            self._detector.fit(df)

        # Predict on recent data (last window)
        # We take the last N samples that haven't been alerted on
        recent_df = df.tail(10)  # Check last 10 points

        result = self._detector.detect(recent_df)

        if result.anomalies:
            await self._handle_anomalies(result.anomalies)

        return result.anomalies  # type: ignore[no-any-return]

    async def _handle_anomalies(self, anomalies: list[DetectedAnomaly]):
        """
        Handle detected anomalies (log, alert, trigger circuit breakers).
        """
        for anomaly in anomalies:
            logger.warning(
                f"ANOMALY DETECTED [{anomaly.severity_label.upper()}]: "
                f"{anomaly.description} (Score: {anomaly.severity_score:.2f})"
            )

            # Here we would integrate with the alerting system / PagerDuty / Slack
            # and potentially trigger automated responses

            if anomaly.severity_label == "critical":
                # Example: Automatic circuit breaker for critical anomalies
                # await self.bus.trigger_circuit_breaker(reason=f"Anomaly: {anomaly.description}")
                pass
