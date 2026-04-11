"""Pre-built governance workflow templates.

Templates are YAML files compilable via GovernanceWorkflowCompiler.
Use list_workflow_templates() to discover available templates.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from pathlib import Path

_TEMPLATE_DIR = Path(__file__).parent

_TEMPLATES = {
    "action_validation": _TEMPLATE_DIR / "action_validation.yaml",
    "compliance_assessment": _TEMPLATE_DIR / "compliance_assessment.yaml",
    "agent_onboarding": _TEMPLATE_DIR / "agent_onboarding.yaml",
}


def list_workflow_templates() -> dict[str, Path]:
    """Return mapping of template name → YAML path for all built-in templates."""
    return {name: path for name, path in _TEMPLATES.items() if path.exists()}
