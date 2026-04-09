"""Display-only rule rendering helpers for constitutional text interpolation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .interpolation import render_constitution

if TYPE_CHECKING:
    from .constitution import Constitution


def render(constitution: Constitution, context: dict[str, Any]) -> Constitution:
    """Return a copy of *constitution* with rule text placeholders resolved."""
    return render_constitution(constitution, context)


def explain_rendered(
    constitution: Constitution,
    action: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Explain an action using rendered rule text."""
    rendered = render(constitution, context)
    return rendered.explain(action)
