# Security Best Practices Report

Executive summary: the three findings identified in the initial review have now been remediated in code. The API gateway now enforces CSRF protection for session-backed browser flows, the shared FastAPI bootstrap enforces trusted hosts, and validation errors no longer reflect raw request bodies.

## Remediation Status

### SEC-001
- Status: Remediated
- Severity: Critical
- Title: Session-authenticated admin routes lacked CSRF protection
- Original risk: browser-authenticated admins could be exposed to CSRF on state-changing routes that relied on the session cookie.
- Remediation:
  - The gateway now installs `CSRFMiddleware` immediately after `SessionMiddleware` at `src/core/services/api_gateway/main.py:182-209`.
  - The middleware is configured to enforce CSRF only when the `acgs2_session` cookie is present, which protects browser session flows without breaking stateless or bearer-token requests at `src/core/shared/security/csrf.py:46-75` and `src/core/shared/security/csrf.py:144-184`.
  - Protocol-required cross-site endpoints are explicitly exempted: SAML ACS, SAML SLS, and the WorkOS webhook at `src/core/services/api_gateway/main.py:193-207`.
- Verification:
  - `src/core/shared/security/tests/test_csrf.py:11-93` covers CSRF cookie issuance, rejection of session-backed POSTs without the CSRF header, acceptance of matching tokens, stateless bypass, and exempt webhook behavior.
- Residual notes:
  - Browser clients that use session auth for state-changing requests now need to send the `X-CSRF-Token` header with the value from the `csrf_token` cookie.

### SEC-002
- Status: Remediated
- Severity: Medium
- Title: Trusted host configuration existed but host header validation was not enforced
- Original risk: forged `Host` headers could influence URL generation, redirects, cache behavior, and other host-sensitive logic.
- Remediation:
  - The shared app factory now normalizes trusted hosts and installs `TrustedHostMiddleware` at `src/core/shared/fastapi_base.py:16-37` and `src/core/shared/fastapi_base.py:67-72`.
  - The API gateway now passes `settings.security.trusted_hosts` into the shared app factory at `src/core/services/api_gateway/main.py:102-112`.
  - Non-production environments automatically allow `testserver` so the test harness remains usable at `src/core/shared/fastapi_base.py:34-35`.
- Verification:
  - `src/core/shared/tests/test_fastapi_base.py:9-36` verifies that allowed hosts succeed, unexpected hosts are rejected with HTTP 400, and `testserver` is accepted in test environments.
- Residual notes:
  - Runtime deployments still need ingress and reverse-proxy configuration aligned with the application allowlist.

### SEC-003
- Status: Remediated
- Severity: Medium
- Title: Validation error responses reflected submitted request bodies, including secret-bearing admin payloads
- Original risk: invalid requests could echo sensitive request content, including secret material from admin SSO payloads, back to callers or downstream logging and monitoring systems.
- Remediation:
  - The common `RequestValidationError` handler now returns only `{"detail": exc.errors()}` and no longer includes the submitted body at `src/core/shared/fastapi_base.py:118-130`.
- Verification:
  - `src/core/shared/tests/test_fastapi_base.py:39-56` verifies that validation errors still return 422 with `detail`, but no longer return a `body` field.
- Residual notes:
  - If developers later add request echoing for debugging, it should remain disabled by default and require explicit non-production gating plus redaction.

## Verification Summary

Completed checks:
1. `python -m pytest --import-mode=importlib src/core/shared/security/tests/test_csrf.py`
2. `python -m pytest --import-mode=importlib src/core/shared/tests/test_fastapi_base.py src/core/shared/security/tests/test_csrf.py`
3. `python -m pytest --import-mode=importlib src/core/services/api_gateway/tests/test_workos.py`
4. `python -m ruff check src/core/shared/security/csrf.py src/core/services/api_gateway/main.py src/core/shared/fastapi_base.py src/core/shared/tests/test_fastapi_base.py src/core/shared/security/tests/test_csrf.py`

Known unrelated test issues encountered while verifying:
1. `src/core/services/api_gateway/tests/test_saml.py` fails during collection on this branch because it imports a missing `SAMLAuthenticationError`.
2. `src/core/services/api_gateway/tests/test_oidc.py` has pre-existing failures on this branch, including lifespan startup failures when `CONSTITUTIONAL_HASH` is not set for production-style startup and separate token-decoding expectation mismatches.

## Next Steps

1. If desired, clean up the unrelated OIDC/SAML test instability so the full gateway security regression suite can run green.
2. Keep the report updated as future security findings are fixed so it remains a current status document rather than a point-in-time audit.
