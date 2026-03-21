# ACGS-2 API Gateway Service

**Constitutional Hash**: `cdd01ef066bc6cf2`

## Overview

The API Gateway service serves as the central entry point for all external API requests to the ACGS-2 platform. It provides request routing, load balancing, authentication, rate limiting, and centralized logging for all microservices.

## Architecture

The API Gateway implements a reverse proxy pattern with the following components:

- **Request Routing**: Intelligent routing based on path patterns and service availability
- **Load Balancing**: Round-robin distribution across service instances
- **Authentication**: JWT token validation and user context propagation
- **Rate Limiting**: Configurable rate limits per endpoint and user
- **Request Transformation**: Header manipulation and request enrichment
- **Centralized Logging**: Structured logging for all API requests
- **Health Monitoring**: Service health checks and circuit breaker patterns

## API Endpoints

### Health Checks

- `GET /health` - Service health status
- `GET /health/live` - Kubernetes liveness probe
- `GET /health/ready` - Kubernetes readiness probe

### API Routes

- `GET /api/v1/*` - Forwarded to appropriate microservices
- `POST /api/v1/*` - Forwarded to appropriate microservices
- `PUT /api/v1/*` - Forwarded to appropriate microservices
- `DELETE /api/v1/*` - Forwarded to appropriate microservices

### WorkOS SSO Operations

- `POST /api/v1/admin/sso/workos/portal-links` - Generate WorkOS Admin Portal links (admin-only)
- `GET /api/v1/admin/sso/workos/events` - Pull WorkOS events via cursor (admin-only)
- `POST /api/v1/sso/workos/webhooks/events` - Ingest and verify WorkOS webhooks

## Configuration

### Environment Variables

| Variable                            | Default                 | Description                                      |
| ----------------------------------- | ----------------------- | ------------------------------------------------ |
| `API_GATEWAY_PORT`                  | `8080`                  | Port to listen on                                |
| `AGENT_BUS_URL`                     | `http://localhost:8000` | Agent bus service URL                            |
| `TENANT_MANAGEMENT_URL`             | `http://localhost:8500` | Tenant management URL                            |
| `AUDIT_SERVICE_URL`                 | `http://localhost:8300` | Audit service URL                                |
| `REDIS_URL`                         | `redis://redis:6379/0`  | Redis connection URL                             |
| `RATE_LIMIT_REQUESTS`               | `100`                   | Requests per minute limit                        |
| `JWT_SECRET`                        | Required                | JWT signing secret                               |
| `WORKOS_ENABLED`                    | `false`                 | Enable WorkOS integration endpoints              |
| `WORKOS_CLIENT_ID`                  | None                    | WorkOS client ID                                 |
| `WORKOS_API_KEY`                    | None                    | WorkOS server API key                            |
| `WORKOS_WEBHOOK_SECRET`             | None                    | WorkOS webhook signing secret                    |
| `WORKOS_WEBHOOK_DEDUPE_TTL_SECONDS` | `86400`                 | Replay/idempotency key TTL for webhook event IDs |
| `WORKOS_WEBHOOK_FAIL_CLOSED`        | `false`                 | Return non-2xx when audit forwarding fails       |

### Routing Configuration

Routes are configured via environment variables or configuration files:

```python
ROUTES = {
    "/api/v1/agents": "agent-bus:8000",
    "/api/v1/tenants": "tenant-management:8500",
    "/api/v1/audit": "audit-service:8300",
}
```

## Development

### Local Development Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run from repo root
python start_api_gateway.py

# Or run with uvicorn from repo root
python -m uvicorn src.core.services.api_gateway.main:app --reload --port 8080

# Run tests
pytest tests/
```

### Docker Development

```bash
# Build and run
docker build -f Dockerfile.dev -t acgs2-api-gateway .
docker run -p 8080:8080 acgs2-api-gateway
```

## Deployment

### Docker Compose

```yaml
api-gateway:
  build:
    context: ./services/api_gateway
    dockerfile: Dockerfile.dev
  ports:
    - "8080:8080"
  environment:
    - API_GATEWAY_PORT=8080
    - AGENT_BUS_URL=http://agent-bus:8000
  depends_on:
    - agent-bus
    - redis
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-gateway
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api-gateway
  template:
    metadata:
      labels:
        app: api-gateway
    spec:
      containers:
        - name: api-gateway
          image: acgs2/api-gateway:latest
          ports:
            - containerPort: 8080
          env:
            - name: API_GATEWAY_PORT
              value: "8080"
          livenessProbe:
            httpGet:
              path: /health/live
              port: 8080
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 5
```

## Monitoring

### Metrics

The service exposes Prometheus metrics at `/metrics`:

- `api_gateway_requests_total` - Total requests processed
- `api_gateway_requests_duration` - Request duration histogram
- `api_gateway_active_connections` - Current active connections
- `api_gateway_rate_limit_exceeded` - Rate limit violations

### Logging

All requests are logged with structured logging including:

- Request ID for tracing
- User ID and tenant context
- Request method and path
- Response status code
- Request duration
- Error details (if applicable)

## Security

### Authentication

- JWT token validation for protected endpoints
- Token refresh handling
- User context propagation to downstream services

### Authorization

- Role-based access control (RBAC)
- Service-level permissions
- Tenant isolation enforcement

### Rate Limiting

- Configurable limits per endpoint
- Burst handling with token bucket algorithm
- Automatic retry with exponential backoff

## Testing

### Unit Tests

```bash
pytest tests/test_routing.py -v
pytest tests/test_auth.py -v
pytest tests/test_rate_limiting.py -v
```

### Integration Tests

```bash
pytest tests/integration/ -v
```

### Load Testing

```bash
# Using locust or similar
locust -f tests/load/locustfile.py
```

## Troubleshooting

### Common Issues

1. **502 Bad Gateway**: Check if downstream services are healthy
2. **429 Too Many Requests**: Review rate limiting configuration
3. **401 Unauthorized**: Verify JWT token validity
4. **504 Gateway Timeout**: Check service response times

### Debug Mode

Enable debug logging:

```bash
export LOG_LEVEL=DEBUG
uvicorn main:app --reload --log-level debug
```

## Contributing

Follow the ACGS-2 service development guidelines in the main repository documentation.

## License

This service is part of the ACGS-2 platform and follows the same license terms.
