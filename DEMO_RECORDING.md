# Demo Recording Guide — ACGS-Auth0 Hackathon Submission
> Deadline: April 6, 2026 | Target length: 2–3 minutes

## Setup (5 min)

```bash
# Install OBS or use asciinema (terminal-only, simplest)
pip install asciinema          # terminal recording
# OR use OBS Studio if you want webcam + narration

cd /home/martin/Documents/acgs-clean
```

## Script (follow exactly — 3 acts)

### Act 1 — The Problem (30 sec narration while showing code)

Open `examples/governed_agents/constitutions/default.yaml` in an editor.
**Say**: "Today's AI agents get a token and use it however they want.
ACGS-Auth0 puts a constitution between the agent and the token.
The YAML you're looking at is that constitution — it declares exactly
which roles can request which scopes."

Point to this section:
```yaml
EXECUTIVE:
  permitted_scopes: ["read:user", "repo:read"]
IMPLEMENTER:
  permitted_scopes: ["repo:read", "repo:write"]
  high_risk_scopes: ["repo:write"]
# JUDICIAL intentionally absent — validators never call external APIs
```

### Act 2 — The Demo (90 sec — run the demo live)

```bash
python examples/governed_agents/main.py
```

As output scrolls, narrate each section:

1. **✅ EXECUTIVE read → granted**
   "The planner agent requests read access. Constitutional gate passes."

2. **🚫 EXECUTIVE write → denied**
   "Same agent requests write. The constitution says no. Blocked before
   it ever reaches Auth0 Token Vault."

3. **🚫 JUDICIAL → blocked entirely**
   "The validator agent tries to read GitHub. The MACI Golden Rule:
   validators never touch external APIs. Separation of powers enforced."

4. **🟡 IMPLEMENTER write → CIBA step-up**
   "The executor agent requests write access. Constitutional gate passes —
   but write is high-risk, so Auth0 CIBA sends a push notification to
   the user's Guardian app before the token is released."

5. **📋 Audit trail**
   "Every decision — granted, denied, step-up — recorded with
   constitutional hash 608508a9bd224290. Immutable. Attributable."

### Act 3 — The Insight (20 sec)

**Say**: "Auth0 Token Vault secures how credentials are stored and exchanged.
ACGS-Auth0 answers the prior question: should this agent be constitutionally
permitted to ask for these credentials at all?
That's not a security question. It's a governance question.
And it belongs in a constitution — not in agent code."

Show the PyPI badge or run:
```bash
pip install acgs-auth0
```

## Recording Commands

```bash
# Option A: Terminal recording (simplest, no setup)
asciinema rec acgs-auth0-demo.cast
python examples/governed_agents/main.py
# Ctrl+D to stop

# Play back to review:
asciinema play acgs-auth0-demo.cast

# Convert to video for upload (requires asciinema2gif or svg-term):
# OR upload the .cast file directly to asciinema.org → share link

# Option B: Screen record with audio (OBS or Loom)
# Start recording → run demo → narrate → stop → export MP4 → upload to YouTube unlisted
```

## Upload & Link

1. Upload to YouTube (unlisted) or asciinema.org
2. Paste the URL into Devpost under "Demo Video"
3. Update HACKATHON.md line 206 with the actual URL

## Submission Checklist (Final)

- [x] Auth0 Token Vault integration
- [x] CIBA step-up for high-risk scopes
- [x] MACI role-based scope policies
- [x] Constitutional audit trail
- [x] auth0-ai-langchain integration
- [x] 51 unit tests passing
- [x] Working demo (`python examples/governed_agents/main.py`)
- [x] Public GitHub repo: https://github.com/dislovelhl/acgs
- [x] README with setup instructions
- [x] Bonus blog post (in HACKATHON.md)
- [x] asyncio deprecation fixed (commit 1fa7da172)
- [ ] **Demo video — RECORD NOW**
- [ ] Paste video URL into Devpost
