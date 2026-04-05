"""Sandbox self-serve signup endpoint backed by an in-memory account store."""

import secrets
import threading
import time
from typing import TypedDict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from enhanced_agent_bus.observability.structured_logging import get_logger

from ..rate_limiting import limiter
from ..runtime_guards import require_sandbox_endpoint

logger = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["signup"])

FREE_TIER_LIMIT = 1000  # validations per month


class AccountRecord(TypedDict):
    """In-memory account record shape."""

    email: str
    plan: str
    monthly_limit: int
    used_this_month: int
    created_at: float


# In-memory store (production: Redis/PostgreSQL)
_accounts: dict[str, AccountRecord] = {}
_accounts_lock = threading.Lock()


def _reset_accounts() -> None:
    """Reset in-memory account store. Used by test fixtures."""
    with _accounts_lock:
        _accounts.clear()


def _check_production_guard() -> None:
    """Reject sandbox signup outside development-like environments."""
    require_sandbox_endpoint(
        "Signup endpoint",
        "it still issues API keys from an in-memory account store instead of persistent storage",
    )


class SignupRequest(BaseModel):
    """Signup request body."""

    email: EmailStr = Field(..., description="Developer email address")


class SignupResponse(BaseModel):
    """Signup response with API key and quickstart."""

    api_key: str
    email: str
    plan: str = "free"
    monthly_limit: int = FREE_TIER_LIMIT
    quickstart: str


def _generate_api_key() -> str:
    """Generate a prefixed API key."""
    return f"acgs_live_{secrets.token_hex(16)}"


def _email_already_registered(email: str) -> bool:
    """Check whether an account already exists for the email."""
    return any(account["email"] == email for account in _accounts.values())


def _build_account_record(email: str) -> AccountRecord:
    """Build a new free-tier account record."""
    return {
        "email": email,
        "plan": "free",
        "monthly_limit": FREE_TIER_LIMIT,
        "used_this_month": 0,
        "created_at": time.time(),
    }


def _build_quickstart(api_key: str) -> str:
    """Build quickstart snippet for new developers."""
    return (
        f"pip install acgs\n"
        f"from acgs import ACGS\n\n"
        f'client = ACGS(api_key="{api_key}")\n'
        f"result = await client.validate(\n"
        f'    agent_id="my-agent",\n'
        f'    action="send_message",\n'
        f'    context={{"target": "user"}},\n'
        f")\n"
        f'print(f"Compliant: {{result.compliant}}")'
    )


@router.post("/signup", response_model=SignupResponse)
@limiter.limit("10/minute")
async def signup(request: Request, body: SignupRequest) -> SignupResponse:
    """
    Create a free-tier developer account.

    Returns an API key instantly. No email verification required
    for the free tier. Key is valid for 1,000 validations/month.

    Rate limited to 10 requests per minute per client.
    """
    _check_production_guard()

    email = body.email.lower()

    with _accounts_lock:
        if _email_already_registered(email):
            raise HTTPException(
                status_code=409,
                detail="An account with this email already exists. Check your records for your API key.",
            )

        api_key = _generate_api_key()
        _accounts[api_key] = _build_account_record(email)

    logger.info("New developer signup: %s", email)

    return SignupResponse(
        api_key=api_key,
        email=email,
        quickstart=_build_quickstart(api_key),
    )


def get_account(api_key: str) -> AccountRecord | None:
    """Look up an account by API key. Returns None if not found."""
    with _accounts_lock:
        return _accounts.get(api_key)


def get_accounts_store() -> dict[str, AccountRecord]:
    """Return the accounts store (for testing)."""
    return _accounts
