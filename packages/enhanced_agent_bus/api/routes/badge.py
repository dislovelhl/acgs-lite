"""
ACGS-2 Badge Endpoint
Constitutional Hash: 608508a9bd224290

GET /v1/badge/{agent_id} — returns an SVG compliance badge.
No authentication required. Cached for 5 minutes.
"""

from fastapi import APIRouter, Request
from fastapi.responses import Response

from ..badge_generator import generate_badge_svg
from ..rate_limiting import limiter

router = APIRouter(prefix="/v1", tags=["badge"])
BADGE_CACHE_CONTROL = {"Cache-Control": "max-age=300, public"}
BADGE_MEDIA_TYPE = "image/svg+xml"
BADGE_LABEL = "ACGS"
DEFAULT_BADGE_SCORE = 1.0


@router.get("/badge/{agent_id}")
@limiter.limit("60/minute")
async def get_badge(request: Request, agent_id: str) -> Response:
    """
    Return an SVG compliance badge for the given agent.

    The badge shows the agent's current governance compliance score
    in shields.io flat style, suitable for embedding in README files.
    """
    agent_id = agent_id.strip()
    return Response(
        content=generate_badge_svg(label=BADGE_LABEL, score=DEFAULT_BADGE_SCORE, message=agent_id),
        media_type=BADGE_MEDIA_TYPE,
        headers=BADGE_CACHE_CONTROL,
    )
