"""
ACGS-2 Embeddable Widget JS Endpoint
Constitutional Hash: 608508a9bd224290

GET /v1/widget.js — returns a self-contained JavaScript snippet
that renders a floating governance compliance badge.
"""

from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter(prefix="/v1", tags=["widget"])
WIDGET_CACHE_CONTROL = {"Cache-Control": "max-age=300, public"}
WIDGET_MEDIA_TYPE = "application/javascript"

WIDGET_JS_TEMPLATE = """\
(function(){
  const doc = document;
  const script = doc.currentScript ?? doc.querySelector('script[data-agent-id]');
  if (!script) return;

  const attrOrDefault = (name, fallback) => script.getAttribute(name) || fallback;
  const agentId = attrOrDefault('data-agent-id', 'default');
  const position = attrOrDefault('data-position', 'bottom-right');
  const theme = attrOrDefault('data-theme', 'dark');
  const host = (script.src || '').replace(/\\/v1\\/widget\\.js.*/, '');

  const verticalStyle = position.includes('bottom') ? 'bottom:16px;' : 'top:16px;';
  const horizontalStyle = position.includes('right') ? 'right:16px;' : 'left:16px;';
  const themeStyles = {
    light: 'filter:none;',
    dark: 'filter:drop-shadow(0 1px 3px rgba(0,0,0,0.3));',
  };
  const themeStyle = themeStyles[theme] || themeStyles.dark;

  const container = doc.createElement('div');
  container.id = 'acgs-widget';
  container.style.cssText = `position:fixed;z-index:9999;${verticalStyle}${horizontalStyle}`;

  const link = doc.createElement('a');
  link.href = `${host}/dashboard`;
  link.target = '_blank';
  link.rel = 'noopener';
  link.title = 'ACGS Governance';
  link.style.cssText = 'display:block;text-decoration:none;';

  const image = doc.createElement('img');
  image.src = `${host}/v1/badge/${encodeURIComponent(agentId)}`;
  image.alt = 'ACGS Compliance';
  image.style.cssText = `height:20px;border-radius:3px;${themeStyle}`;

  link.appendChild(image);
  container.appendChild(link);
  doc.body.appendChild(container);
})();
"""


@router.get("/widget.js")
async def get_widget_js() -> Response:
    """
    Return a self-contained JavaScript snippet for embedding
    the ACGS governance badge as a floating widget.

    Configure via data attributes on the script tag:
    - data-agent-id: Agent identifier for the badge
    - data-position: bottom-right | bottom-left | top-right | top-left
    - data-theme: dark | light
    """
    return Response(
        content=WIDGET_JS_TEMPLATE,
        media_type=WIDGET_MEDIA_TYPE,
        headers=WIDGET_CACHE_CONTROL,
    )
