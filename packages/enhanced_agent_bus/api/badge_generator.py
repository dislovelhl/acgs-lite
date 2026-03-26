"""
ACGS-2 Badge SVG Generator
Constitutional Hash: 608508a9bd224290

Generates shields.io-style SVG badges for governance compliance scores.
"""

from xml.sax.saxutils import escape

SCORE_COLORS: tuple[tuple[float, str], ...] = (
    (0.9, "#4c1"),  # bright green
    (0.7, "#a3c51c"),  # yellow-green
    (0.5, "#dfb317"),  # yellow
    (0.3, "#fe7d37"),  # orange
)
LOWEST_SCORE_COLOR = "#e05d44"  # red
TEXT_CHAR_WIDTH = 6.5
TEXT_PADDING = 10


def _score_to_color(score: float) -> str:
    """Map a compliance score [0.0, 1.0] to a hex color."""
    for threshold, color in SCORE_COLORS:
        if score >= threshold:
            return color
    return LOWEST_SCORE_COLOR


def _score_label(score: float) -> str:
    """Human-readable label for a score."""
    pct = int(score * 100)
    return f"{pct}%"


def generate_badge_svg(
    label: str = "ACGS",
    score: float = 1.0,
    message: str | None = None,
) -> str:
    """
    Generate a shields.io-style flat SVG badge.

    Args:
        label: Left-side label text.
        score: Compliance score [0.0, 1.0].
        message: Right-side message (defaults to score percentage).

    Returns:
        SVG string.
    """
    score = max(0.0, min(1.0, score))
    color = _score_to_color(score)
    msg = escape(message or _score_label(score))
    lbl = escape(label)

    label_width = len(lbl) * TEXT_CHAR_WIDTH + TEXT_PADDING
    msg_width = len(msg) * TEXT_CHAR_WIDTH + TEXT_PADDING
    total_width = label_width + msg_width

    return f"""\
<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20" role="img" \
aria-label="{lbl}: {msg}">
  <title>{lbl}: {msg}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="{total_width}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_width}" height="20" fill="#555"/>
    <rect x="{label_width}" width="{msg_width}" height="20" fill="{color}"/>
    <rect width="{total_width}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" \
font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" \
font-size="11">
    <text aria-hidden="true" x="{label_width / 2}" y="15" fill="#010101" \
fill-opacity=".3">{lbl}</text>
    <text x="{label_width / 2}" y="14">{lbl}</text>
    <text aria-hidden="true" x="{label_width + msg_width / 2}" y="15" fill="#010101" \
fill-opacity=".3">{msg}</text>
    <text x="{label_width + msg_width / 2}" y="14">{msg}</text>
  </g>
</svg>"""
