# Constitution Lifecycle HTTP API

The constitution lifecycle router exposes draft, review, evaluation, approval,
activation, rollback, and history over FastAPI under `/constitution/lifecycle`.

Use it when you want to manage `ConstitutionBundle` state transitions over HTTP
instead of calling `ConstitutionLifecycle` directly in-process.

## Enable the router

The lifecycle API is mounted by `acgs_lite.server.create_governance_app()`.

```python
from acgs_lite.server import create_governance_app

app = create_governance_app(
    include_lifecycle=True,
    lifecycle_api_key="dev-lifecycle-key",
)
```

You can also enable it with environment variables:

```bash
export ACGS_LIFECYCLE_ENABLED=1
export ACGS_LIFECYCLE_API_KEY=dev-lifecycle-key
```

## Authentication model

- **Mutation endpoints** require `X-API-Key` when a lifecycle key is configured.
- **Actor identity** comes from `X-Actor-ID`, not the request body.
- **Read endpoints** (`GET`) do not require the API key.
- If no lifecycle key is configured, auth is disabled. That is useful for tests,
  not for production.

Example headers:

```http
X-API-Key: dev-lifecycle-key
X-Actor-ID: reviewer-42
```

## Error envelope

Lifecycle errors use a structured `detail` payload:

```json
{
  "detail": {
    "error": "Invalid or missing API key",
    "code": "AUTH_REQUIRED",
    "bundle_id": null
  }
}
```

Common `code` values:

| Code | Meaning | Typical status |
| ---- | ------- | -------------- |
| `AUTH_REQUIRED` | Missing or invalid lifecycle API key | `401` |
| `ACTOR_REQUIRED` | Missing `X-Actor-ID` header | `400` |
| `NOT_FOUND` | Bundle or active tenant bundle was not found | `404` |
| `MACI_VIOLATION` | MACI role separation or self-approval rule failed | `403` |
| `CONCURRENT_CONFLICT` | CAS conflict during lifecycle transition | `409` |
| `LIFECYCLE_ERROR` | Domain rule rejected the transition | `400` |

## Bundle response shape

Most lifecycle endpoints return a serialized `ConstitutionBundle`.

```json
{
  "bundle_id": "b6b9d9aa-61ae-4c28-b630-6d8848f1d85f",
  "version": 1,
  "tenant_id": "acme",
  "constitutional_hash": "608508a9bd224290",
  "status": "draft",
  "proposed_by": "operator-1",
  "reviewed_by": null,
  "approved_by": null,
  "eval_run_ids": [],
  "eval_summary": {},
  "created_at": "2026-04-15T20:00:00Z"
}
```

The full payload also includes the embedded constitution, status history, and
activation metadata.

## Lifecycle overview

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `POST` | `/constitution/lifecycle/draft` | Create a draft bundle |
| `POST` | `/constitution/lifecycle/{bundle_id}/submit` | Move `draft -> review` |
| `POST` | `/constitution/lifecycle/{bundle_id}/review` | Reviewer sign-off, move `review -> eval` |
| `POST` | `/constitution/lifecycle/{bundle_id}/eval` | Run evaluation scenarios |
| `POST` | `/constitution/lifecycle/{bundle_id}/approve` | Final approval, move `eval -> staged` |
| `POST` | `/constitution/lifecycle/{bundle_id}/stage` | Canary/staging step |
| `POST` | `/constitution/lifecycle/{bundle_id}/activate` | Activate staged bundle |
| `POST` | `/constitution/lifecycle/{bundle_id}/rollback` | Roll back an active bundle |
| `POST` | `/constitution/lifecycle/{bundle_id}/withdraw` | Withdraw pre-activation bundle |
| `POST` | `/constitution/lifecycle/{bundle_id}/reject` | Reject a bundle (VALIDATOR role) |
| `GET` | `/constitution/lifecycle/{bundle_id}` | Fetch a bundle by id |
| `GET` | `/constitution/lifecycle/active/{tenant_id}` | Fetch tenant's active bundle |
| `GET` | `/constitution/lifecycle/history/{tenant_id}` | List bundle history for a tenant |

## Endpoint reference

### POST /constitution/lifecycle/draft

Creates a new draft bundle for a tenant. The proposer is taken from
`X-Actor-ID`.

#### Request body

| Name | Type | Required | Description |
| ---- | ---- | -------- | ----------- |
| `tenant_id` | string | Yes | Tenant that owns the draft |
| `name` | string | No | Human-friendly label |

```json
{
  "tenant_id": "acme",
  "name": "v2-rules"
}
```

#### Response

- `200` returns the new bundle with `status: "draft"`.

### POST /constitution/lifecycle/{bundle_id}/submit

Moves a bundle from `draft` to `review`.

#### Parameters

| Name | Type | Required | Description |
| ---- | ---- | -------- | ----------- |
| `bundle_id` | string | Yes | Bundle identifier |

#### Response

- `200` returns the updated bundle with `status: "review"`.
- `404` if the bundle does not exist.

### POST /constitution/lifecycle/{bundle_id}/review

Records reviewer sign-off and moves a bundle from `review` to `eval`.

#### Response

- `200` returns the updated bundle with `status: "eval"`.
- `403` on MACI violations.

### POST /constitution/lifecycle/{bundle_id}/eval

Runs evaluation scenarios against the bundle's constitution. Empty scenario
lists are rejected by the service layer.

#### Request body

| Name | Type | Required | Description |
| ---- | ---- | -------- | ----------- |
| `scenarios` | array | Yes | Non-empty list of eval scenarios |
| `pass_threshold` | float | No | Required passing fraction, default `1.0` |
| `eval_run_id` | string | No | Optional explicit eval run id |

```json
{
  "scenarios": [
    {
      "id": "s1",
      "input_action": "check current status of the system",
      "context": {
        "tenant_id": "acme"
      },
      "expected_valid": true
    }
  ],
  "pass_threshold": 1.0
}
```

#### Response

- `200` returns the bundle with updated `eval_run_ids` and `eval_summary`.
- `400` when the request violates lifecycle rules, including zero scenarios.

### POST /constitution/lifecycle/{bundle_id}/approve

Performs final approval after evaluation. The approver comes from
`X-Actor-ID`, which blocks body spoofing.

#### Request body

| Name | Type | Required | Description |
| ---- | ---- | -------- | ----------- |
| `signature` | string | Yes | Audit signature for approval |

```json
{
  "signature": "sha256:abcdef"
}
```

#### Response

- `200` returns the bundle after successful approval.
- `403` on MACI or self-approval violations.

### POST /constitution/lifecycle/{bundle_id}/stage

Runs the explicit staging step before activation. The caller identity comes
from `X-Actor-ID`.

#### Response

- `200` returns the staged bundle.

### POST /constitution/lifecycle/{bundle_id}/activate

Activates a staged bundle. Returns an activation record, not a bundle.

#### Response

- `200` returns the active bundle.

### POST /constitution/lifecycle/{bundle_id}/rollback

Rolls back an active bundle to its predecessor. Returns an activation record.

#### Request body

| Name | Type | Required | Description |
| ---- | ---- | -------- | ----------- |
| `reason` | string | No | Operator-visible rollback reason |

```json
{
  "reason": "operator rollback"
}
```

### POST /constitution/lifecycle/{bundle_id}/withdraw

Withdraws a bundle before activation.

#### Request body

| Name | Type | Required | Description |
| ---- | ---- | -------- | ----------- |
| `reason` | string | No | Why the proposer withdrew the bundle |

```json
{
  "reason": "withdrawn by proposer"
}
```

### POST /constitution/lifecycle/{bundle_id}/reject

Rejects a bundle. Requires **VALIDATOR** role (`X-Actor-ID` is treated as the validator).
Can be called on any pre-active bundle state.

#### Request body

| Name | Type | Required | Description |
| ---- | ---- | -------- | ----------- |
| `reason` | string | No | Why the validator rejected the bundle |

```json
{
  "reason": "rejected by validator"
}
```

#### Response

- `200` with the updated bundle (status `rejected`).
- `400` if the bundle is already in a terminal state.
- `403` on MACI violation.
- `404` if the bundle does not exist.

### GET /constitution/lifecycle/{bundle_id}

Returns a single bundle by id.

#### Response

- `200` with the serialized bundle.
- `404` if the bundle does not exist.

### GET /constitution/lifecycle/active/{tenant_id}

Returns the tenant's currently active bundle.

In addition to the normal bundle fields, this response includes:

| Name | Type | Description |
| ---- | ---- | ----------- |
| `engine_binding_active` | boolean | Whether Phase E engine binding is wired into request validation |
| `engine_binding_note` | string | Human-readable explanation of the binding state |

Example:

```json
{
  "bundle_id": "b6b9d9aa-61ae-4c28-b630-6d8848f1d85f",
  "tenant_id": "acme",
  "status": "active",
  "engine_binding_active": false,
  "engine_binding_note": "Activation is recorded. Engine binding requires BundleAwareGovernanceEngine — see Phase E / bundle_binding.py."
}
```

### GET /constitution/lifecycle/history/{tenant_id}

Lists all bundles for a tenant in chronological order.

#### Response

```json
[
  {
    "bundle_id": "bundle-1",
    "tenant_id": "acme",
    "status": "draft"
  },
  {
    "bundle_id": "bundle-2",
    "tenant_id": "acme",
    "status": "active"
  }
]
```

## Example flow

```bash
curl -X POST http://localhost:8000/constitution/lifecycle/draft \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-lifecycle-key" \
  -H "X-Actor-ID: proposer-1" \
  -d '{"tenant_id":"acme","name":"v2-rules"}'
```

Followed by:

1. `POST /{bundle_id}/submit`
2. `POST /{bundle_id}/review`
3. `POST /{bundle_id}/eval`
4. `POST /{bundle_id}/approve`
5. `POST /{bundle_id}/stage`
6. `POST /{bundle_id}/activate`

## Source reference

- Router factory: `acgs_lite.constitution.lifecycle_router.create_lifecycle_router`
- Server mounting: `acgs_lite.server.create_governance_app`
- Domain implementation: `acgs_lite.constitution.lifecycle_service.ConstitutionLifecycle`
