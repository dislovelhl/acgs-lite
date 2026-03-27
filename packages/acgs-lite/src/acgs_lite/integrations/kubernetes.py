"""ACGS-Lite Kubernetes Integration.

Provides governance-as-infrastructure for Kubernetes clusters:

- **ConstitutionalPolicy**: CRD-compatible dataclass for storing constitutional
  rules as Kubernetes custom resources.
- **GovernanceAdmissionWebhook**: Validates Kubernetes admission requests
  against constitutional rules (ValidatingWebhookConfiguration).
- **PolicySyncController**: Syncs constitutional policies between Kubernetes
  ConfigMaps/CRDs and the local governance engine.
- **GovernanceHealthCheck**: Kubernetes-compatible liveness, readiness, and
  startup probe data.
- **create_crd_manifest**: Generates the ConstitutionalPolicy CRD definition.
- **create_deployment_manifest**: Generates a Kubernetes Deployment for running
  the governance admission webhook.

Usage::

    from acgs_lite.constitution import Constitution
    from acgs_lite.engine import GovernanceEngine
    from acgs_lite.integrations.kubernetes import (
        ConstitutionalPolicy,
        GovernanceAdmissionWebhook,
        GovernanceHealthCheck,
        PolicySyncController,
        create_crd_manifest,
        create_deployment_manifest,
    )

    constitution = Constitution.default()
    engine = GovernanceEngine(constitution, strict=False)

    # Admission webhook
    webhook = GovernanceAdmissionWebhook(engine)
    response = webhook.validate_admission(admission_request)

    # Policy sync
    sync = PolicySyncController(engine)
    config_map = sync.sync_to_config_map(constitution)

    # Health checks
    health = GovernanceHealthCheck(engine, audit_log)
    print(health.readiness())

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution, Severity
from acgs_lite.engine import GovernanceEngine

logger = logging.getLogger(__name__)

try:
    import kubernetes  # noqa: F401

    K8S_AVAILABLE = True
except ImportError:
    K8S_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_API_GROUP = "acgs.ai"
_API_VERSION = "v1alpha1"
_CRD_KIND = "ConstitutionalPolicy"
_CRD_PLURAL = "constitutionalpolicies"
_CONSTITUTIONAL_HASH = "608508a9bd224290"

_VALID_ENFORCEMENT_MODES = frozenset({"enforce", "audit", "warn"})


# ---------------------------------------------------------------------------
# ConstitutionalPolicy
# ---------------------------------------------------------------------------


@dataclass
class ConstitutionalPolicy:
    """A constitutional policy stored as a Kubernetes custom resource.

    Attributes:
        name: Policy name (must be DNS-compatible).
        namespace: Kubernetes namespace.
        rules: Serialized constitution rules as list of dicts.
        constitutional_hash: Hash of the constitution these rules derive from.
        enforcement_mode: One of ``"enforce"``, ``"audit"``, ``"warn"``.
        created_at: ISO-8601 timestamp of creation.
    """

    name: str
    namespace: str = "default"
    rules: list[dict[str, Any]] = field(default_factory=list)
    constitutional_hash: str = _CONSTITUTIONAL_HASH
    enforcement_mode: str = "enforce"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )

    def __post_init__(self) -> None:
        if self.enforcement_mode not in _VALID_ENFORCEMENT_MODES:
            raise ValueError(
                f"enforcement_mode must be one of "
                f"{sorted(_VALID_ENFORCEMENT_MODES)}, "
                f"got {self.enforcement_mode!r}"
            )

    def to_custom_resource(self) -> dict[str, Any]:
        """Serialize to a Kubernetes custom resource dict."""
        return {
            "apiVersion": f"{_API_GROUP}/{_API_VERSION}",
            "kind": _CRD_KIND,
            "metadata": {
                "name": self.name,
                "namespace": self.namespace,
                "labels": {
                    f"{_API_GROUP}/constitutional-hash": self.constitutional_hash,
                    f"{_API_GROUP}/enforcement-mode": self.enforcement_mode,
                },
                "annotations": {
                    f"{_API_GROUP}/created-at": self.created_at,
                },
            },
            "spec": {
                "rules": self.rules,
                "constitutionalHash": self.constitutional_hash,
                "enforcementMode": self.enforcement_mode,
            },
        }

    @classmethod
    def from_custom_resource(
        cls, resource: dict[str, Any],
    ) -> ConstitutionalPolicy:
        """Deserialize from a Kubernetes custom resource dict."""
        metadata = resource.get("metadata", {})
        spec = resource.get("spec", {})
        annotations = metadata.get("annotations", {})
        return cls(
            name=metadata.get("name", ""),
            namespace=metadata.get("namespace", "default"),
            rules=spec.get("rules", []),
            constitutional_hash=spec.get(
                "constitutionalHash", _CONSTITUTIONAL_HASH,
            ),
            enforcement_mode=spec.get("enforcementMode", "enforce"),
            created_at=annotations.get(
                f"{_API_GROUP}/created-at",
                datetime.now(timezone.utc).isoformat(),
            ),
        )


# ---------------------------------------------------------------------------
# GovernanceAdmissionWebhook
# ---------------------------------------------------------------------------


def _extract_admission_text(request: dict[str, Any]) -> str:
    """Extract governance-relevant text from an admission request.

    Pulls metadata annotations, labels, and spec-level fields that
    carry human-readable descriptions suitable for constitutional
    validation.
    """
    parts: list[str] = []
    obj = request.get("object", {})
    metadata = obj.get("metadata", {})

    # Annotations often carry descriptions, purpose statements
    for key, value in metadata.get("annotations", {}).items():
        if isinstance(value, str):
            parts.append(f"{key}={value}")

    # Labels carry intent signals
    for key, value in metadata.get("labels", {}).items():
        if isinstance(value, str):
            parts.append(f"{key}={value}")

    # Name itself can carry meaning
    name = metadata.get("name", "")
    if name:
        parts.append(name)

    # Namespace
    ns = metadata.get("namespace", "")
    if ns:
        parts.append(ns)

    # Spec-level description fields (common in CRDs)
    spec = obj.get("spec", {})
    for desc_key in ("description", "purpose", "goal", "backstory"):
        desc = spec.get(desc_key, "")
        if isinstance(desc, str) and desc:
            parts.append(desc)

    # Container images and commands (Pods, Deployments)
    containers = spec.get("containers", [])
    if not containers:
        template_spec = spec.get("template", {}).get("spec", {})
        containers = template_spec.get("containers", [])
    for container in containers:
        if isinstance(container, dict):
            image = container.get("image", "")
            if image:
                parts.append(f"image={image}")
            command = container.get("command", [])
            if command:
                parts.append(f"command={' '.join(command)}")

    return " ".join(parts)


class GovernanceAdmissionWebhook:
    """Validates Kubernetes admission requests against constitutional rules.

    Operates as the decision logic behind a Kubernetes
    ``ValidatingWebhookConfiguration``. Each admission request is
    converted to a text representation and validated through the
    governance engine.

    Args:
        engine_or_constitution: A :class:`GovernanceEngine` instance or a
            :class:`Constitution` (which will be wrapped in a non-strict
            engine automatically).
        agent_id: Agent identifier recorded in audit entries.
    """

    def __init__(
        self,
        engine_or_constitution: GovernanceEngine | Constitution,
        *,
        agent_id: str = "k8s-admission",
    ) -> None:
        if isinstance(engine_or_constitution, Constitution):
            self._engine = GovernanceEngine(
                engine_or_constitution, strict=False,
            )
        else:
            self._engine = engine_or_constitution
        self._agent_id = agent_id

    def validate_admission(self, request: dict[str, Any]) -> dict[str, Any]:
        """Validate a Kubernetes AdmissionReview request.

        Args:
            request: The ``request`` field of an ``AdmissionReview``.

        Returns:
            An ``AdmissionReview`` response dict with ``allowed`` and
            ``status`` fields.
        """
        uid = request.get("uid", "")
        text = _extract_admission_text(request)

        if not text.strip():
            return _admission_response(uid, allowed=True)

        # Use non-strict mode to get a result instead of raising
        with self._engine.non_strict():
            result = self._engine.validate(
                text, agent_id=self._agent_id,
            )

        enforcement = getattr(self, "_enforcement_mode", "enforce")

        if result.valid:
            return _admission_response(uid, allowed=True)

        # Build violation summary
        violation_msgs = [
            f"[{v.severity.value}] {v.rule_id}: {v.rule_text}"
            for v in result.violations
        ]
        message = (
            "Constitutional violation(s) detected: "
            + "; ".join(violation_msgs)
        )

        if enforcement == "warn":
            logger.warning(
                "Admission warning (warn mode): %s", message,
            )
            return _admission_response(
                uid, allowed=True, message=message,
            )

        if enforcement == "audit":
            logger.info("Admission audit: %s", message)
            return _admission_response(
                uid, allowed=True, message=message,
            )

        # enforce mode — block
        has_blocking = any(
            v.severity.blocks() for v in result.violations
        )
        if has_blocking:
            return _admission_response(
                uid, allowed=False, message=message,
            )

        # Non-blocking violations in enforce mode still allow
        return _admission_response(
            uid, allowed=True, message=message,
        )

    def create_webhook_config(
        self,
        service_name: str,
        namespace: str,
        *,
        ca_bundle: str | None = None,
    ) -> dict[str, Any]:
        """Generate a ``ValidatingWebhookConfiguration`` manifest.

        Args:
            service_name: Name of the K8s Service fronting the webhook.
            namespace: Namespace where the webhook Service lives.
            ca_bundle: Base64-encoded CA bundle for TLS verification.

        Returns:
            A Kubernetes ``ValidatingWebhookConfiguration`` dict.
        """
        client_config: dict[str, Any] = {
            "service": {
                "name": service_name,
                "namespace": namespace,
                "path": "/validate",
            },
        }
        if ca_bundle is not None:
            client_config["caBundle"] = ca_bundle

        return {
            "apiVersion": "admissionregistration.k8s.io/v1",
            "kind": "ValidatingWebhookConfiguration",
            "metadata": {
                "name": f"{service_name}-governance",
                "labels": {
                    f"{_API_GROUP}/component": "admission-webhook",
                    f"{_API_GROUP}/constitutional-hash": (
                        self._engine.constitution.hash
                    ),
                },
            },
            "webhooks": [
                {
                    "name": f"governance.{_API_GROUP}",
                    "admissionReviewVersions": ["v1", "v1beta1"],
                    "sideEffects": "None",
                    "failurePolicy": "Fail",
                    "clientConfig": client_config,
                    "rules": [
                        {
                            "apiGroups": ["*"],
                            "apiVersions": ["*"],
                            "operations": [
                                "CREATE",
                                "UPDATE",
                            ],
                            "resources": ["*"],
                        },
                    ],
                },
            ],
        }


def _admission_response(
    uid: str,
    *,
    allowed: bool,
    message: str = "",
) -> dict[str, Any]:
    """Build a minimal AdmissionReview response."""
    response: dict[str, Any] = {
        "apiVersion": "admission.k8s.io/v1",
        "kind": "AdmissionReview",
        "response": {
            "uid": uid,
            "allowed": allowed,
        },
    }
    if message:
        response["response"]["status"] = {"message": message}
    return response


# ---------------------------------------------------------------------------
# PolicySyncController
# ---------------------------------------------------------------------------


class PolicySyncController:
    """Syncs constitutional policies between K8s and the governance engine.

    Reads constitution data from Kubernetes ConfigMaps and writes engine
    state back, keeping the cluster and the governance engine in sync.

    Args:
        engine: The governance engine to synchronise.
        namespace: Kubernetes namespace for the ConfigMap.
        config_map_name: Name of the ConfigMap storing the constitution.
    """

    def __init__(
        self,
        engine: GovernanceEngine,
        *,
        namespace: str = "default",
        config_map_name: str = "acgs-constitution",
    ) -> None:
        self._engine = engine
        self._namespace = namespace
        self._config_map_name = config_map_name
        self._last_sync: str | None = None

    def sync_from_config_map(
        self, data: dict[str, str],
    ) -> Constitution:
        """Parse ConfigMap data into a :class:`Constitution`.

        Expects the ConfigMap's ``data`` section where keys map to
        string values.  A key named ``constitution.yaml`` or
        ``constitution.json`` is parsed; otherwise all keys are treated
        as individual rule JSON blobs.

        Args:
            data: The ``data`` field from a Kubernetes ConfigMap.

        Returns:
            A new :class:`Constitution` built from the ConfigMap data.
        """
        if "constitution.yaml" in data:
            constitution = Constitution.from_yaml_str(
                data["constitution.yaml"],
            )
        elif "constitution.json" in data:
            raw = json.loads(data["constitution.json"])
            constitution = Constitution.from_dict(raw)
        else:
            # Treat each key as a JSON-encoded rule
            rules_data: list[dict[str, Any]] = []
            for key in sorted(data.keys()):
                try:
                    rule_dict = json.loads(data[key])
                    if isinstance(rule_dict, dict):
                        rules_data.append(rule_dict)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(
                        "Skipping non-JSON ConfigMap key: %s", key,
                    )
            constitution = Constitution.from_dict({"rules": rules_data})

        self._last_sync = datetime.now(timezone.utc).isoformat()
        return constitution

    def sync_to_config_map(
        self, constitution: Constitution,
    ) -> dict[str, Any]:
        """Serialize a :class:`Constitution` to ConfigMap format.

        Args:
            constitution: The constitution to serialize.

        Returns:
            A Kubernetes ConfigMap dict ready for ``kubectl apply``.
        """
        rules_data = [
            {
                "id": r.id,
                "text": r.text,
                "severity": r.severity.value,
                "keywords": r.keywords,
                "patterns": r.patterns,
                "category": r.category,
                "enabled": r.enabled,
            }
            for r in constitution.rules
        ]
        constitution_dict = {
            "name": constitution.name,
            "version": constitution.version,
            "rules": rules_data,
        }
        self._last_sync = datetime.now(timezone.utc).isoformat()
        return {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": self._config_map_name,
                "namespace": self._namespace,
                "labels": {
                    f"{_API_GROUP}/constitutional-hash": constitution.hash,
                    f"{_API_GROUP}/component": "constitution",
                },
            },
            "data": {
                "constitution.json": json.dumps(
                    constitution_dict, indent=2,
                ),
            },
        }

    def get_policy_status(self) -> dict[str, Any]:
        """Return the current sync status.

        Returns:
            Dict with ``hash``, ``last_sync``, ``rule_count``, and
            ``namespace`` fields.
        """
        return {
            "hash": self._engine.constitution.hash,
            "last_sync": self._last_sync,
            "rule_count": len(self._engine.constitution.rules),
            "namespace": self._namespace,
            "config_map_name": self._config_map_name,
        }


# ---------------------------------------------------------------------------
# GovernanceHealthCheck
# ---------------------------------------------------------------------------


class GovernanceHealthCheck:
    """Kubernetes health probe data for the governance engine.

    Provides structured responses suitable for Kubernetes liveness,
    readiness, and startup probes.

    Args:
        engine: The governance engine to monitor.
        audit_log: The audit log for chain-integrity checks.
    """

    def __init__(
        self,
        engine: GovernanceEngine,
        audit_log: AuditLog,
    ) -> None:
        self._engine = engine
        self._audit_log = audit_log

    def liveness(self) -> dict[str, Any]:
        """Liveness check: is the engine functional?

        Attempts a trivial validation to confirm the engine is alive.

        Returns:
            ``{"status": "ok"}`` if alive, ``{"status": "error", ...}``
            otherwise.
        """
        try:
            with self._engine.non_strict():
                self._engine.validate(
                    "health check ping",
                    agent_id="k8s-healthcheck",
                )
            return {"status": "ok"}
        except Exception as exc:
            return {
                "status": "error",
                "reason": type(exc).__name__,
            }

    def readiness(self) -> dict[str, Any]:
        """Readiness check: engine alive AND audit chain intact.

        Returns:
            ``{"status": "ok", ...}`` with details, or
            ``{"status": "not_ready", ...}`` on failure.
        """
        liveness = self.liveness()
        if liveness["status"] != "ok":
            return {
                "status": "not_ready",
                "reason": "engine_not_alive",
                "details": liveness,
            }

        chain_valid = self._audit_log.verify_chain()
        if not chain_valid:
            return {
                "status": "not_ready",
                "reason": "audit_chain_invalid",
            }

        return {
            "status": "ok",
            "constitutional_hash": self._engine.constitution.hash,
            "rules_count": len(self._engine.constitution.rules),
            "audit_entries": len(self._audit_log),
            "chain_valid": True,
        }

    def startup(self) -> dict[str, Any]:
        """Startup check: is a constitution loaded?

        Returns:
            ``{"status": "ok", ...}`` if constitution is loaded,
            ``{"status": "not_ready", ...}`` otherwise.
        """
        rules = self._engine.constitution.rules
        if not rules:
            return {
                "status": "not_ready",
                "reason": "no_rules_loaded",
            }

        return {
            "status": "ok",
            "constitutional_hash": self._engine.constitution.hash,
            "rules_count": len(rules),
            "constitution_name": self._engine.constitution.name,
        }


# ---------------------------------------------------------------------------
# Manifest generators
# ---------------------------------------------------------------------------


def create_crd_manifest() -> dict[str, Any]:
    """Generate the ConstitutionalPolicy CRD manifest.

    Returns:
        A Kubernetes ``CustomResourceDefinition`` dict ready for
        ``kubectl apply``.
    """
    return {
        "apiVersion": "apiextensions.k8s.io/v1",
        "kind": "CustomResourceDefinition",
        "metadata": {
            "name": f"{_CRD_PLURAL}.{_API_GROUP}",
        },
        "spec": {
            "group": _API_GROUP,
            "names": {
                "kind": _CRD_KIND,
                "listKind": f"{_CRD_KIND}List",
                "plural": _CRD_PLURAL,
                "singular": "constitutionalpolicy",
                "shortNames": ["cp", "cpolicy"],
            },
            "scope": "Namespaced",
            "versions": [
                {
                    "name": _API_VERSION,
                    "served": True,
                    "storage": True,
                    "schema": {
                        "openAPIV3Schema": {
                            "type": "object",
                            "properties": {
                                "spec": {
                                    "type": "object",
                                    "properties": {
                                        "rules": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "id": {
                                                        "type": "string",
                                                    },
                                                    "text": {
                                                        "type": "string",
                                                    },
                                                    "severity": {
                                                        "type": "string",
                                                        "enum": [
                                                            s.value
                                                            for s in Severity
                                                        ],
                                                    },
                                                    "keywords": {
                                                        "type": "array",
                                                        "items": {
                                                            "type": "string",
                                                        },
                                                    },
                                                    "category": {
                                                        "type": "string",
                                                    },
                                                    "enabled": {
                                                        "type": "boolean",
                                                    },
                                                },
                                                "required": [
                                                    "id",
                                                    "text",
                                                ],
                                            },
                                        },
                                        "constitutionalHash": {
                                            "type": "string",
                                        },
                                        "enforcementMode": {
                                            "type": "string",
                                            "enum": sorted(
                                                _VALID_ENFORCEMENT_MODES,
                                            ),
                                        },
                                    },
                                    "required": [
                                        "rules",
                                        "constitutionalHash",
                                    ],
                                },
                            },
                        },
                    },
                    "additionalPrinterColumns": [
                        {
                            "name": "Hash",
                            "type": "string",
                            "jsonPath": ".spec.constitutionalHash",
                        },
                        {
                            "name": "Mode",
                            "type": "string",
                            "jsonPath": ".spec.enforcementMode",
                        },
                        {
                            "name": "Rules",
                            "type": "integer",
                            "jsonPath": ".spec.rules",
                            "description": "Number of rules",
                        },
                        {
                            "name": "Age",
                            "type": "date",
                            "jsonPath": ".metadata.creationTimestamp",
                        },
                    ],
                },
            ],
        },
    }


def create_deployment_manifest(
    image: str,
    namespace: str = "acgs-system",
    replicas: int = 2,
) -> dict[str, Any]:
    """Generate a Kubernetes Deployment for the governance webhook.

    Args:
        image: Container image reference.
        namespace: Target namespace.
        replicas: Number of replicas.

    Returns:
        A Kubernetes ``Deployment`` dict ready for ``kubectl apply``.
    """
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": "acgs-governance-webhook",
            "namespace": namespace,
            "labels": {
                f"{_API_GROUP}/component": "admission-webhook",
                "app.kubernetes.io/name": "acgs-governance-webhook",
                "app.kubernetes.io/part-of": "acgs",
            },
        },
        "spec": {
            "replicas": replicas,
            "selector": {
                "matchLabels": {
                    "app.kubernetes.io/name": "acgs-governance-webhook",
                },
            },
            "template": {
                "metadata": {
                    "labels": {
                        "app.kubernetes.io/name": (
                            "acgs-governance-webhook"
                        ),
                        f"{_API_GROUP}/component": "admission-webhook",
                    },
                },
                "spec": {
                    "containers": [
                        {
                            "name": "governance-webhook",
                            "image": image,
                            "ports": [
                                {
                                    "containerPort": 8443,
                                    "protocol": "TCP",
                                },
                            ],
                            "livenessProbe": {
                                "httpGet": {
                                    "path": "/healthz",
                                    "port": 8443,
                                    "scheme": "HTTPS",
                                },
                                "initialDelaySeconds": 5,
                                "periodSeconds": 10,
                            },
                            "readinessProbe": {
                                "httpGet": {
                                    "path": "/readyz",
                                    "port": 8443,
                                    "scheme": "HTTPS",
                                },
                                "initialDelaySeconds": 3,
                                "periodSeconds": 5,
                            },
                            "resources": {
                                "requests": {
                                    "cpu": "100m",
                                    "memory": "128Mi",
                                },
                                "limits": {
                                    "cpu": "500m",
                                    "memory": "256Mi",
                                },
                            },
                            "env": [
                                {
                                    "name": "CONSTITUTION_PATH",
                                    "value": (
                                        "/etc/acgs/constitution.yaml"
                                    ),
                                },
                            ],
                            "volumeMounts": [
                                {
                                    "name": "constitution",
                                    "mountPath": "/etc/acgs",
                                    "readOnly": True,
                                },
                                {
                                    "name": "tls-certs",
                                    "mountPath": "/etc/tls",
                                    "readOnly": True,
                                },
                            ],
                        },
                    ],
                    "volumes": [
                        {
                            "name": "constitution",
                            "configMap": {
                                "name": "acgs-constitution",
                            },
                        },
                        {
                            "name": "tls-certs",
                            "secret": {
                                "secretName": (
                                    "acgs-governance-webhook-tls"
                                ),
                            },
                        },
                    ],
                },
            },
        },
    }
