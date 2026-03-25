# Constitutional Sentinel — Demo Video Script

**Target: 2:35–2:50** (stay safely under the 3 minute cap)

---

## SECTION 1: Hook + Problem (0:00 – 0:20)

### Show
- Title slide: **"AI wrote the merge request. Who governs the merge?"**
- Optional quick flash of GitLab MR page

### Say
> "AI coding agents can open merge requests fast, but they do not understand your security rules, compliance requirements, or separation-of-duties policies.
>
> Constitutional Sentinel is a GitLab governance agent that reviews AI-generated merge requests, flags risky code inline, and blocks unsafe merges before they reach production."

---

## SECTION 2: Show the MR and inline violations (0:20 – 1:00)

### Show
1. Open MR !1: `https://gitlab.com/martin664/constitutional-sentinel-demo/-/merge_requests/1`
2. Go to **Changes**
3. Pause on 3 concrete findings:
   - hardcoded secret
   - SSN / PII pattern
   - destructive SQL

### Say
> "Here is a merge request generated with intentionally unsafe content.
>
> Constitutional Sentinel inspects the diff automatically and leaves inline governance comments exactly where the violations occur.
>
> In this demo it catches a hardcoded credential, exposed PII, and destructive SQL. Instead of giving a vague warning, it points to the exact lines that need to change."

---

## SECTION 3: Governance summary + merge blocking (1:00 – 1:35)

### Show
1. Scroll to MR discussion / governance summary
2. Zoom in on:
   - risk score
   - violation count
   - constitutional hash
   - blocked / failed result

### Say
> "The Sentinel also posts a governance summary back to the merge request.
>
> It reports the overall risk, lists the violations, and includes a constitutional hash — a fingerprint of the exact ruleset used for this decision.
>
> If the violations are severe enough, the Sentinel fails the governance step and the merge should not proceed."

---

## SECTION 4: Explain the architecture simply (1:35 – 2:10)

### Show
Architecture slide:
- GitLab MR event
- Constitutional Sentinel on Cloud Run
- ACGS-Lite engine
- inline comments + governance summary back to GitLab
- human decides whether to merge

### Say
> "The workflow is simple. A GitLab merge request event triggers Constitutional Sentinel.
>
> Sentinel runs the diff through ACGS-Lite using a YAML constitution of governance rules, then posts inline findings and a governance report back to GitLab.
>
> The key design principle is separation of powers: the AI that proposes code is not the system that validates it, and a human remains the final executor."

---

## SECTION 5: Close with why it matters (2:10 – 2:35)

### Show
- Return to MR with visible inline comments and report
- Optional final slide: **"Governance for AI-generated code"**

### Say
> "This project turns AI code governance from an afterthought into an active GitLab workflow.
>
> Constitutional Sentinel reacts to merge request events, reviews AI-generated code, blocks unsafe changes, and leaves a tamper-evident audit trail.
>
> That means safer AI-assisted development with visible, enforceable governance inside the developer workflow."

---

## KEY STATS (for Q&A, not all required in narration)

| Topic | Stat |
|-------|------|
| Demo MR | 12 violations caught |
| Eval suite | 30/30 hackathon evals passing |
| Roles | Proposer → Validator → Executor |
| Deploy | Cloud Run |
| Rules | YAML constitution |
| Auditability | Constitutional hash + audit trail |

## PRE-RECORDING CHECKLIST

- [ ] MR !1 is public and loads cleanly
- [ ] Inline comments are visible in the Changes view
- [ ] Governance summary is visible in discussion
- [ ] Browser zoom set for readability
- [ ] Notifications silenced
- [ ] Only relevant tabs open
- [ ] Architecture slide/image ready
- [ ] Final export under 3:00
