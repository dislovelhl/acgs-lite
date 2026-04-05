# Security Headers Middleware - Quick Start Guide

> **Constitutional Hash**: `608508a9bd224290`

## 5-Minute Integration Guide

### Step 1: Import the Middleware

```python
from shared.security import SecurityHeadersConfig, SecurityHeadersMiddleware
```

### Step 2: Choose Your Configuration

```python
# For most production services
config = SecurityHeadersConfig.for_production()

# For services with webhooks/external APIs
config = SecurityHeadersConfig.for_integration_service()

# For services with WebSocket connections
config = SecurityHeadersConfig.for_websocket_service()

# For development/local testing
config = SecurityHeadersConfig.for_development()
```

### Step 3: Add to FastAPI App (AFTER CORS)

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# 1. CORS first
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)

# 2. Security headers second
app.add_middleware(SecurityHeadersMiddleware, config=config)
```

### Step 4: Verify with cURL

```bash
curl -I http://localhost:8000/health | grep -i "x-content-type\|x-frame\|x-xss\|strict-transport\|content-security\|referrer"
```

You should see all 6 headers:

- `Content-Security-Policy`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Strict-Transport-Security`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`

## Complete Example

```python
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from shared.security import SecurityHeadersConfig, SecurityHeadersMiddleware

app = FastAPI(title="My Service")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers middleware
environment = os.getenv("APP_ENV", "production")
if environment == "development":
    security_config = SecurityHeadersConfig.for_development()
else:
    security_config = SecurityHeadersConfig.for_production()

app.add_middleware(SecurityHeadersMiddleware, config=security_config)

@app.get("/health")
async def health():
    return {"status": "healthy"}
```

## Testing

```bash
# Run tests
cd src/core
pytest shared/security/tests/test_security_headers.py -v

# Run your service integration tests
pytest tests/test_security_headers.py -v
```

## Custom CSP Example

```python
# Allow external CDN
custom_csp = {
    "script-src": ["'self'", "https://cdn.example.com"],
    "img-src": ["'self'", "data:", "https://images.example.com"]
}

config = SecurityHeadersConfig(
    environment="production",
    custom_csp_directives=custom_csp
)
```

## Troubleshooting

**Headers not appearing?**

- Check middleware is AFTER CORS
- Verify import path is correct
- Check FastAPI startup logs

**CSP blocking resources?**

- Check browser console for violations
- Add required sources to custom_csp_directives
- Use for_websocket_service() for WebSocket apps

**Can't access localhost HTTP?**

- Use for_development() to disable HSTS
- Set environment to "development"

## Full Documentation

See [src/core/docs/security/SECURITY_HEADERS.md](../../docs/security/SECURITY_HEADERS.md) for:

- Complete configuration options
- Environment-specific behavior
- Custom CSP directives
- Testing approach
- Verification checklist
- Troubleshooting guide

## Questions?

Contact the ACGS-2 Security Team or refer to:

- Full docs: `src/core/docs/security/SECURITY_HEADERS.md`
- Source code: `src/core/shared/security/security_headers.py`
- Tests: `src/core/shared/security/tests/test_security_headers.py`
