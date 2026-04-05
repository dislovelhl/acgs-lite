# mypy: disable-error-code="no-redef"
"""Operations and observability configuration: Telemetry, AWS, Quality.

Constitutional Hash: 608508a9bd224290
"""

import os
from typing import Final

from pydantic import Field, SecretStr

try:
    from pydantic_settings import BaseSettings

    HAS_PYDANTIC_SETTINGS: Final[bool] = True
except ImportError:
    HAS_PYDANTIC_SETTINGS: Final[bool] = False  # type: ignore[misc]
    from pydantic import BaseModel as BaseSettings  # type: ignore[assignment]


if HAS_PYDANTIC_SETTINGS:

    class TelemetrySettings(BaseSettings):
        """OpenTelemetry and observability settings."""

        otlp_endpoint: str = Field(
            "http://localhost:4317", validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT"
        )
        service_name: str = Field("acgs2", validation_alias="OTEL_SERVICE_NAME")
        export_traces: bool = Field(True, validation_alias="OTEL_EXPORT_TRACES")
        export_metrics: bool = Field(True, validation_alias="OTEL_EXPORT_METRICS")
        trace_sample_rate: float = Field(0.1, validation_alias="OTEL_TRACE_SAMPLE_RATE")

    class AWSSettings(BaseSettings):
        """AWS/S3 storage settings (supports MinIO for local development)."""

        access_key_id: SecretStr | None = Field(None, validation_alias="AWS_ACCESS_KEY_ID")
        secret_access_key: SecretStr | None = Field(None, validation_alias="AWS_SECRET_ACCESS_KEY")
        region: str = Field("us-east-1", validation_alias="AWS_REGION")
        s3_endpoint_url: str | None = Field(None, validation_alias="S3_ENDPOINT_URL")

    class QualitySettings(BaseSettings):
        """Code quality and SonarQube settings."""

        sonarqube_url: str = Field("http://localhost:9000", validation_alias="SONARQUBE_URL")
        sonarqube_token: SecretStr | None = Field(None, validation_alias="SONARQUBE_TOKEN")
        enable_local_analysis: bool = Field(True, validation_alias="QUALITY_ENABLE_LOCAL_ANALYSIS")

else:
    from dataclasses import dataclass, field

    @dataclass
    class TelemetrySettings:  # type: ignore[no-redef]
        """OpenTelemetry tracing and metrics export settings (dataclass fallback)."""

        otlp_endpoint: str = field(
            default_factory=lambda: os.getenv(
                "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
            )
        )
        service_name: str = field(default_factory=lambda: os.getenv("OTEL_SERVICE_NAME", "acgs2"))
        export_traces: bool = field(
            default_factory=lambda: os.getenv("OTEL_EXPORT_TRACES", "true").lower() == "true"
        )
        export_metrics: bool = field(
            default_factory=lambda: os.getenv("OTEL_EXPORT_METRICS", "true").lower() == "true"
        )
        trace_sample_rate: float = field(
            default_factory=lambda: float(os.getenv("OTEL_TRACE_SAMPLE_RATE", "0.1"))
        )

    @dataclass
    class AWSSettings:  # type: ignore[no-redef]
        """AWS credentials and S3 configuration settings (dataclass fallback)."""

        access_key_id: SecretStr | None = field(
            default_factory=lambda: (
                SecretStr(os.getenv("AWS_ACCESS_KEY_ID", ""))
                if os.getenv("AWS_ACCESS_KEY_ID")
                else None
            )
        )
        secret_access_key: SecretStr | None = field(
            default_factory=lambda: (
                SecretStr(os.getenv("AWS_SECRET_ACCESS_KEY", ""))
                if os.getenv("AWS_SECRET_ACCESS_KEY")
                else None
            )
        )
        region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))
        s3_endpoint_url: str | None = field(default_factory=lambda: os.getenv("S3_ENDPOINT_URL"))

    @dataclass
    class QualitySettings:  # type: ignore[no-redef]
        """Code quality and SonarQube integration settings (dataclass fallback)."""

        sonarqube_url: str = field(
            default_factory=lambda: os.getenv("SONARQUBE_URL", "http://localhost:9000")
        )
        sonarqube_token: SecretStr | None = field(
            default_factory=lambda: (
                SecretStr(os.getenv("SONARQUBE_TOKEN", ""))
                if os.getenv("SONARQUBE_TOKEN")
                else None
            )
        )
        enable_local_analysis: bool = field(
            default_factory=lambda: (
                os.getenv("QUALITY_ENABLE_LOCAL_ANALYSIS", "true").lower() == "true"
            )
        )
