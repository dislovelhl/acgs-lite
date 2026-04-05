"""Tests for acgs-lite Kubernetes integration.

Validates ConstitutionalPolicy, GovernanceAdmissionWebhook,
PolicySyncController, GovernanceHealthCheck, and manifest generators
against real Constitution/GovernanceEngine instances.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from acgs_lite import Constitution
from acgs_lite.audit import AuditLog
from acgs_lite.engine import GovernanceEngine
from acgs_lite.integrations.kubernetes import (
    ConstitutionalPolicy,
    GovernanceAdmissionWebhook,
    GovernanceHealthCheck,
    PolicySyncController,
    _extract_admission_text,
    create_crd_manifest,
    create_deployment_manifest,
)

# ─── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def constitution() -> Constitution:
    return Constitution.default()


@pytest.fixture()
def audit_log() -> AuditLog:
    return AuditLog()


@pytest.fixture()
def engine(constitution: Constitution, audit_log: AuditLog) -> GovernanceEngine:
    return GovernanceEngine(constitution, audit_log=audit_log, strict=False)


@pytest.fixture()
def strict_engine(constitution: Constitution, audit_log: AuditLog) -> GovernanceEngine:
    return GovernanceEngine(constitution, audit_log=audit_log, strict=True)


def _make_admission_request(
    *,
    uid: str = "test-uid-123",
    name: str = "my-deployment",
    namespace: str = "default",
    annotations: dict[str, str] | None = None,
    labels: dict[str, str] | None = None,
    kind: str = "Deployment",
    spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a minimal Kubernetes admission request."""
    obj: dict[str, Any] = {
        "metadata": {
            "name": name,
            "namespace": namespace,
            "annotations": annotations or {},
            "labels": labels or {},
        },
        "kind": kind,
        "spec": spec or {},
    }
    return {
        "uid": uid,
        "kind": {"kind": kind},
        "object": obj,
    }


# ═══════════════════════════════════════════════════════════════════════
# ConstitutionalPolicy
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestConstitutionalPolicy:
    def test_create_default(self) -> None:
        policy = ConstitutionalPolicy(name="test-policy")
        assert policy.name == "test-policy"
        assert policy.namespace == "default"
        assert policy.enforcement_mode == "enforce"
        assert policy.constitutional_hash == "608508a9bd224290"
        assert policy.rules == []

    def test_create_with_rules(self) -> None:
        rules = [
            {"id": "R001", "text": "No harmful output", "severity": "critical"},
        ]
        policy = ConstitutionalPolicy(
            name="safety-policy",
            namespace="governance",
            rules=rules,
            enforcement_mode="audit",
        )
        assert policy.namespace == "governance"
        assert policy.enforcement_mode == "audit"
        assert len(policy.rules) == 1

    def test_invalid_enforcement_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="enforcement_mode"):
            ConstitutionalPolicy(
                name="bad-policy", enforcement_mode="invalid",
            )

    def test_to_custom_resource_structure(self) -> None:
        policy = ConstitutionalPolicy(
            name="my-policy",
            namespace="prod",
            rules=[{"id": "R1", "text": "be safe"}],
            enforcement_mode="warn",
        )
        cr = policy.to_custom_resource()

        assert cr["apiVersion"] == "acgs.ai/v1alpha1"
        assert cr["kind"] == "ConstitutionalPolicy"
        assert cr["metadata"]["name"] == "my-policy"
        assert cr["metadata"]["namespace"] == "prod"
        assert cr["spec"]["enforcementMode"] == "warn"
        assert cr["spec"]["constitutionalHash"] == "608508a9bd224290"
        assert len(cr["spec"]["rules"]) == 1

    def test_to_custom_resource_labels(self) -> None:
        policy = ConstitutionalPolicy(name="label-test")
        cr = policy.to_custom_resource()
        labels = cr["metadata"]["labels"]
        assert "acgs.ai/constitutional-hash" in labels
        assert "acgs.ai/enforcement-mode" in labels

    def test_from_custom_resource(self) -> None:
        original = ConstitutionalPolicy(
            name="round-trip",
            namespace="staging",
            rules=[{"id": "R2", "text": "respect privacy"}],
            enforcement_mode="audit",
        )
        cr = original.to_custom_resource()
        restored = ConstitutionalPolicy.from_custom_resource(cr)

        assert restored.name == original.name
        assert restored.namespace == original.namespace
        assert restored.rules == original.rules
        assert restored.enforcement_mode == original.enforcement_mode
        assert restored.constitutional_hash == original.constitutional_hash

    def test_round_trip_preserves_all_fields(self) -> None:
        rules = [
            {"id": "R1", "text": "rule one", "severity": "high"},
            {"id": "R2", "text": "rule two", "severity": "low"},
        ]
        policy = ConstitutionalPolicy(
            name="full-test",
            namespace="ns",
            rules=rules,
            constitutional_hash="abc123",
            enforcement_mode="warn",
        )
        cr = policy.to_custom_resource()
        restored = ConstitutionalPolicy.from_custom_resource(cr)

        assert restored.name == "full-test"
        assert restored.namespace == "ns"
        assert len(restored.rules) == 2
        assert restored.constitutional_hash == "abc123"
        assert restored.enforcement_mode == "warn"

    def test_from_custom_resource_missing_fields(self) -> None:
        cr: dict[str, Any] = {
            "metadata": {},
            "spec": {},
        }
        policy = ConstitutionalPolicy.from_custom_resource(cr)
        assert policy.name == ""
        assert policy.namespace == "default"
        assert policy.rules == []
        assert policy.enforcement_mode == "enforce"

    def test_created_at_set_automatically(self) -> None:
        policy = ConstitutionalPolicy(name="ts-test")
        assert policy.created_at  # non-empty
        assert "T" in policy.created_at  # ISO format


# ═══════════════════════════════════════════════════════════════════════
# GovernanceAdmissionWebhook
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestGovernanceAdmissionWebhook:
    def test_init_with_engine(self, engine: GovernanceEngine) -> None:
        webhook = GovernanceAdmissionWebhook(engine)
        assert webhook._agent_id == "k8s-admission"

    def test_init_with_constitution(self, constitution: Constitution) -> None:
        webhook = GovernanceAdmissionWebhook(constitution)
        assert webhook._engine is not None
        assert webhook._engine.strict is False

    def test_init_custom_agent_id(self, engine: GovernanceEngine) -> None:
        webhook = GovernanceAdmissionWebhook(engine, agent_id="custom-agent")
        assert webhook._agent_id == "custom-agent"

    def test_allowed_request(self, engine: GovernanceEngine) -> None:
        webhook = GovernanceAdmissionWebhook(engine)
        request = _make_admission_request(name="safe-deployment")
        response = webhook.validate_admission(request)

        assert response["response"]["allowed"] is True
        assert response["response"]["uid"] == "test-uid-123"
        assert response["kind"] == "AdmissionReview"

    def test_empty_text_is_allowed(self, engine: GovernanceEngine) -> None:
        webhook = GovernanceAdmissionWebhook(engine)
        request = _make_admission_request(
            name="",
            namespace="",
            annotations={},
            labels={},
        )
        response = webhook.validate_admission(request)
        assert response["response"]["allowed"] is True

    def test_admission_response_uid_preserved(
        self, engine: GovernanceEngine,
    ) -> None:
        webhook = GovernanceAdmissionWebhook(engine)
        request = _make_admission_request(uid="specific-uid-456")
        response = webhook.validate_admission(request)
        assert response["response"]["uid"] == "specific-uid-456"

    def test_webhook_config_generation(
        self, engine: GovernanceEngine,
    ) -> None:
        webhook = GovernanceAdmissionWebhook(engine)
        config = webhook.create_webhook_config(
            "acgs-webhook", "acgs-system",
        )

        assert config["kind"] == "ValidatingWebhookConfiguration"
        assert config["metadata"]["name"] == "acgs-webhook-governance"
        webhooks = config["webhooks"]
        assert len(webhooks) == 1
        assert webhooks[0]["name"] == "governance.acgs.ai"
        assert webhooks[0]["sideEffects"] == "None"
        assert webhooks[0]["failurePolicy"] == "Fail"

    def test_webhook_config_with_ca_bundle(
        self, engine: GovernanceEngine,
    ) -> None:
        webhook = GovernanceAdmissionWebhook(engine)
        config = webhook.create_webhook_config(
            "svc", "ns", ca_bundle="base64data",
        )
        client_config = config["webhooks"][0]["clientConfig"]
        assert client_config["caBundle"] == "base64data"

    def test_webhook_config_without_ca_bundle(
        self, engine: GovernanceEngine,
    ) -> None:
        webhook = GovernanceAdmissionWebhook(engine)
        config = webhook.create_webhook_config("svc", "ns")
        client_config = config["webhooks"][0]["clientConfig"]
        assert "caBundle" not in client_config

    def test_webhook_config_service_path(
        self, engine: GovernanceEngine,
    ) -> None:
        webhook = GovernanceAdmissionWebhook(engine)
        config = webhook.create_webhook_config("my-svc", "my-ns")
        service = config["webhooks"][0]["clientConfig"]["service"]
        assert service["name"] == "my-svc"
        assert service["namespace"] == "my-ns"
        assert service["path"] == "/validate"

    def test_webhook_config_labels_include_hash(
        self, engine: GovernanceEngine,
    ) -> None:
        webhook = GovernanceAdmissionWebhook(engine)
        config = webhook.create_webhook_config("svc", "ns")
        labels = config["metadata"]["labels"]
        assert "acgs.ai/constitutional-hash" in labels


# ═══════════════════════════════════════════════════════════════════════
# Enforcement Modes
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestEnforcementModes:
    """Test that enforcement_mode attr on webhook changes behavior."""

    def test_warn_mode_allows_with_message(
        self, engine: GovernanceEngine,
    ) -> None:
        webhook = GovernanceAdmissionWebhook(engine)
        webhook._enforcement_mode = "warn"  # type: ignore[attr-defined]

        # Use annotations that mention a violation-triggering phrase
        request = _make_admission_request(
            annotations={"purpose": "modify validation logic bypass"},
        )
        response = webhook.validate_admission(request)
        # warn mode always allows
        assert response["response"]["allowed"] is True

    def test_audit_mode_allows_with_message(
        self, engine: GovernanceEngine,
    ) -> None:
        webhook = GovernanceAdmissionWebhook(engine)
        webhook._enforcement_mode = "audit"  # type: ignore[attr-defined]

        request = _make_admission_request(
            annotations={"purpose": "modify validation logic bypass"},
        )
        response = webhook.validate_admission(request)
        assert response["response"]["allowed"] is True

    def test_enforce_mode_default(
        self, engine: GovernanceEngine,
    ) -> None:
        webhook = GovernanceAdmissionWebhook(engine)
        # Default has no _enforcement_mode attr, defaults to "enforce"
        request = _make_admission_request(name="safe-deploy")
        response = webhook.validate_admission(request)
        assert response["response"]["allowed"] is True


# ═══════════════════════════════════════════════════════════════════════
# _extract_admission_text
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestExtractAdmissionText:
    def test_extracts_annotations(self) -> None:
        request = _make_admission_request(
            annotations={"description": "run inference"},
        )
        text = _extract_admission_text(request)
        assert "description=run inference" in text

    def test_extracts_labels(self) -> None:
        request = _make_admission_request(
            labels={"team": "ml-platform"},
        )
        text = _extract_admission_text(request)
        assert "team=ml-platform" in text

    def test_extracts_name_and_namespace(self) -> None:
        request = _make_admission_request(
            name="my-pod", namespace="production",
        )
        text = _extract_admission_text(request)
        assert "my-pod" in text
        assert "production" in text

    def test_extracts_spec_description(self) -> None:
        request = _make_admission_request(
            spec={"description": "AI governance service"},
        )
        text = _extract_admission_text(request)
        assert "AI governance service" in text

    def test_extracts_container_images(self) -> None:
        request = _make_admission_request(
            spec={
                "containers": [
                    {"image": "acgs/webhook:v1", "name": "webhook"},
                ],
            },
        )
        text = _extract_admission_text(request)
        assert "image=acgs/webhook:v1" in text

    def test_extracts_template_containers(self) -> None:
        request = _make_admission_request(
            spec={
                "template": {
                    "spec": {
                        "containers": [
                            {"image": "nginx:latest", "command": ["nginx", "-g"]},
                        ],
                    },
                },
            },
        )
        text = _extract_admission_text(request)
        assert "image=nginx:latest" in text
        assert "command=nginx -g" in text

    def test_empty_request_returns_empty(self) -> None:
        request: dict[str, Any] = {"object": {"metadata": {}}}
        text = _extract_admission_text(request)
        assert text.strip() == ""


# ═══════════════════════════════════════════════════════════════════════
# PolicySyncController
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestPolicySyncController:
    def test_init_defaults(self, engine: GovernanceEngine) -> None:
        sync = PolicySyncController(engine)
        assert sync._namespace == "default"
        assert sync._config_map_name == "acgs-constitution"

    def test_init_custom(self, engine: GovernanceEngine) -> None:
        sync = PolicySyncController(
            engine, namespace="prod", config_map_name="my-constitution",
        )
        assert sync._namespace == "prod"
        assert sync._config_map_name == "my-constitution"

    def test_sync_to_config_map(
        self, engine: GovernanceEngine, constitution: Constitution,
    ) -> None:
        sync = PolicySyncController(engine)
        cm = sync.sync_to_config_map(constitution)

        assert cm["apiVersion"] == "v1"
        assert cm["kind"] == "ConfigMap"
        assert cm["metadata"]["name"] == "acgs-constitution"
        assert cm["metadata"]["namespace"] == "default"
        assert "constitution.json" in cm["data"]

        # Parse the embedded JSON
        parsed = json.loads(cm["data"]["constitution.json"])
        assert "rules" in parsed
        assert len(parsed["rules"]) > 0

    def test_sync_to_config_map_labels(
        self, engine: GovernanceEngine, constitution: Constitution,
    ) -> None:
        sync = PolicySyncController(engine)
        cm = sync.sync_to_config_map(constitution)
        labels = cm["metadata"]["labels"]
        assert "acgs.ai/constitutional-hash" in labels
        assert labels["acgs.ai/component"] == "constitution"

    def test_sync_from_config_map_json(
        self, engine: GovernanceEngine, constitution: Constitution,
    ) -> None:
        sync = PolicySyncController(engine)
        # Round-trip: write then read
        cm = sync.sync_to_config_map(constitution)
        restored = sync.sync_from_config_map(cm["data"])

        assert len(restored.rules) == len(constitution.rules)
        assert restored.name == constitution.name

    def test_sync_from_config_map_yaml(
        self, engine: GovernanceEngine, constitution: Constitution,
    ) -> None:
        sync = PolicySyncController(engine)
        yaml_str = constitution.to_yaml()
        data = {"constitution.yaml": yaml_str}
        restored = sync.sync_from_config_map(data)
        assert len(restored.rules) == len(constitution.rules)

    def test_sync_from_config_map_individual_rules(
        self, engine: GovernanceEngine,
    ) -> None:
        sync = PolicySyncController(engine)
        data = {
            "rule-001": json.dumps({
                "id": "K8S-001",
                "text": "No unvetted images",
                "severity": "high",
                "keywords": ["image", "unvetted"],
            }),
            "rule-002": json.dumps({
                "id": "K8S-002",
                "text": "Require resource limits",
                "severity": "medium",
                "keywords": ["limits", "resources"],
            }),
        }
        restored = sync.sync_from_config_map(data)
        assert len(restored.rules) == 2

    def test_sync_from_config_map_skips_invalid_json(
        self, engine: GovernanceEngine,
    ) -> None:
        sync = PolicySyncController(engine)
        data = {
            "good-rule": json.dumps({
                "id": "K8S-003",
                "text": "Valid rule",
                "severity": "low",
                "keywords": ["valid"],
            }),
            "bad-rule": "not-json{{{",
        }
        restored = sync.sync_from_config_map(data)
        assert len(restored.rules) == 1

    def test_get_policy_status(
        self, engine: GovernanceEngine, constitution: Constitution,
    ) -> None:
        sync = PolicySyncController(engine, namespace="staging")
        status = sync.get_policy_status()

        assert status["hash"] == constitution.hash
        assert status["rule_count"] == len(constitution.rules)
        assert status["namespace"] == "staging"
        assert status["last_sync"] is None

    def test_get_policy_status_after_sync(
        self, engine: GovernanceEngine, constitution: Constitution,
    ) -> None:
        sync = PolicySyncController(engine)
        sync.sync_to_config_map(constitution)
        status = sync.get_policy_status()
        assert status["last_sync"] is not None


# ═══════════════════════════════════════════════════════════════════════
# GovernanceHealthCheck
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestGovernanceHealthCheck:
    def test_liveness_healthy(
        self, engine: GovernanceEngine, audit_log: AuditLog,
    ) -> None:
        health = GovernanceHealthCheck(engine, audit_log)
        result = health.liveness()
        assert result["status"] == "ok"

    def test_readiness_healthy(
        self, engine: GovernanceEngine, audit_log: AuditLog,
    ) -> None:
        health = GovernanceHealthCheck(engine, audit_log)
        result = health.readiness()
        assert result["status"] == "ok"
        assert "constitutional_hash" in result
        assert "rules_count" in result
        assert result["chain_valid"] is True

    def test_readiness_invalid_chain(
        self, engine: GovernanceEngine, audit_log: AuditLog,
    ) -> None:
        health = GovernanceHealthCheck(engine, audit_log)
        # Tamper with the audit log chain
        from acgs_lite.audit import AuditEntry
        audit_log.record(AuditEntry(id="1", type="validation"))
        audit_log._chain_hashes[-1] = "tampered"

        result = health.readiness()
        assert result["status"] == "not_ready"
        assert result["reason"] == "audit_chain_invalid"

    def test_startup_healthy(
        self, engine: GovernanceEngine, audit_log: AuditLog,
    ) -> None:
        health = GovernanceHealthCheck(engine, audit_log)
        result = health.startup()
        assert result["status"] == "ok"
        assert result["rules_count"] > 0
        assert "constitution_name" in result

    def test_startup_no_rules(self, audit_log: AuditLog) -> None:
        empty_constitution = Constitution(name="empty", rules=[])
        engine = GovernanceEngine(
            empty_constitution, audit_log=audit_log, strict=False,
        )
        health = GovernanceHealthCheck(engine, audit_log)
        result = health.startup()
        assert result["status"] == "not_ready"
        assert result["reason"] == "no_rules_loaded"

    def test_liveness_error_handling(
        self, engine: GovernanceEngine, audit_log: AuditLog,
    ) -> None:
        health = GovernanceHealthCheck(engine, audit_log)
        # Simulate engine failure by replacing validate method
        with patch.object(
            engine, "validate", side_effect=RuntimeError("broken"),
        ):
            result = health.liveness()
        assert result["status"] == "error"
        assert result["reason"] == "RuntimeError"

    def test_readiness_engine_down(
        self, engine: GovernanceEngine, audit_log: AuditLog,
    ) -> None:
        health = GovernanceHealthCheck(engine, audit_log)
        with patch.object(
            engine, "validate", side_effect=RuntimeError("down"),
        ):
            result = health.readiness()
        assert result["status"] == "not_ready"
        assert result["reason"] == "engine_not_alive"


# ═══════════════════════════════════════════════════════════════════════
# CRD Manifest
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestCRDManifest:
    def test_crd_structure(self) -> None:
        crd = create_crd_manifest()
        assert crd["apiVersion"] == "apiextensions.k8s.io/v1"
        assert crd["kind"] == "CustomResourceDefinition"
        assert crd["metadata"]["name"] == "constitutionalpolicies.acgs.ai"

    def test_crd_group_and_names(self) -> None:
        crd = create_crd_manifest()
        spec = crd["spec"]
        assert spec["group"] == "acgs.ai"
        names = spec["names"]
        assert names["kind"] == "ConstitutionalPolicy"
        assert names["plural"] == "constitutionalpolicies"
        assert "cp" in names["shortNames"]

    def test_crd_schema_has_required_fields(self) -> None:
        crd = create_crd_manifest()
        version = crd["spec"]["versions"][0]
        assert version["name"] == "v1alpha1"
        assert version["served"] is True
        assert version["storage"] is True

        props = version["schema"]["openAPIV3Schema"]["properties"]
        spec_props = props["spec"]["properties"]
        assert "rules" in spec_props
        assert "constitutionalHash" in spec_props
        assert "enforcementMode" in spec_props

    def test_crd_severity_enum(self) -> None:
        crd = create_crd_manifest()
        version = crd["spec"]["versions"][0]
        props = version["schema"]["openAPIV3Schema"]["properties"]
        rule_props = props["spec"]["properties"]["rules"]["items"]["properties"]
        severity_enum = rule_props["severity"]["enum"]
        assert "critical" in severity_enum
        assert "high" in severity_enum
        assert "medium" in severity_enum
        assert "low" in severity_enum

    def test_crd_printer_columns(self) -> None:
        crd = create_crd_manifest()
        columns = crd["spec"]["versions"][0]["additionalPrinterColumns"]
        column_names = [c["name"] for c in columns]
        assert "Hash" in column_names
        assert "Mode" in column_names
        assert "Age" in column_names

    def test_crd_scope_namespaced(self) -> None:
        crd = create_crd_manifest()
        assert crd["spec"]["scope"] == "Namespaced"


# ═══════════════════════════════════════════════════════════════════════
# Deployment Manifest
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestDeploymentManifest:
    def test_deployment_structure(self) -> None:
        dep = create_deployment_manifest("acgs/webhook:v1")
        assert dep["apiVersion"] == "apps/v1"
        assert dep["kind"] == "Deployment"
        assert dep["metadata"]["namespace"] == "acgs-system"

    def test_deployment_custom_namespace(self) -> None:
        dep = create_deployment_manifest("img:v1", namespace="custom")
        assert dep["metadata"]["namespace"] == "custom"

    def test_deployment_replicas(self) -> None:
        dep = create_deployment_manifest("img:v1", replicas=3)
        assert dep["spec"]["replicas"] == 3

    def test_deployment_default_replicas(self) -> None:
        dep = create_deployment_manifest("img:v1")
        assert dep["spec"]["replicas"] == 2

    def test_deployment_container_image(self) -> None:
        dep = create_deployment_manifest("acgs/webhook:latest")
        containers = dep["spec"]["template"]["spec"]["containers"]
        assert len(containers) == 1
        assert containers[0]["image"] == "acgs/webhook:latest"

    def test_deployment_probes(self) -> None:
        dep = create_deployment_manifest("img:v1")
        container = dep["spec"]["template"]["spec"]["containers"][0]
        assert "livenessProbe" in container
        assert "readinessProbe" in container
        assert container["livenessProbe"]["httpGet"]["path"] == "/healthz"
        assert container["readinessProbe"]["httpGet"]["path"] == "/readyz"

    def test_deployment_volumes(self) -> None:
        dep = create_deployment_manifest("img:v1")
        volumes = dep["spec"]["template"]["spec"]["volumes"]
        volume_names = [v["name"] for v in volumes]
        assert "constitution" in volume_names
        assert "tls-certs" in volume_names

    def test_deployment_labels(self) -> None:
        dep = create_deployment_manifest("img:v1")
        labels = dep["metadata"]["labels"]
        assert labels["app.kubernetes.io/name"] == "acgs-governance-webhook"
        assert labels["app.kubernetes.io/part-of"] == "acgs"

    def test_deployment_resource_limits(self) -> None:
        dep = create_deployment_manifest("img:v1")
        container = dep["spec"]["template"]["spec"]["containers"][0]
        resources = container["resources"]
        assert "requests" in resources
        assert "limits" in resources
        assert resources["requests"]["cpu"] == "100m"
        assert resources["limits"]["memory"] == "256Mi"


# ═══════════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestEdgeCases:
    def test_policy_with_empty_rules(self) -> None:
        policy = ConstitutionalPolicy(name="empty", rules=[])
        cr = policy.to_custom_resource()
        assert cr["spec"]["rules"] == []

    def test_sync_empty_config_map(
        self, engine: GovernanceEngine,
    ) -> None:
        sync = PolicySyncController(engine)
        result = sync.sync_from_config_map({})
        assert len(result.rules) == 0

    def test_admission_webhook_missing_object(
        self, engine: GovernanceEngine,
    ) -> None:
        webhook = GovernanceAdmissionWebhook(engine)
        request: dict[str, Any] = {"uid": "no-object"}
        response = webhook.validate_admission(request)
        # No object means empty text, should be allowed
        assert response["response"]["allowed"] is True

    def test_all_enforcement_modes_valid(self) -> None:
        for mode in ("enforce", "audit", "warn"):
            policy = ConstitutionalPolicy(
                name=f"mode-{mode}", enforcement_mode=mode,
            )
            assert policy.enforcement_mode == mode

    def test_config_map_round_trip_preserves_rule_count(
        self,
        engine: GovernanceEngine,
        constitution: Constitution,
    ) -> None:
        sync = PolicySyncController(engine)
        cm = sync.sync_to_config_map(constitution)
        restored = sync.sync_from_config_map(cm["data"])
        assert len(restored.rules) == len(constitution.rules)

    def test_custom_resource_round_trip_empty(self) -> None:
        policy = ConstitutionalPolicy(name="empty-rt", rules=[])
        cr = policy.to_custom_resource()
        restored = ConstitutionalPolicy.from_custom_resource(cr)
        assert restored.rules == []
        assert restored.name == "empty-rt"
