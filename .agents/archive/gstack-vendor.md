## Archived: Vendored `gstack` Skill Bundle

Reason archived:
- It was a third-party, repo-external skill system vendored directly into `.agents/skills/`.
- It exposed 26 active repo-local skill entrypoints via symlinks even though they were not
  ACGS-specific workflows.
- It added a second instruction universe, telemetry behavior, templates, and an embedded `.git`
  checkout, which reduced signal and increased maintenance cost.
- The vendored tree size was approximately `459M`.

Removed active paths:
- `.agents/skills/gstack/`
- the top-level symlinked skills that pointed into that tree

Restore source:
- Upstream: `https://github.com/garrytan/gstack.git`
- Archived commit: `aa7daf052ece077ab3d05da3834ad7a029b79bc9`

If ACGS ever needs one of those workflows again, re-import it intentionally as either:
- a user-wide/global Codex skill, or
- a small repo-local skill rewritten for this repository's actual workflow.
