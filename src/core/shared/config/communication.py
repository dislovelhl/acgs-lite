# mypy: disable-error-code="no-redef"
"""Communication configuration: SMTP.

Constitutional Hash: cdd01ef066bc6cf2
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

    class SMTPSettings(BaseSettings):
        """SMTP email delivery settings."""

        host: str = Field("localhost", validation_alias="SMTP_HOST")
        port: int = Field(587, validation_alias="SMTP_PORT")
        username: str | None = Field(None, validation_alias="SMTP_USERNAME")
        password: SecretStr | None = Field(None, validation_alias="SMTP_PASSWORD")
        use_tls: bool = Field(True, validation_alias="SMTP_USE_TLS")
        use_ssl: bool = Field(False, validation_alias="SMTP_USE_SSL")
        from_email: str = Field("noreply@example.com", validation_alias="SMTP_FROM_EMAIL")
        from_name: str = Field("ACGS-2 Audit Service", validation_alias="SMTP_FROM_NAME")
        timeout: float = Field(30.0, validation_alias="SMTP_TIMEOUT")
        enabled: bool = Field(False, validation_alias="SMTP_ENABLED")

else:
    from dataclasses import dataclass, field

    @dataclass
    class SMTPSettings:  # type: ignore[no-redef]
        """SMTP email delivery settings (dataclass fallback)."""

        host: str = field(default_factory=lambda: os.getenv("SMTP_HOST", "localhost"))
        port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587")))
        username: str | None = field(default_factory=lambda: os.getenv("SMTP_USERNAME"))
        password: SecretStr | None = field(
            default_factory=lambda: (
                SecretStr(os.getenv("SMTP_PASSWORD", "")) if os.getenv("SMTP_PASSWORD") else None
            )
        )
        use_tls: bool = field(
            default_factory=lambda: os.getenv("SMTP_USE_TLS", "true").lower() == "true"
        )
        use_ssl: bool = field(
            default_factory=lambda: os.getenv("SMTP_USE_SSL", "false").lower() == "true"
        )
        from_email: str = field(
            default_factory=lambda: os.getenv("SMTP_FROM_EMAIL", "noreply@example.com")
        )
        from_name: str = field(
            default_factory=lambda: os.getenv("SMTP_FROM_NAME", "ACGS-2 Audit Service")
        )
        timeout: float = field(default_factory=lambda: float(os.getenv("SMTP_TIMEOUT", "30.0")))
        enabled: bool = field(
            default_factory=lambda: os.getenv("SMTP_ENABLED", "false").lower() == "true"
        )
