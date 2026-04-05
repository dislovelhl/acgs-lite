"""ClinicalGuard entrypoint.

Usage:
    uvicorn clinicalguard.main:app --host 0.0.0.0 --port 8080
    python -m clinicalguard.main

Environment variables:
    CLINICALGUARD_API_KEY      Required in production. Omit for local dev.
    CLINICALGUARD_AUDIT_LOG    Path to persist audit log JSON. Default: /tmp/clinicalguard_audit.json
    CLINICALGUARD_URL          Public URL for agent card. Default: http://localhost:8080
    PI_BINARY                  Path to pi binary. Default: pi (must be in PATH).

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from .agent import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

_audit_log_path = Path(
    os.environ.get("CLINICALGUARD_AUDIT_LOG", "/tmp/clinicalguard_audit.json")
)

app = create_app(audit_log_path=_audit_log_path)

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(
        "clinicalguard.main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
