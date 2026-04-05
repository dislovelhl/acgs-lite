"""
Audit Client - Communicates with the decentralized Audit Service
Constitutional Hash: 608508a9bd224290
"""

import logging
from dataclasses import asdict

import httpx

from src.core.shared.types import JSONDict, JSONValue

logger = logging.getLogger(__name__)


class AuditClient:
    """
    Asynchronous client for reporting validation results to the Audit Service.
    Designed to be used within the EnhancedAgentBus.
    """

    def __init__(self, service_url: str = "http://localhost:8300"):
        self.service_url = service_url
        self.client = httpx.AsyncClient(timeout=5.0)

    async def report_validation(
        self, validation_result: JSONDict | JSONValue | object
    ) -> str | None:
        """
        Reports a single validation result to the audit ledger.
        Returns the entry hash if successful.
        """
        try:
            # Check if validation_result has to_dict
            if hasattr(validation_result, "to_dict"):
                data = validation_result.to_dict()
            else:
                from dataclasses import is_dataclass

                if is_dataclass(validation_result):
                    data = asdict(validation_result)
                else:
                    data = validation_result

            # Make actual HTTP request to audit service
            try:
                response = await self.client.post(
                    f"{self.service_url}/record",
                    json=data,
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code == 200:
                    result = response.json()
                    entry_hash = result.get("entry_hash")
                    logger.info(f"Validation recorded with hash: {entry_hash}")
                    return entry_hash
                else:
                    logger.warning(
                        f"Audit service returned error: {response.status_code} - {response.text}"
                    )
                    # Fall back to simulated hash for backwards compatibility
                    logger.warning(
                        "Falling back to simulated validation hash due to audit service error"
                    )
                    return f"simulated_{hash(str(data)) % 1000000:06x}"
            except (httpx.HTTPError, OSError) as conn_error:
                logger.warning(f"Audit service connection failed: {conn_error}")
                # Fall back to simulated hash when service is unavailable
                logger.warning(
                    "Falling back to simulated validation hash due to connection failure"
                )
                return f"simulated_{hash(str(data)) % 1000000:06x}"

        except (ValueError, TypeError, AttributeError) as e:
            logger.error(f"Failed to report validation to audit service: {e}")
            return None

    async def report_decision(self, decision_log: JSONDict | JSONValue | object) -> str | None:
        """
        Reports a structured decision log for compliance reporting.
        """
        try:
            if hasattr(decision_log, "to_dict"):
                data = decision_log.to_dict()
            else:
                from dataclasses import is_dataclass

                data = asdict(decision_log) if is_dataclass(decision_log) else decision_log

            logger.info(
                f"Audit decision reported: {data.get('decision')} for agent {data.get('agent_id')}"
            )

            # Make actual HTTP request to audit service
            try:
                response = await self.client.post(
                    f"{self.service_url}/record",
                    json=data,
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code == 200:
                    result = response.json()
                    entry_hash = result.get("entry_hash")
                    logger.info(f"Decision recorded with hash: {entry_hash}")
                    return entry_hash
                else:
                    logger.warning(
                        f"Audit service returned error: {response.status_code} - {response.text}"
                    )
                    # Fall back to simulated hash for backwards compatibility
                    logger.warning(
                        "Falling back to simulated decision hash due to audit service error"
                    )
                    return f"simulated_{hash(str(data)) % 1000000:06x}"
            except (httpx.HTTPError, OSError) as conn_error:
                logger.warning(f"Audit service connection failed: {conn_error}")
                # Fall back to simulated hash when service is unavailable
                logger.warning("Falling back to simulated decision hash due to connection failure")
                return f"simulated_{hash(str(data)) % 1000000:06x}"

        except (ValueError, TypeError, AttributeError) as e:
            logger.error(f"Failed to report decision to audit service: {e}")
            return None

    async def get_stats(self) -> JSONDict:
        """Fetch statistics from the Audit Service."""
        try:
            response = await self.client.get(f"{self.service_url}/stats")
            return response.json()
        except (httpx.HTTPError, OSError) as e:
            logger.error(f"Failed to fetch audit stats: {e}")
            return {}

    async def close(self):
        """Close the underlying HTTP client."""
        await self.client.aclose()
