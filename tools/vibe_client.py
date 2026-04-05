"""
Vibe client for ACGS — wraps Mistral Vibe programmatic API for governed codebase tasks.

Usage:
    from tools.vibe_client import VibeClient

    client = VibeClient()
    result = client.explore("Using grep: find all files that import from acgs_lite.engine")
    cost = client.last_cost  # float, dollars
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# Vibe lives in its own uv-managed venv
VIBE_SITE_PACKAGES = Path.home() / ".local/share/uv/tools/mistral-vibe/lib/python3.13/site-packages"


@dataclass
class VibeResult:
    response: str | None
    cost: float
    prompt_tokens: int
    completion_tokens: int
    duration_s: float


class VibeClient:
    """Thin wrapper around Mistral Vibe programmatic API."""

    def __init__(self, workdir: str | Path | None = None) -> None:
        self._workdir = Path(workdir or Path.cwd())
        self._initialized = False
        self._config = None

    def _ensure_init(self) -> None:
        if self._initialized:
            return

        # Add vibe to path if needed
        vibe_path = str(VIBE_SITE_PACKAGES)
        if vibe_path not in sys.path:
            sys.path.insert(0, vibe_path)

        # Load env
        env_file = Path.home() / ".vibe/.env"
        if env_file.exists():
            from dotenv import load_dotenv

            load_dotenv(env_file)

        from vibe.core.config import VibeConfig
        from vibe.core.config.harness_files import init_harness_files_manager

        init_harness_files_manager(Path.home() / ".vibe")

        config = VibeConfig.load()
        self._config = config.model_copy(
            update={
                "include_commit_signature": False,
                "include_model_info": False,
            }
        )
        self._initialized = True

    def _run(self, prompt: str, agent: str = "explore", max_turns: int = 10) -> VibeResult:
        import time

        self._ensure_init()

        cwd_before = Path.cwd()
        os.chdir(self._workdir)

        try:
            from vibe.core.programmatic import run_programmatic

            start = time.time()
            response = run_programmatic(
                config=self._config,
                prompt=prompt,
                max_turns=max_turns,
                agent_name=agent,
            )
            duration = time.time() - start
        finally:
            os.chdir(cwd_before)

        # Read cost from most recent session log
        cost = prompt_tokens = completion_tokens = 0
        logs = sorted(
            (Path.home() / ".vibe/logs/session").glob("*/meta.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if logs:
            meta = json.loads(logs[-1].read_text())
            stats = meta.get("stats", {})
            cost = stats.get("session_cost", 0.0)
            prompt_tokens = stats.get("session_prompt_tokens", 0)
            completion_tokens = stats.get("session_completion_tokens", 0)

        return VibeResult(
            response=response,
            cost=cost,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_s=duration,
        )

    def explore(self, task: str, max_turns: int = 10) -> VibeResult:
        """Read-only exploration task. Always prefixes with tool use instruction."""
        prompt = f"Using grep and read_file tools: {task}"
        return self._run(prompt, agent="acgs-explorer", max_turns=max_turns)

    def audit(self, task: str, max_turns: int = 15) -> VibeResult:
        """Security/compliance audit task."""
        prompt = f"Using grep and read_file tools: {task}"
        return self._run(prompt, agent="acgs-audit", max_turns=max_turns)
