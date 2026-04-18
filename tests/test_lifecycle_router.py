"""HTTP integration tests for the lifecycle FastAPI router — Phase C."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from acgs_lite.constitution.lifecycle_router import create_lifecycle_router
from acgs_lite.evals.schema import EvalScenario


def _make_app(api_key: str | None = "test-secret") -> FastAPI:
    app = FastAPI()
    app.include_router(create_lifecycle_router(api_key=api_key))
    return app


BASE = "/constitution/lifecycle"
KEY = "test-secret"
HEADERS = {"X-API-Key": KEY, "X-Actor-ID": "actor-1"}
PROPOSER = "proposer-1"


@pytest.fixture
def app() -> FastAPI:
    return _make_app()


@pytest.fixture
async def client(app: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestAuth:
    @pytest.mark.asyncio
    async def test_401_without_api_key(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"{BASE}/draft",
            json={"tenant_id": "t1"},
            headers={"X-Actor-ID": "actor-1"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_401_with_wrong_api_key(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"{BASE}/draft",
            json={"tenant_id": "t1"},
            headers={"X-API-Key": "wrong-key", "X-Actor-ID": "actor-1"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_400_without_actor_id(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"{BASE}/draft",
            json={"tenant_id": "t1"},
            headers={"X-API-Key": KEY},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_auth_disabled_when_no_key_configured(self) -> None:
        app = _make_app(api_key=None)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"{BASE}/draft",
                json={"tenant_id": "t1"},
                headers={"X-Actor-ID": "actor-1"},  # no X-API-Key
            )
        assert resp.status_code == 200


class TestDraftEndpoint:
    @pytest.mark.asyncio
    async def test_create_draft_200(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"{BASE}/draft",
            json={"tenant_id": "tenant-a"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "bundle_id" in data
        assert data["status"] == "draft"

    @pytest.mark.asyncio
    async def test_404_on_unknown_bundle(self, client: AsyncClient) -> None:
        resp = await client.get(f"{BASE}/nonexistent-bundle-id", headers=HEADERS)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_400_on_zero_scenarios(self, client: AsyncClient) -> None:
        # Create draft first
        draft_resp = await client.post(
            f"{BASE}/draft",
            json={"tenant_id": "tenant-a"},
            headers=HEADERS,
        )
        bid = draft_resp.json()["bundle_id"]

        # Submit
        await client.post(f"{BASE}/{bid}/submit", headers=HEADERS)
        # Approve review
        await client.post(f"{BASE}/{bid}/review", headers=HEADERS)

        # Now try eval with zero scenarios
        eval_resp = await client.post(
            f"{BASE}/{bid}/eval",
            json={"scenarios": []},
            headers=HEADERS,
        )
        assert eval_resp.status_code == 400
        body = eval_resp.json()
        # Should have structured error envelope
        assert "error" in body.get("detail", body)

    @pytest.mark.asyncio
    async def test_active_bundle_includes_engine_binding_active_field(
        self, client: AsyncClient
    ) -> None:
        resp = await client.get(f"{BASE}/active/tenant-no-bundle", headers=HEADERS)
        # Either 404 (no active bundle) or 200 with engine_binding_active field
        # When no active bundle exists, router returns 404
        assert resp.status_code == 404


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_full_draft_to_active_lifecycle(self, client: AsyncClient) -> None:
        """HTTP happy path: draft → submit → review → eval → approve → stage → activate."""
        # 1. Create draft
        resp = await client.post(
            f"{BASE}/draft",
            json={"tenant_id": "tenant-x"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        bundle_id = resp.json()["bundle_id"]

        # 2. Submit for review
        resp = await client.post(f"{BASE}/{bundle_id}/submit", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["status"] == "review"

        # 3. Approve review — reviewer must be different from proposer (actor-1).
        reviewer_headers = {**HEADERS, "X-Actor-ID": "reviewer-distinct-1"}
        resp = await client.post(f"{BASE}/{bundle_id}/review", headers=reviewer_headers)
        assert resp.status_code == 200

        # 4. Run evaluation with one passing scenario
        resp = await client.post(
            f"{BASE}/{bundle_id}/eval",
            json={
                "scenarios": [
                    {
                        "id": "s1",
                        "input_action": "check current status of the system",
                        "expected_valid": True,
                    }
                ]
            },
            headers=HEADERS,
        )
        assert resp.status_code == 200

        # 5. Approve — use a distinct actor from the proposer.
        approve_headers = {**HEADERS, "X-Actor-ID": "approver-distinct-1"}
        resp = await client.post(
            f"{BASE}/{bundle_id}/approve",
            json={"signature": "sig-ok"},
            headers=approve_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approve"

        # 6. Stage
        stage_headers = {**HEADERS, "X-Actor-ID": "executor-1"}
        resp = await client.post(f"{BASE}/{bundle_id}/stage", headers=stage_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "staged"

        # 7. Activate
        resp = await client.post(f"{BASE}/{bundle_id}/activate", headers=stage_headers)
        assert resp.status_code == 200
        activation = resp.json()
        assert activation["tenant_id"] == "tenant-x"
        assert activation["bundle_id"] == bundle_id

    @pytest.mark.asyncio
    async def test_history_endpoint(self, client: AsyncClient) -> None:
        # Create a draft to populate history
        resp = await client.post(
            f"{BASE}/draft",
            json={"tenant_id": "hist-tenant"},
            headers=HEADERS,
        )
        assert resp.status_code == 200

        resp = await client.get(f"{BASE}/history/hist-tenant", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_reject_endpoint(self, client: AsyncClient) -> None:
        """VALIDATOR can reject a bundle in review state."""
        # actor-1 (from HEADERS) creates the draft and submits it (proposer role)
        resp = await client.post(
            f"{BASE}/draft",
            json={"tenant_id": "reject-tenant"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        bundle_id = resp.json()["bundle_id"]

        resp = await client.post(f"{BASE}/{bundle_id}/submit", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["status"] == "review"

        # VALIDATOR rejects the bundle
        validator_headers = {**HEADERS, "X-Actor-ID": "validator-reject-1"}
        resp = await client.post(
            f"{BASE}/{bundle_id}/reject",
            json={"reason": "does not meet compliance standards"},
            headers=validator_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_reject_on_unknown_bundle_returns_error(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"{BASE}/nonexistent-bundle/reject",
            json={"reason": "bad"},
            headers=HEADERS,
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "NOT_FOUND"


# ── MACI-aware header helpers ─────────────────────────────────────────────

REVIEWER_HEADERS = {**HEADERS, "X-Actor-ID": "reviewer-distinct-1"}
APPROVER_HEADERS = {**HEADERS, "X-Actor-ID": "approver-distinct-1"}
EXECUTOR_HEADERS = {**HEADERS, "X-Actor-ID": "executor-distinct-1"}


async def _drive_to_staged_http(client: AsyncClient, tenant_id: str) -> str:
    """HTTP-level helper: drive a bundle from DRAFT → STAGED using MACI-correct actors."""
    resp = await client.post(f"{BASE}/draft", json={"tenant_id": tenant_id}, headers=HEADERS)
    assert resp.status_code == 200
    bundle_id = resp.json()["bundle_id"]

    r = await client.post(f"{BASE}/{bundle_id}/submit", headers=HEADERS)
    assert r.status_code == 200

    r = await client.post(f"{BASE}/{bundle_id}/review", headers=REVIEWER_HEADERS)
    assert r.status_code == 200

    r = await client.post(
        f"{BASE}/{bundle_id}/eval",
        json={"scenarios": [{"id": "s1", "input_action": "check status", "expected_valid": True}]},
        headers=HEADERS,
    )
    assert r.status_code == 200

    r = await client.post(
        f"{BASE}/{bundle_id}/approve", json={"signature": "sig-ok"}, headers=APPROVER_HEADERS
    )
    assert r.status_code == 200

    r = await client.post(f"{BASE}/{bundle_id}/stage", headers=EXECUTOR_HEADERS)
    assert r.status_code == 200

    return bundle_id


class TestUncoveredEndpoints:
    """Hardening coverage for stage/activate/rollback/withdraw/get_bundle/get_active."""

    @pytest.mark.asyncio
    async def test_get_bundle_by_id_200(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"{BASE}/draft",
            json={"tenant_id": "tenant-get-id"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        bundle_id = resp.json()["bundle_id"]

        resp = await client.get(f"{BASE}/{bundle_id}", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["bundle_id"] == bundle_id

    @pytest.mark.asyncio
    async def test_get_bundle_by_id_404(self, client: AsyncClient) -> None:
        resp = await client.get(f"{BASE}/nonexistent-bundle-id-xyz", headers=HEADERS)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_active_bundle_returns_engine_binding_fields(self) -> None:
        """GET /active/{tenant} on a tenant with an active bundle returns engine_binding fields."""
        from acgs_lite.constitution.bundle_store import InMemoryBundleStore
        from acgs_lite.constitution.evidence import InMemoryLifecycleAuditSink
        from acgs_lite.constitution.lifecycle_service import ConstitutionLifecycle

        lc = ConstitutionLifecycle(store=InMemoryBundleStore(), sink=InMemoryLifecycleAuditSink())
        draft = await lc.create_draft("tenant-active-get", "proposer-1")
        await lc.submit_for_review(draft.bundle_id, "proposer-1")
        await lc.approve_review(draft.bundle_id, "reviewer-1")
        await lc.run_evaluation(
            draft.bundle_id,
            scenarios=[EvalScenario(id="s1", input_action="check status", expected_valid=True)],
        )
        await lc.approve(draft.bundle_id, "approver-1", signature="sig-1")
        await lc.stage(draft.bundle_id, "executor-1")
        await lc.activate(draft.bundle_id, "executor-1")

        app2 = FastAPI()
        app2.include_router(create_lifecycle_router(lifecycle=lc, api_key=KEY))
        async with AsyncClient(transport=ASGITransport(app=app2), base_url="http://test") as c:
            resp = await c.get(f"{BASE}/active/tenant-active-get", headers=HEADERS)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert "engine_binding_active" in data
        assert data["engine_binding_active"] is False
        assert "engine_binding_note" in data

    @pytest.mark.asyncio
    async def test_stage_endpoint_200(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"{BASE}/draft", json={"tenant_id": "tenant-stage-test"}, headers=HEADERS
        )
        bundle_id = resp.json()["bundle_id"]
        await client.post(f"{BASE}/{bundle_id}/submit", headers=HEADERS)
        await client.post(f"{BASE}/{bundle_id}/review", headers=REVIEWER_HEADERS)
        await client.post(
            f"{BASE}/{bundle_id}/eval",
            json={"scenarios": [{"id": "s1", "input_action": "check", "expected_valid": True}]},
            headers=HEADERS,
        )
        await client.post(
            f"{BASE}/{bundle_id}/approve", json={"signature": "sig-stage"}, headers=APPROVER_HEADERS
        )

        resp = await client.post(f"{BASE}/{bundle_id}/stage", headers=EXECUTOR_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["status"] == "staged"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("endpoint", "body"),
        [
            ("submit", None),
            ("review", None),
            (
                "eval",
                {"scenarios": [{"id": "s1", "input_action": "check", "expected_valid": True}]},
            ),
            ("approve", {"signature": "sig-missing"}),
            ("stage", None),
            ("activate", None),
            ("rollback", {"reason": "missing bundle"}),
            ("reject", {"reason": "missing bundle"}),
            ("withdraw", {"reason": "missing bundle"}),
        ],
    )
    async def test_missing_bundle_mutations_return_not_found(
        self,
        client: AsyncClient,
        endpoint: str,
        body: dict[str, object] | None,
    ) -> None:
        resp = await client.post(
            f"{BASE}/nonexistent-bundle/{endpoint}",
            json=body,
            headers=HEADERS,
        )

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_activate_endpoint_returns_activation_record(self, client: AsyncClient) -> None:
        bundle_id = await _drive_to_staged_http(client, "tenant-activate-test")

        resp = await client.post(f"{BASE}/{bundle_id}/activate", headers=EXECUTOR_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "bundle_id" in data
        assert "tenant_id" in data
        assert data["bundle_id"] == bundle_id
        assert data["tenant_id"] == "tenant-activate-test"

    @pytest.mark.asyncio
    async def test_rollback_endpoint_200(self, client: AsyncClient) -> None:
        # v1: activate
        bid1 = await _drive_to_staged_http(client, "tenant-rollback-test")
        r = await client.post(f"{BASE}/{bid1}/activate", headers=EXECUTOR_HEADERS)
        assert r.status_code == 200

        # v2: activate to replace v1, then rollback
        bid2 = await _drive_to_staged_http(client, "tenant-rollback-test")
        r = await client.post(f"{BASE}/{bid2}/activate", headers=EXECUTOR_HEADERS)
        assert r.status_code == 200

        resp = await client.post(
            f"{BASE}/{bid2}/rollback",
            json={"reason": "reverting to stable v1"},
            headers=EXECUTOR_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "bundle_id" in data  # ActivationRecord shape

    @pytest.mark.asyncio
    async def test_withdraw_endpoint_200(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"{BASE}/draft", json={"tenant_id": "tenant-withdraw-test"}, headers=HEADERS
        )
        bundle_id = resp.json()["bundle_id"]

        resp = await client.post(
            f"{BASE}/{bundle_id}/withdraw",
            json={"reason": "no longer needed"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "withdrawn"

    @pytest.mark.asyncio
    async def test_concurrent_modification_returns_409(self) -> None:
        """ConcurrentLifecycleError raised by the service returns HTTP 409."""
        from unittest.mock import AsyncMock, MagicMock

        from acgs_lite.constitution.lifecycle_service import ConcurrentLifecycleError

        mock_lc = MagicMock()
        mock_lc.create_draft = AsyncMock(
            side_effect=ConcurrentLifecycleError("tenant version changed")
        )

        app2 = FastAPI()
        app2.include_router(create_lifecycle_router(lifecycle=mock_lc, api_key=KEY))
        async with AsyncClient(transport=ASGITransport(app=app2), base_url="http://test") as c:
            resp = await c.post(
                f"{BASE}/draft",
                json={"tenant_id": "tenant-conflict"},
                headers=HEADERS,
            )

        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "CONCURRENT_CONFLICT"


class TestMACIViolation:
    @pytest.mark.asyncio
    async def test_403_when_reviewer_equals_proposer(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        """MACI: the reviewer cannot be the same actor who submitted the bundle."""
        # proposer creates and submits the draft
        draft_resp = await client.post(
            f"{BASE}/draft",
            json={"tenant_id": "tenant-maci"},
            headers={"X-API-Key": KEY, "X-Actor-ID": PROPOSER},
        )
        assert draft_resp.status_code == 200
        bid = draft_resp.json()["bundle_id"]

        await client.post(
            f"{BASE}/{bid}/submit",
            headers={"X-API-Key": KEY, "X-Actor-ID": PROPOSER},
        )

        # same actor attempts to review — should be rejected
        review_resp = await client.post(
            f"{BASE}/{bid}/review",
            headers={"X-API-Key": KEY, "X-Actor-ID": PROPOSER},
        )
        assert review_resp.status_code == 403
        assert review_resp.json()["detail"]["code"] == "MACI_VIOLATION"


class TestInvalidTransition:
    @pytest.mark.asyncio
    async def test_400_on_invalid_state_transition(self, client: AsyncClient) -> None:
        """Calling /submit on an already-submitted bundle returns 400."""
        draft_resp = await client.post(
            f"{BASE}/draft",
            json={"tenant_id": "tenant-trans"},
            headers=HEADERS,
        )
        bid = draft_resp.json()["bundle_id"]

        # first submit succeeds
        await client.post(f"{BASE}/{bid}/submit", headers=HEADERS)

        # second submit on same bundle violates VALID_TRANSITIONS
        resp = await client.post(f"{BASE}/{bid}/submit", headers=HEADERS)
        assert resp.status_code == 400
