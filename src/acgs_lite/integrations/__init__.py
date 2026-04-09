"""Integration adapters for third-party runtimes and services.

Import concrete adapters from their module paths, for example:

    from acgs_lite.integrations.openai import GovernedOpenAI
    from acgs_lite.integrations.anthropic import GovernedAnthropic

Keep this package initializer intentionally minimal so importing
`acgs_lite.integrations` does not accidentally duplicate or shadow a specific
integration module.
"""

from __future__ import annotations

__all__: list[str] = []
