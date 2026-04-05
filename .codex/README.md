# Codex Workspace

Repo-local Codex defaults live in `config.toml`.

Use:

```bash
make codex-doctor
```

This checks:
- `AGENTS.md`
- `PLANS.md`
- active repo-local skills in `.agents/skills/`
- `.codex/config.toml` presence and parseability

Keep user-wide trust levels, plugins, and personal defaults in `~/.codex/config.toml`.
