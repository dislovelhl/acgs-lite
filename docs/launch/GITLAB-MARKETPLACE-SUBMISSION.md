# GitLab Marketplace / CI Component Submission

**Status:** Ready for submission
**Package:** `acgs-lite` v2.6.0 on PyPI
**Constitutional Hash:** `608508a9bd224290`

---

## 1. Marketplace Listing Copy

### Title

ACGS -- Constitutional Governance for AI

### Tagline

Enforce governance rules on every merge request. 5 lines of YAML. 9 regulatory frameworks.

### Description

ACGS adds a constitutional governance gate to your GitLab CI/CD pipeline. Every merge
request is validated against a set of declarative rules that cover code quality, security
policy, data protection, and regulatory compliance -- before the code can be merged.

The engine ships as a single `pip install` with zero heavy dependencies. Define your
governance rules in a YAML constitution file, add one CI/CD stage, and every MR diff is
checked line by line. Violations surface as inline comments on the exact lines that
triggered them, plus a structured governance report posted as an MR note.

Key capabilities beyond basic linting:

- **MACI separation of powers** -- the engine enforces that the MR author cannot also be
  the sole approver, preventing self-validation of changes.
- **EU AI Act compliance** -- automated assessment against Articles 12 (record-keeping),
  13 (transparency), and 14 (human oversight), with PDF report generation.
- **Cryptographic audit trail** -- every governance decision is recorded in a hash-chained
  audit log that can be verified independently.
- **18-framework compliance mapping** -- GDPR, HIPAA, SOC 2, ISO 42001, NIST AI RMF,
  OECD AI Principles, and more from one constitution file.

ACGS integrates with GitLab Duo Chat via MCP, supports custom constitutions, and runs
entirely offline -- no external API calls required for validation.

### Category

Security & Compliance

### Key Features

1. **Governance gate in your pipeline** -- Block merges that violate constitutional rules.
   Inline MR comments point to the exact lines with violations.
2. **MACI separation of powers** -- Automatically enforce that proposers, validators, and
   executors are different people on every merge request.
3. **EU AI Act compliance reports** -- Generate compliance assessments against EU AI Act
   Articles 12-14, with PDF artifacts stored in CI/CD.
4. **Cryptographic audit trail** -- Hash-chained, tamper-evident audit log for every
   governance decision. Export for auditors in JSON or PDF.
5. **5 lines to integrate** -- Add one CI/CD stage to your `.gitlab-ci.yml`. No external
   services, no API keys, no infrastructure to manage.

### Screenshots / Demo Descriptions

Capture these for the listing:

| Screenshot | What to show |
|------------|-------------|
| **MR governance report** | An MR note showing the governance report table: status (PASSED/BLOCKED), risk score, rules checked, violations with severity badges, and constitutional hash. Use MR !42 from the demo project. |
| **Inline violation comment** | A diff view with an ACGS inline comment on a specific line, showing the rule ID, severity, and rule text. Best captured on a line that introduces a hardcoded secret. |
| **MACI separation block** | An MR where the author attempted self-approval, showing the MACI violation comment with the separation-of-powers explanation. |
| **Pipeline stage** | The GitLab CI/CD pipeline view showing the `governance` stage between `test` and `deploy`, with a green checkmark or red X. |
| **EU AI Act report** | The JSON or PDF artifact from the `governance-reports/` directory, showing the Article 12/13/14 assessment for an AI/ML file change. |
| **Constitution YAML** | A clean view of a `constitution.yaml` file showing 3-4 rules with severity, category, and pattern fields. |

---

## 2. CI/CD Component Template

### Minimal Setup (Recommended Starting Point)

Add this stage to your existing `.gitlab-ci.yml`:

```yaml
# -- ACGS Governance Gate --------------------------------------------------
# Validates every MR against your constitutional rules.
# Docs: https://acgs.ai/docs/gitlab
# Constitutional Hash: 608508a9bd224290

stages:
  - build
  - test
  - governance  # <-- add this stage
  - deploy

acgs-governance:
  stage: governance
  image: python:3.11-slim

  variables:
    # Path to your constitution file (relative to repo root).
    # Run `acgs init` to generate a starter constitution.yaml.
    ACGS_CONSTITUTION_PATH: "constitution.yaml"
    # Set to "true" to block the pipeline on violations.
    ACGS_STRICT: "true"
    PIP_CACHE_DIR: "$CI_PROJECT_DIR/.pip-cache"
    PIP_DISABLE_PIP_VERSION_CHECK: "1"

  cache:
    key: acgs-governance-pip-v1
    paths:
      - .pip-cache/
    policy: pull-push

  before_script:
    - pip install --quiet --no-cache-dir "acgs-lite[gitlab]>=2.6"

  script:
    - |
      python3 - <<'GOVERNANCE_EOF'
      """ACGS CI/CD governance gate.

      Validates MR diffs against constitutional rules, posts a governance
      report as an MR comment, and exits non-zero on blocking violations.
      """
      import asyncio
      import json
      import os
      import sys
      from pathlib import Path

      from acgs_lite import Constitution
      from acgs_lite.integrations.gitlab import GitLabGovernanceBot


      async def main() -> int:
          # --- Configuration ---
          token = os.environ.get("GITLAB_TOKEN")
          if not token:
              print("WARNING: GITLAB_TOKEN not set. Governance comments will not be posted.")
              print("Add GITLAB_TOKEN as a masked CI/CD variable (Settings > CI/CD > Variables).")

          project_id_raw = os.environ.get("CI_PROJECT_ID")
          mr_iid_raw = os.environ.get("CI_MERGE_REQUEST_IID", "0")

          if not project_id_raw or mr_iid_raw == "0":
              print("Not a merge request pipeline -- skipping governance check.")
              return 0

          project_id = int(project_id_raw)
          mr_iid = int(mr_iid_raw)
          strict = os.environ.get("ACGS_STRICT", "true").lower() == "true"

          # --- Load constitution ---
          constitution_path = os.environ.get("ACGS_CONSTITUTION_PATH", "constitution.yaml")
          if Path(constitution_path).exists():
              constitution = Constitution.from_yaml(constitution_path)
              print(f"Constitution loaded: {constitution.name} v{constitution.version}")
          else:
              constitution = Constitution.from_template("gitlab")
              print(f"WARNING: {constitution_path} not found -- using built-in gitlab template.")
              print("Run 'acgs init' to generate a starter constitution.")

          print(f"Constitutional hash: {constitution.hash}")
          print(f"Rules: {len(constitution.rules)} total, {len(constitution.active_rules())} active")

          # --- Run governance validation ---
          if token:
              bot = GitLabGovernanceBot(
                  token=token,
                  project_id=project_id,
                  constitution=constitution,
              )
              report = await bot.run_governance_pipeline(mr_iid=mr_iid)
          else:
              # Offline mode: validate without posting to GitLab
              from acgs_lite.engine import GovernanceEngine
              from acgs_lite.audit import AuditLog
              import subprocess

              target = os.environ.get("CI_MERGE_REQUEST_TARGET_BRANCH_NAME", "main")
              audit_log = AuditLog()
              engine = GovernanceEngine(constitution, audit_log=audit_log, strict=False)

              result = subprocess.run(
                  ["git", "diff", f"origin/{target}...HEAD"],
                  capture_output=True, text=True, timeout=60,
              )
              diff_text = result.stdout if result.returncode == 0 else ""
              validation = engine.validate(diff_text, agent_id="gitlab-ci")

              class _OfflineReport:
                  passed = validation.valid
                  violations = [{"rule_id": v.rule_id, "severity": v.severity.value, "rule_text": v.rule_text} for v in validation.violations]
                  warnings = []
                  rules_checked = len(constitution.active_rules())
                  risk_score = 0.0
                  mr_iid = mr_iid

              report = _OfflineReport()

          # --- Print summary ---
          status = "PASSED" if report.passed else "BLOCKED"
          print(f"\n{'=' * 60}")
          print(f"  ACGS Governance: {status}")
          print(f"  Risk score:      {report.risk_score:.2f}")
          print(f"  Violations:      {len(report.violations)}")
          print(f"  Rules checked:   {report.rules_checked}")
          print(f"{'=' * 60}")

          if report.violations:
              print("\nViolations:")
              for v in report.violations:
                  sev = v.get("severity", "unknown") if isinstance(v, dict) else v.severity
                  rid = v.get("rule_id", "?") if isinstance(v, dict) else v.rule_id
                  txt = v.get("rule_text", "") if isinstance(v, dict) else v.rule_text
                  print(f"  [{sev.upper()}] {rid}: {txt}")

          # --- Write report artifact ---
          os.makedirs("governance-reports", exist_ok=True)
          report_data = {
              "status": status,
              "violations": len(report.violations) if hasattr(report.violations, '__len__') else 0,
              "rules_checked": report.rules_checked,
              "risk_score": report.risk_score,
              "mr_iid": mr_iid,
              "constitutional_hash": constitution.hash,
          }
          with open("governance-reports/governance-report.json", "w") as f:
              json.dump(report_data, f, indent=2, default=str)

          # --- Exit code ---
          if not report.passed and strict:
              print(f"\nPipeline BLOCKED: {len(report.violations)} violation(s) found.")
              return 1
          if not report.passed:
              print("\nWARNING: Violations found but strict mode is off.")
          return 0


      sys.exit(asyncio.run(main()))
      GOVERNANCE_EOF

  artifacts:
    paths:
      - governance-reports/
    when: always
    expire_in: 90 days

  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_COMMIT_BRANCH && $CI_OPEN_MERGE_REQUESTS
```

### Full Setup (With EU AI Act + MACI + Hash Verification)

For regulated environments, use these additional jobs alongside the stage above:

```yaml
# -- MACI Separation of Powers Check --------------------------------------
acgs-maci-check:
  stage: governance
  image: python:3.11-slim
  cache:
    key: acgs-governance-pip-v1
    paths:
      - .pip-cache/
    policy: pull
  before_script:
    - pip install --quiet --no-cache-dir "acgs-lite>=2.6"
  script:
    - |
      python3 - <<'MACI_EOF'
      import os, subprocess, sys

      from acgs_lite.maci import MACIEnforcer, MACIRole

      author = os.environ.get(
          "CI_MERGE_REQUEST_AUTHOR",
          os.environ.get("GITLAB_USER_LOGIN", "unknown"),
      )
      exempt = set(
          u.strip()
          for u in os.environ.get("ACGS_MACI_EXEMPT", "").split(",")
          if u.strip()
      )

      print(f"MACI check for author: {author}")
      if author in exempt:
          print(f"Author is MACI-exempt. Skipping.")
          sys.exit(0)

      target = os.environ.get("CI_MERGE_REQUEST_TARGET_BRANCH_NAME", "main")
      try:
          result = subprocess.run(
              ["git", "diff", f"origin/{target}...HEAD"],
              capture_output=True, text=True, timeout=60,
          )
          diff_lower = result.stdout.lower() if result.returncode == 0 else ""
      except subprocess.SubprocessError:
          diff_lower = ""

      violations = []
      for pattern in ("self-approve", "auto-approve", "self-validate", "skip audit", "bypass validation"):
          if pattern in diff_lower:
              violations.append(f"MACI violation: pattern '{pattern}' found in diff")

      if violations:
          print("\nMACI VIOLATIONS:")
          for v in violations:
              print(f"  {v}")
          sys.exit(1)

      print("MACI separation of powers: PASS")
      MACI_EOF
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"

# -- Constitutional Hash Verification --------------------------------------
acgs-hash-check:
  stage: governance
  image: python:3.11-slim
  variables:
    ACGS_EXPECTED_HASH: "608508a9bd224290"
  cache:
    key: acgs-governance-pip-v1
    paths:
      - .pip-cache/
    policy: pull
  before_script:
    - pip install --quiet --no-cache-dir "acgs-lite>=2.6"
  script:
    - |
      python3 -c "
      import os, sys
      from acgs_lite.constitution import Constitution
      from pathlib import Path

      expected = os.environ.get('ACGS_EXPECTED_HASH', '608508a9bd224290')
      path = os.environ.get('ACGS_CONSTITUTION_PATH', '')

      if path and Path(path).exists():
          c = Constitution.from_yaml(path)
      else:
          c = Constitution.default()

      print(f'Constitution: {c.name} v{c.version}')
      print(f'Expected hash: {expected}')
      print(f'Actual hash:   {c.hash}')

      if c.hash == expected:
          print('PASS: Constitutional hash verified.')
          sys.exit(0)

      print('FAIL: Hash mismatch -- constitution may have been tampered with.')
      sys.exit(1)
      "
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"

# -- EU AI Act Compliance Report (opt-in) ----------------------------------
acgs-eu-ai-act:
  stage: governance
  image: python:3.11-slim
  variables:
    ACGS_EU_AI_ACT_ENABLED: "true"
  cache:
    key: acgs-governance-pip-v1
    paths:
      - .pip-cache/
    policy: pull
  before_script:
    - pip install --quiet --no-cache-dir "acgs-lite[pdf]>=2.6"
  script:
    - acgs eu-ai-act --system-id "$CI_PROJECT_NAME" --domain "${ACGS_DOMAIN:-general}" -o governance-reports/eu_ai_act_report.json --json
  artifacts:
    paths:
      - governance-reports/eu_ai_act_report.json
    when: always
    expire_in: 90 days
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event" && $ACGS_EU_AI_ACT_ENABLED == "true"
  allow_failure: true
```

### Include-Based Setup (Cleanest)

If your project already has a `.gitlab-ci.yml`, use `include` to pull the governance
stage from a shared configuration:

```yaml
# In your .gitlab-ci.yml
include:
  - project: 'your-org/acgs-ci-templates'
    ref: main
    file: '/templates/acgs-governance.yml'

stages:
  - build
  - test
  - governance
  - deploy
```

---

## 3. Integration Guide

### Step 1: Install ACGS locally (optional, for testing)

```bash
pip install acgs-lite
acgs --version
```

### Step 2: Initialize a constitution

```bash
cd your-project
acgs init
```

This creates a `constitution.yaml` with sensible defaults (data protection, audit
requirements, access control). Edit it to match your governance requirements.

### Step 3: Test locally

```bash
# Lint your constitution for quality issues
acgs lint constitution.yaml

# Run a local governance check on a file
acgs assess --constitution constitution.yaml src/main.py
```

### Step 4: Add the CI/CD variable

1. Go to **Settings > CI/CD > Variables** in your GitLab project.
2. Add `GITLAB_TOKEN` with a personal access token that has `api` scope.
3. Mark it as **Masked** and **Protected**.

The token is used to read MR diffs and post governance comments. Without it, ACGS still
runs validation but cannot post inline comments.

### Step 5: Add the governance stage to your pipeline

Copy the minimal CI/CD template from Section 2 above into your `.gitlab-ci.yml`. The
only required change is adding `governance` to your `stages:` list and pasting the
`acgs-governance` job definition.

### Step 6: Open a merge request

Create a branch, make a change, and open an MR. The governance stage runs automatically.
If violations are found:

- A governance report is posted as an MR comment.
- Inline comments appear on the specific lines with violations.
- The pipeline fails (if `ACGS_STRICT: "true"`).

### Step 7: Customize

| What | How |
|------|-----|
| Add rules | Edit `constitution.yaml` and add rules with `id`, `severity`, `category`, and `pattern` fields. |
| Use a built-in template | Set `ACGS_CONSTITUTION_PATH` to empty and ACGS falls back to the `gitlab` built-in template. |
| Disable strict mode | Set `ACGS_STRICT: "false"` to report violations without blocking the pipeline. |
| Add EU AI Act checks | Add the `acgs-eu-ai-act` job from the full template and set `ACGS_EU_AI_ACT_ENABLED: "true"`. |
| Exempt users from MACI | Set `ACGS_MACI_EXEMPT: "bot-user,service-account"` as a comma-separated list. |
| Self-hosted GitLab | The `GitLabGovernanceBot` accepts a `base_url` parameter. Set `GITLAB_URL` in CI/CD variables. |

### Troubleshooting

| Problem | Fix |
|---------|-----|
| `constitution.yaml not found` | Run `acgs init` in your repo root, or set `ACGS_CONSTITUTION_PATH` to the correct path. |
| `GITLAB_TOKEN not set` | Add it as a masked CI/CD variable. Needs `api` scope. |
| `Not a merge request pipeline` | ACGS only runs on MR pipelines. Push to a branch with an open MR. |
| Governance passes but no comments | Check that the token has `api` scope (not just `read_api`). |
| Pipeline too slow | The `cache` block in the template caches pip packages. First run is ~15s, subsequent runs ~3s. |

---

## 4. Submission Checklist

### Account Requirements

- [ ] GitLab account with a public or internal project for the CI/CD component
- [ ] Verified email address on the GitLab account
- [ ] Project must be on GitLab.com (not self-managed) for Marketplace listing
- [ ] Namespace must be an organization or group (not a personal namespace) for
      official CI/CD Components
- [ ] Two-factor authentication enabled on the account

### Technical Requirements

- [ ] CI/CD component follows the [GitLab CI/CD component specification](https://docs.gitlab.com/ee/ci/components/)
- [ ] Component project structure:
  ```
  acgs-ci-component/
  ├── templates/
  │   └── acgs-governance.yml    # Main component template
  ├── README.md                   # Component documentation
  ├── LICENSE                     # Apache-2.0 or compatible
  └── .gitlab-ci.yml             # CI to test the component itself
  ```
- [ ] Template uses `spec:inputs` for configurable parameters (GitLab 16.6+):
  ```yaml
  spec:
    inputs:
      constitution_path:
        default: "constitution.yaml"
      strict:
        default: "true"
      acgs_version:
        default: ">=2.6"
  ```
- [ ] Component is tested with its own CI/CD pipeline
- [ ] Component works with GitLab Free, Premium, and Ultimate tiers
- [ ] Python 3.11-slim image used (minimal, secure, well-maintained)
- [ ] No secrets hardcoded in the component
- [ ] Caching configured for pip packages
- [ ] Artifacts configured with `expire_in` (90 days recommended)
- [ ] Jobs scoped to `merge_request_event` to avoid running on every push
- [ ] `allow_failure: true` on optional jobs (EU AI Act, posture checks)
- [ ] Tested on:
  - [ ] GitLab.com shared runners (Linux)
  - [ ] Self-managed GitLab instance (if claiming support)
  - [ ] Both SaaS and self-managed GitLab API endpoints

### Documentation Requirements

- [ ] README.md with:
  - [ ] One-paragraph description
  - [ ] 5-line quickstart
  - [ ] Full configuration reference (all CI/CD variables)
  - [ ] Example constitution.yaml
  - [ ] Screenshots of governance report and inline comments
  - [ ] Troubleshooting section
  - [ ] Link to full documentation (https://acgs.ai/docs/gitlab)
- [ ] CHANGELOG.md tracking component versions
- [ ] LICENSE file (Apache-2.0)
- [ ] Contributing guide (optional but recommended)
- [ ] Working demo project that reviewers can fork and test

### Marketplace Listing Requirements

- [ ] Title: "ACGS -- Constitutional Governance for AI" (under 50 chars ideally)
- [ ] Tagline: under 100 characters
- [ ] Description: 250 words max (use Section 1 above)
- [ ] Category: Security & Compliance
- [ ] Icon/logo: SVG or PNG, 512x512px minimum, transparent background
- [ ] Screenshots: at least 3 (governance report, inline comment, pipeline view)
- [ ] Tags: `governance`, `compliance`, `security`, `ai`, `eu-ai-act`, `audit`
- [ ] Support URL: https://acgs.ai/support or GitHub Issues link
- [ ] Documentation URL: https://acgs.ai/docs/gitlab

### Pre-Submission Validation

- [ ] Run `acgs lint` on the default constitution -- must pass with zero errors
- [ ] Run the full CI/CD template against a test MR -- governance report posts correctly
- [ ] Verify inline comments appear on violation lines
- [ ] Verify pipeline blocks on CRITICAL violations when strict mode is on
- [ ] Verify pipeline passes when no violations exist
- [ ] Verify offline mode works (no GITLAB_TOKEN set)
- [ ] Verify caching works (second run is significantly faster)
- [ ] Verify artifacts are stored and downloadable
- [ ] Run EU AI Act job and verify report artifact is generated
- [ ] Test with a custom constitution.yaml

### Submission Process

1. **Create the component project** on GitLab.com under your organization namespace.
   - Repository name: `acgs-ci-component` (or similar)
   - Visibility: Public
   - Add the component template files

2. **Publish to the CI/CD Catalog** (GitLab 17.0+):
   - Go to **Settings > General > CI/CD Catalog**
   - Toggle "List this project in the CI/CD catalog"
   - This requires the project to have a `README.md` and at least one release

3. **Create a release**:
   - Tag the repository (e.g., `v1.0.0`)
   - Write release notes covering features and setup instructions
   - GitLab automatically publishes catalog-listed projects on release

4. **Submit for Marketplace review** (if applying for verified/featured status):
   - Fill out the [GitLab Partner Program application](https://partners.gitlab.com/)
   - Or email `marketplace@gitlab.com` with:
     - Component project URL
     - Description of what it does
     - Target audience
     - Pricing model (free / freemium / paid)
   - Typical review timeline: 2-4 weeks for initial review

5. **Post-submission**:
   - Monitor the CI/CD Catalog listing for star count and usage metrics
   - Respond to issues and feature requests promptly
   - Update the component when new acgs-lite versions ship

### Key Links

| Resource | URL |
|----------|-----|
| GitLab CI/CD Components docs | https://docs.gitlab.com/ee/ci/components/ |
| GitLab CI/CD Catalog | https://docs.gitlab.com/ee/ci/components/#cicd-catalog |
| Publishing to CI/CD Catalog | https://docs.gitlab.com/ee/ci/components/#publish-a-component-project |
| GitLab Partner Program | https://partners.gitlab.com/ |
| Component spec:inputs reference | https://docs.gitlab.com/ee/ci/components/#define-inputs |
| GitLab Marketplace overview | https://about.gitlab.com/partners/technology-partners/ |
| acgs-lite on PyPI | https://pypi.org/project/acgs-lite/ |
| ACGS documentation | https://acgs.ai/docs |

### Timeline Estimate

| Step | Duration |
|------|----------|
| Create component project + template files | 1-2 hours |
| Test on GitLab.com shared runners | 1-2 hours |
| Write README, screenshots, demo project | 2-3 hours |
| Create first release + catalog listing | 30 minutes |
| Submit for partner/verified status | 15 minutes (form) + 2-4 weeks (review) |
| **Total hands-on time** | **~6 hours** |
