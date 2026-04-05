"""
Coverage tests for:
- enhanced_agent_bus/bundle_registry.py (90.9% -> target 97%+)
- enhanced_agent_bus/constitutional/review_api.py (84.6% -> target 97%+)

Constitutional Hash: 608508a9bd224290

Targets uncovered lines:
  bundle_registry: verify_signature paths, verify_cosign_signature, push_bundle,
    pull_bundle helpers, sign_manifest, copy_bundle, replicate_from,
    BundleDistributionService.publish/fetch/get_ab_test_bundle,
    AWSECRAuthProvider.refresh_token, OCIRegistryClientAdapter,
    close_distribution_service with fallbacks, _session property alias
  review_api: approve_amendment, reject_amendment, rollback_to_version,
    list_amendments success, get_amendment with metrics/diff branches,
    error paths (500s)
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from enhanced_agent_bus._compat.errors import (
    ConstitutionalViolationError as ACGSConstitutionalViolationError,
)

# ---------------------------------------------------------------------------
# bundle_registry imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.bundle_registry import (
    CONSTITUTIONAL_HASH,
    AWSECRAuthProvider,
    BasicAuthProvider,
    BundleArtifact,
    BundleDistributionService,
    BundleManifest,
    BundleStatus,
    OCIRegistryClient,
    OCIRegistryClientAdapter,
    RegistryType,
    close_distribution_service,
    get_distribution_service,
    initialize_distribution_service,
)

# ---------------------------------------------------------------------------
# review_api imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.constitutional.amendment_model import (
    AmendmentProposal,
    AmendmentStatus,
)
from enhanced_agent_bus.constitutional.diff_engine import SemanticDiff
from enhanced_agent_bus.constitutional.review_api import (
    AmendmentDetailResponse,
    AmendmentListQuery,
    AmendmentListResponse,
    ApprovalRequest,
    ApprovalResponse,
    RejectionRequest,
    RollbackRequest,
    RollbackResponse,
    approve_amendment,
    get_amendment,
    health_check,
    list_amendments,
    reject_amendment,
    rollback_to_version,
)
from enhanced_agent_bus.constitutional.version_model import (
    ConstitutionalVersion,
)

_MISSING = object()


@contextmanager
def _review_api_patch(name: str, value=_MISSING, **kwargs):
    namespace = list_amendments.__globals__
    original = namespace.get(name, _MISSING)

    if value is _MISSING:
        new_callable = kwargs.pop("new_callable", MagicMock)
        replacement = new_callable()
        if hasattr(replacement, "configure_mock"):
            replacement.configure_mock(**kwargs)
        else:
            for key, attr_value in kwargs.items():
                setattr(replacement, key, attr_value)
    else:
        if kwargs:
            raise TypeError("Direct-value patches do not accept mock keyword arguments")
        replacement = value

    namespace[name] = replacement
    try:
        yield replacement
    finally:
        if original is _MISSING:
            namespace.pop(name, None)
        else:
            namespace[name] = original


# ============================================================================
# Helpers
# ============================================================================


def _make_amendment(
    *,
    status: AmendmentStatus = AmendmentStatus.UNDER_REVIEW,
    impact_score: float | None = 0.5,
    proposed_changes: dict | str | None = None,
    governance_metrics_before: dict | None = None,
    governance_metrics_after: dict | None = None,
    approval_chain: list | None = None,
) -> AmendmentProposal:
    return AmendmentProposal(
        proposed_changes=proposed_changes or {"rules": {"new_rule": "value"}},
        justification="This amendment improves governance significantly",
        proposer_agent_id="agent-proposer-1",
        target_version="1.0.0",
        status=status,
        impact_score=impact_score,
        governance_metrics_before=governance_metrics_before or {},
        governance_metrics_after=governance_metrics_after or {},
        approval_chain=approval_chain or [],
    )


def _make_version(
    *,
    version: str = "1.0.0",
    version_id: str = "v-1",
    predecessor: str | None = None,
) -> ConstitutionalVersion:
    return ConstitutionalVersion(
        version_id=version_id,
        version=version,
        content={"rules": {"rule_1": "test"}},
        predecessor_version=predecessor,
    )


def _gen_ed25519_keypair():
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    priv_bytes = private_key.private_bytes_raw().hex()
    pub_bytes = public_key.public_bytes_raw().hex()
    return priv_bytes, pub_bytes


def _make_manifest(**overrides):
    defaults = {
        "version": "1.0.0",
        "revision": "a" * 40,
    }
    defaults.update(overrides)
    return BundleManifest(**defaults)


def _make_semantic_diff() -> SemanticDiff:
    return SemanticDiff(
        from_version="1.0.0",
        to_version="2.0.0",
        from_version_id="v-1",
        to_version_id="v-2",
        from_hash="aaa",
        to_hash="bbb",
        hash_changed=True,
    )


def _mock_httpx_response(status_code=200, json_data=None, headers=None, content=b""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.headers = headers or {}
    resp.read.return_value = content
    resp.content = content
    return resp


# ============================================================================
# SECTION 1: bundle_registry.py coverage
# ============================================================================


class TestBundleManifestSignatureVerification:
    """Cover verify_signature branches: valid sig, invalid sig, unsupported alg, cosign."""

    def test_verify_signature_valid(self):
        priv_hex, pub_hex = _gen_ed25519_keypair()
        manifest = _make_manifest()
        # Sign the manifest content
        manifest_data = manifest.to_dict()
        manifest_data.pop("signatures", [])
        content = json.dumps(manifest_data, sort_keys=True).encode()
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv_hex))
        sig = private_key.sign(content).hex()
        manifest.add_signature(keyid="key-1", signature=sig, algorithm="ed25519")
        assert manifest.verify_signature(pub_hex) is True

    def test_verify_signature_invalid_sig(self):
        _priv_hex, pub_hex = _gen_ed25519_keypair()
        manifest = _make_manifest()
        manifest.add_signature(keyid="key-1", signature="ab" * 32, algorithm="ed25519")
        assert manifest.verify_signature(pub_hex) is False

    def test_verify_signature_unsupported_algorithm_skipped(self):
        _priv_hex, pub_hex = _gen_ed25519_keypair()
        manifest = _make_manifest()
        manifest.add_signature(keyid="key-1", signature="ab" * 32, algorithm="rsa-pss-sha256")
        assert manifest.verify_signature(pub_hex) is False

    def test_verify_signature_mixed_algorithms(self):
        """At least one valid ed25519 sig among mixed algs returns True."""
        priv_hex, pub_hex = _gen_ed25519_keypair()
        manifest = _make_manifest()
        manifest_data = manifest.to_dict()
        manifest_data.pop("signatures", [])
        content = json.dumps(manifest_data, sort_keys=True).encode()
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv_hex))
        sig = private_key.sign(content).hex()
        # Add unsupported alg first
        manifest.add_signature(keyid="rsa-key", signature="ff" * 32, algorithm="ecdsa-p256-sha256")
        # Add valid ed25519
        manifest.add_signature(keyid="ed-key", signature=sig, algorithm="ed25519")
        assert manifest.verify_signature(pub_hex) is True

    def test_verify_signature_invalid_public_key(self):
        manifest = _make_manifest()
        manifest.add_signature(keyid="key-1", signature="ab" * 32, algorithm="ed25519")
        assert manifest.verify_signature("not-hex-key") is False

    def test_verify_signature_empty_signatures(self):
        _priv_hex, pub_hex = _gen_ed25519_keypair()
        manifest = _make_manifest()
        assert manifest.verify_signature(pub_hex) is False


class TestBundleManifestCosignVerification:
    """Cover verify_cosign_signature branches."""

    def test_cosign_valid(self):
        priv_hex, pub_hex = _gen_ed25519_keypair()
        manifest = _make_manifest()
        digest = "sha256:abc123"
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv_hex))
        sig = private_key.sign(digest.encode()).hex()
        manifest.add_signature(keyid="cosign-key", signature=sig, algorithm="ed25519")
        assert manifest.verify_cosign_signature(digest, pub_hex) is True

    def test_cosign_invalid_signature(self):
        _priv_hex, pub_hex = _gen_ed25519_keypair()
        manifest = _make_manifest()
        manifest.add_signature(keyid="cosign-key", signature="dd" * 32, algorithm="ed25519")
        assert manifest.verify_cosign_signature("sha256:abc123", pub_hex) is False

    def test_cosign_no_signatures(self):
        _priv_hex, pub_hex = _gen_ed25519_keypair()
        manifest = _make_manifest()
        assert manifest.verify_cosign_signature("sha256:abc123", pub_hex) is False

    def test_cosign_invalid_public_key(self):
        manifest = _make_manifest()
        manifest.add_signature(keyid="k", signature="ab" * 32, algorithm="ed25519")
        assert manifest.verify_cosign_signature("sha256:abc123", "bad-key") is False

    def test_cosign_skips_non_ed25519(self):
        _priv_hex, pub_hex = _gen_ed25519_keypair()
        manifest = _make_manifest()
        manifest.add_signature(keyid="k", signature="ab" * 32, algorithm="rsa-pss-sha256")
        assert manifest.verify_cosign_signature("sha256:abc123", pub_hex) is False


class TestOCIRegistryClientPushPull:
    """Cover push_bundle, pull_bundle, and helper methods."""

    async def test_push_bundle_blob_exists(self):
        client = OCIRegistryClient("https://registry.example.com")
        mock_client = AsyncMock()
        client._client = mock_client

        # HEAD returns 200 (blob exists)
        mock_client.head.return_value = _mock_httpx_response(200)
        # PUT manifest returns 201
        mock_client.put.return_value = _mock_httpx_response(
            201, headers={"Docker-Content-Digest": "sha256:manifest-digest"}
        )

        manifest = _make_manifest()
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as f:
            f.write(b"test-bundle-data")
            tmp_path = f.name
        try:
            digest, artifact = await client.push_bundle("acgs/test", "v1.0.0", tmp_path, manifest)
            assert "sha256:" in digest or digest == "sha256:manifest-digest"
            assert artifact.size > 0
            assert client._stats["pushes"] == 1
        finally:
            os.unlink(tmp_path)

    async def test_push_bundle_blob_upload(self):
        client = OCIRegistryClient("https://registry.example.com")
        mock_client = AsyncMock()
        client._client = mock_client

        # HEAD returns 404 (blob doesn't exist)
        mock_client.head.return_value = _mock_httpx_response(404)
        # POST upload init returns 202 with Location
        mock_client.post.return_value = _mock_httpx_response(
            202, headers={"Location": "https://registry.example.com/upload/123"}
        )
        # PUT upload blob returns 201
        # PUT manifest returns 201
        mock_client.put.side_effect = [
            _mock_httpx_response(201),  # blob upload
            _mock_httpx_response(201, headers={"Docker-Content-Digest": "sha256:abc"}),  # manifest
        ]

        manifest = _make_manifest()
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as f:
            f.write(b"test-bundle-data-new")
            tmp_path = f.name
        try:
            digest, artifact = await client.push_bundle("acgs/test", "v1.0.0", tmp_path, manifest)
            assert client._stats["pushes"] == 1
        finally:
            os.unlink(tmp_path)

    async def test_push_bundle_constitutional_hash_mismatch(self):
        client = OCIRegistryClient("https://registry.example.com")
        client._client = AsyncMock()
        manifest = _make_manifest()
        # Forcibly change the hash after creation
        object.__setattr__(manifest, "constitutional_hash", "wrong-hash")
        with pytest.raises(ACGSConstitutionalViolationError):
            await client.push_bundle("acgs/test", "v1.0.0", "/tmp/fake.tar.gz", manifest)

    async def test_pull_bundle_success(self):
        client = OCIRegistryClient("https://registry.example.com")
        mock_client = AsyncMock()
        client._client = mock_client

        bundle_data = b"pulled-bundle-content"
        bundle_digest = f"sha256:{hashlib.sha256(bundle_data).hexdigest()}"

        oci_manifest = {
            "layers": [
                {
                    "digest": bundle_digest,
                    "annotations": {
                        "io.acgs.constitutional_hash": CONSTITUTIONAL_HASH,
                        "io.acgs.version": "1.0.0",
                        "io.acgs.revision": "b" * 40,
                    },
                }
            ],
            "annotations": {
                "org.opencontainers.image.created": datetime.now(UTC).isoformat(),
                "io.acgs.signatures": "[]",
            },
        }

        # GET manifest
        mock_client.get.side_effect = [
            _mock_httpx_response(200, json_data=oci_manifest),  # manifest fetch
            _mock_httpx_response(200, content=bundle_data),  # blob download
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "bundle.tar.gz")
            manifest, path = await client.pull_bundle("acgs/test", "v1.0.0", output_path)
            assert manifest.version == "1.0.0"
            assert client._stats["pulls"] == 1

    async def test_pull_bundle_no_layers_raises(self):
        client = OCIRegistryClient("https://registry.example.com")
        mock_client = AsyncMock()
        client._client = mock_client

        mock_client.get.return_value = _mock_httpx_response(200, json_data={"layers": []})

        with pytest.raises(Exception, match="No layers"):
            await client.pull_bundle("acgs/test", "v1.0.0", "/tmp/out.tar.gz")

    async def test_pull_bundle_hash_mismatch(self):
        client = OCIRegistryClient("https://registry.example.com")
        mock_client = AsyncMock()
        client._client = mock_client

        oci_manifest = {
            "layers": [
                {
                    "digest": "sha256:abc",
                    "annotations": {"io.acgs.constitutional_hash": "wrong-hash"},
                }
            ],
            "annotations": {},
        }
        mock_client.get.return_value = _mock_httpx_response(200, json_data=oci_manifest)

        with pytest.raises(Exception, match="hash"):
            await client.pull_bundle("acgs/test", "v1.0.0", "/tmp/out.tar.gz")

    async def test_pull_bundle_with_signature_verification(self):
        priv_hex, pub_hex = _gen_ed25519_keypair()
        client = OCIRegistryClient("https://registry.example.com")
        mock_client = AsyncMock()
        client._client = mock_client

        bundle_data = b"signed-bundle"
        bundle_digest = f"sha256:{hashlib.sha256(bundle_data).hexdigest()}"

        # Create a valid signature
        manifest_for_sig = _make_manifest(
            version="1.0.0",
            revision="c" * 40,
            timestamp=datetime.now(UTC).isoformat(),
        )
        manifest_data = manifest_for_sig.to_dict()
        manifest_data.pop("signatures", [])
        content = json.dumps(manifest_data, sort_keys=True).encode()
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv_hex))
        sig = private_key.sign(content).hex()

        oci_manifest = {
            "layers": [
                {
                    "digest": bundle_digest,
                    "annotations": {
                        "io.acgs.constitutional_hash": CONSTITUTIONAL_HASH,
                        "io.acgs.version": "1.0.0",
                        "io.acgs.revision": "c" * 40,
                    },
                }
            ],
            "annotations": {
                "org.opencontainers.image.created": manifest_for_sig.timestamp,
                "io.acgs.signatures": json.dumps(
                    [{"keyid": "k1", "sig": sig, "alg": "ed25519", "timestamp": "now"}]
                ),
            },
        }

        mock_client.get.side_effect = [
            _mock_httpx_response(200, json_data=oci_manifest),
            _mock_httpx_response(200, content=bundle_data),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "bundle.tar.gz")
            manifest, path = await client.pull_bundle(
                "acgs/test", "v1.0.0", output_path, public_key_hex=pub_hex
            )
            assert manifest.version == "1.0.0"

    async def test_pull_bundle_signature_verification_fails(self):
        _priv_hex, pub_hex = _gen_ed25519_keypair()
        client = OCIRegistryClient("https://registry.example.com")
        mock_client = AsyncMock()
        client._client = mock_client

        bundle_data = b"unsigned-bundle"
        bundle_digest = f"sha256:{hashlib.sha256(bundle_data).hexdigest()}"

        oci_manifest = {
            "layers": [
                {
                    "digest": bundle_digest,
                    "annotations": {
                        "io.acgs.constitutional_hash": CONSTITUTIONAL_HASH,
                        "io.acgs.version": "1.0.0",
                        "io.acgs.revision": "d" * 40,
                    },
                }
            ],
            "annotations": {
                "org.opencontainers.image.created": datetime.now(UTC).isoformat(),
                "io.acgs.signatures": json.dumps(
                    [{"keyid": "k", "sig": "ff" * 32, "alg": "ed25519", "timestamp": "now"}]
                ),
            },
        }

        mock_client.get.return_value = _mock_httpx_response(200, json_data=oci_manifest)

        with pytest.raises(Exception, match="Signature"):
            await client.pull_bundle(
                "acgs/test", "v1.0.0", "/tmp/out.tar.gz", public_key_hex=pub_hex
            )

    async def test_validate_layer_digest_mismatch(self):
        client = OCIRegistryClient("https://registry.example.com")
        with pytest.raises(Exception, match="Digest mismatch"):
            client._validate_layer_digest(b"data", "sha256:wrongdigest", 0)

    async def test_validate_layer_digest_success(self):
        client = OCIRegistryClient("https://registry.example.com")
        data = b"test-data"
        expected = f"sha256:{hashlib.sha256(data).hexdigest()}"
        # Should not raise
        client._validate_layer_digest(data, expected, 0)


class TestOCIRegistryClientSignManifest:
    """Cover sign_manifest method."""

    async def test_sign_manifest_success(self):
        priv_hex, _pub_hex = _gen_ed25519_keypair()
        client = OCIRegistryClient("https://registry.example.com")
        client._client = AsyncMock()

        sig_hex = await client.sign_manifest(
            "acgs/test", "v1.0.0", "sha256:manifest-digest", priv_hex
        )
        assert len(sig_hex) > 0

    async def test_sign_manifest_invalid_key(self):
        client = OCIRegistryClient("https://registry.example.com")
        client._client = AsyncMock()

        with pytest.raises((ValueError, TypeError, OSError)):
            await client.sign_manifest("acgs/test", "v1.0.0", "sha256:digest", "bad-key")


class TestOCIRegistryClientMisc:
    """Cover check_health, list_tags, delete_tag, copy_bundle, replicate_from, _session alias."""

    async def test_check_health_success(self):
        client = OCIRegistryClient("https://registry.example.com")
        mock_client = AsyncMock()
        client._client = mock_client
        mock_client.get.return_value = _mock_httpx_response(200)
        assert await client.check_health() is True

    async def test_check_health_failure(self):
        client = OCIRegistryClient("https://registry.example.com")
        mock_client = AsyncMock()
        client._client = mock_client
        mock_client.get.side_effect = ConnectionError("down")
        assert await client.check_health() is False

    async def test_check_health_non_200(self):
        client = OCIRegistryClient("https://registry.example.com")
        mock_client = AsyncMock()
        client._client = mock_client
        mock_client.get.return_value = _mock_httpx_response(503)
        assert await client.check_health() is False

    async def test_list_tags_success(self):
        client = OCIRegistryClient("https://registry.example.com")
        mock_client = AsyncMock()
        client._client = mock_client
        mock_client.get.return_value = _mock_httpx_response(
            200, json_data={"tags": ["v1.0.0", "v1.1.0"]}
        )
        tags = await client.list_tags("acgs/test")
        assert tags == ["v1.0.0", "v1.1.0"]

    async def test_list_tags_empty(self):
        client = OCIRegistryClient("https://registry.example.com")
        mock_client = AsyncMock()
        client._client = mock_client
        mock_client.get.return_value = _mock_httpx_response(404)
        tags = await client.list_tags("acgs/test")
        assert tags == []

    async def test_delete_tag_success(self):
        client = OCIRegistryClient("https://registry.example.com")
        mock_client = AsyncMock()
        client._client = mock_client
        mock_client.delete.return_value = _mock_httpx_response(202)
        result = await client.delete_tag("acgs/test", "v1.0.0")
        assert result is True

    async def test_delete_tag_failure(self):
        client = OCIRegistryClient("https://registry.example.com")
        mock_client = AsyncMock()
        client._client = mock_client
        mock_client.delete.return_value = _mock_httpx_response(404)
        result = await client.delete_tag("acgs/test", "v1.0.0")
        assert result is False

    async def test_get_headers_ecr_auth(self):
        provider = MagicMock()
        provider.get_token = AsyncMock(return_value="ecr-token")
        client = OCIRegistryClient(
            "https://ecr.example.com",
            auth_provider=provider,
            registry_type=RegistryType.ECR,
        )
        headers = await client._get_headers()
        assert headers["Authorization"] == "Basic ecr-token"

    async def test_get_headers_bearer_auth(self):
        provider = MagicMock()
        provider.get_token = AsyncMock(return_value="bearer-token")
        client = OCIRegistryClient(
            "https://registry.example.com",
            auth_provider=provider,
            registry_type=RegistryType.GENERIC,
        )
        headers = await client._get_headers()
        assert headers["Authorization"] == "Bearer bearer-token"

    async def test_get_headers_no_auth(self):
        client = OCIRegistryClient("https://registry.example.com")
        headers = await client._get_headers()
        assert "Authorization" not in headers

    def test_session_property_alias_getter(self):
        client = OCIRegistryClient("https://registry.example.com")
        assert client._session is None
        mock = MagicMock()
        client._client = mock
        assert client._session is mock

    def test_session_property_alias_setter(self):
        client = OCIRegistryClient("https://registry.example.com")
        mock = MagicMock()
        client._session = mock
        assert client._client is mock

    def test_get_stats(self):
        client = OCIRegistryClient(
            "https://registry.example.com", registry_type=RegistryType.HARBOR
        )
        stats = client.get_stats()
        assert stats["pushes"] == 0
        assert stats["type"] == "harbor"
        assert stats["registry"] == "registry.example.com"


class TestOCIRegistryClientReplicateAndCopy:
    """Cover replicate_from and copy_bundle."""

    async def test_replicate_from(self):
        src_client = OCIRegistryClient("https://src-registry.example.com")
        dst_client = OCIRegistryClient("https://dst-registry.example.com")

        manifest = _make_manifest()
        src_client.pull_bundle = AsyncMock(return_value=(manifest, "/tmp/bundle.tar.gz"))
        dst_client.push_bundle = AsyncMock(return_value=("sha256:replicated", MagicMock()))

        digest = await dst_client.replicate_from(src_client, "acgs/test", "v1.0.0")
        assert digest == "sha256:replicated"

    async def test_replicate_from_with_target_tag(self):
        src_client = OCIRegistryClient("https://src-registry.example.com")
        dst_client = OCIRegistryClient("https://dst-registry.example.com")

        manifest = _make_manifest()
        src_client.pull_bundle = AsyncMock(return_value=(manifest, "/tmp/bundle.tar.gz"))
        dst_client.push_bundle = AsyncMock(return_value=("sha256:custom", MagicMock()))

        digest = await dst_client.replicate_from(
            src_client, "acgs/test", "v1.0.0", target_tag="v1.0.0-mirror"
        )
        assert digest == "sha256:custom"

    async def test_copy_bundle(self):
        client = OCIRegistryClient("https://registry.example.com")

        manifest = _make_manifest()
        client.pull_bundle = AsyncMock(return_value=(manifest, "/tmp/bundle.tar.gz"))
        client.push_bundle = AsyncMock(return_value=("sha256:copied", MagicMock()))

        digest = await client.copy_bundle("acgs/src", "v1.0.0", "acgs/dst", "v1.0.0-copy")
        assert digest == "sha256:copied"


class TestAWSECRAuthProvider:
    """Cover AWSECRAuthProvider token caching and refresh."""

    async def test_get_token_returns_cached(self):
        provider = AWSECRAuthProvider(region="us-east-1")
        provider._token = "cached-token"
        provider._expiry = datetime(2099, 1, 1, tzinfo=UTC)
        token = await provider.get_token()
        assert token == "cached-token"

    async def test_get_token_expired_refreshes(self):
        provider = AWSECRAuthProvider(region="us-east-1")
        provider._token = "old-token"
        provider._expiry = datetime(2000, 1, 1, tzinfo=UTC)
        # Mock boto3 import failure path
        with patch.dict("sys.modules", {"boto3": None}):
            with patch.dict(os.environ, {"AWS_ECR_TOKEN": "env-token"}):
                token = await provider.refresh_token()
                assert token == "env-token"

    async def test_refresh_token_boto3_missing(self):
        provider = AWSECRAuthProvider(region="us-east-1")
        with patch.dict("sys.modules", {"boto3": None}):
            with patch.dict(os.environ, {"AWS_ECR_TOKEN": "fallback-token"}):
                token = await provider.refresh_token()
                assert token == "fallback-token"

    def test_custom_profile(self):
        provider = AWSECRAuthProvider(region="eu-west-1", profile="staging")
        assert provider.profile == "staging"
        assert provider.region == "eu-west-1"


class TestBundleDistributionServicePublish:
    """Cover publish with replicas."""

    async def test_publish_with_replication(self):
        primary = OCIRegistryClient("https://primary.example.com")
        fallback = OCIRegistryClient("https://fallback.example.com")

        primary.push_bundle = AsyncMock(return_value=("sha256:primary", MagicMock()))
        fallback.push_bundle = AsyncMock(return_value=("sha256:fallback", MagicMock()))

        with tempfile.TemporaryDirectory() as tmpdir:
            service = BundleDistributionService(primary, [fallback], cache_dir=tmpdir)
            manifest = _make_manifest()
            results = await service.publish("acgs/test", "v1.0.0", "/tmp/b.tar.gz", manifest)
            assert results["primary"]["digest"] == "sha256:primary"
            assert len(results["replicas"]) == 1
            assert results["replicas"][0]["status"] == "success"

    async def test_publish_replica_failure(self):
        primary = OCIRegistryClient("https://primary.example.com")
        fallback = OCIRegistryClient("https://fallback.example.com")

        primary.push_bundle = AsyncMock(return_value=("sha256:primary", MagicMock()))
        fallback.push_bundle = AsyncMock(side_effect=RuntimeError("replica down"))

        with tempfile.TemporaryDirectory() as tmpdir:
            service = BundleDistributionService(primary, [fallback], cache_dir=tmpdir)
            manifest = _make_manifest()
            results = await service.publish("acgs/test", "v1.0.0", "/tmp/b.tar.gz", manifest)
            assert results["replicas"][0]["status"] == "failed"

    async def test_publish_no_replicate(self):
        primary = OCIRegistryClient("https://primary.example.com")
        primary.push_bundle = AsyncMock(return_value=("sha256:primary", MagicMock()))

        with tempfile.TemporaryDirectory() as tmpdir:
            service = BundleDistributionService(primary, cache_dir=tmpdir)
            manifest = _make_manifest()
            results = await service.publish(
                "acgs/test", "v1.0.0", "/tmp/b.tar.gz", manifest, replicate=False
            )
            assert results["replicas"] == []


class TestBundleDistributionServiceFetch:
    """Cover fetch with failover, cache, and LKG."""

    async def test_fetch_from_cache(self):
        primary = OCIRegistryClient("https://primary.example.com")
        with tempfile.TemporaryDirectory() as tmpdir:
            service = BundleDistributionService(primary, cache_dir=tmpdir)
            # Create cached bundle and manifest
            cache_path = os.path.join(tmpdir, "acgs_test_v1.0.0.tar.gz")
            with open(cache_path, "wb") as f:
                f.write(b"cached-data")
            manifest_data = _make_manifest().to_dict()
            with open(cache_path + ".manifest.json", "w") as f:
                json.dump(manifest_data, f)

            manifest, path = await service.fetch("acgs/test", "v1.0.0", use_cache=True)
            assert manifest.version == "1.0.0"

    async def test_fetch_primary_success(self):
        primary = OCIRegistryClient("https://primary.example.com")
        manifest_obj = _make_manifest()
        primary.pull_bundle = AsyncMock(return_value=(manifest_obj, "/tmp/bundle.tar.gz"))

        with tempfile.TemporaryDirectory() as tmpdir:
            service = BundleDistributionService(primary, cache_dir=tmpdir)
            manifest, path = await service.fetch("acgs/test", "v1.0.0", use_cache=False)
            assert manifest.version == "1.0.0"
            assert service._lkg_manifest is manifest_obj

    async def test_fetch_fallback_on_primary_failure(self):
        primary = OCIRegistryClient("https://primary.example.com")
        fallback = OCIRegistryClient("https://fallback.example.com")

        primary.pull_bundle = AsyncMock(side_effect=RuntimeError("primary down"))
        manifest_obj = _make_manifest()
        fallback.pull_bundle = AsyncMock(return_value=(manifest_obj, "/tmp/bundle.tar.gz"))

        with tempfile.TemporaryDirectory() as tmpdir:
            service = BundleDistributionService(primary, [fallback], cache_dir=tmpdir)
            manifest, path = await service.fetch("acgs/test", "v1.0.0", use_cache=False)
            assert manifest.version == "1.0.0"

    async def test_fetch_lkg_on_all_failure(self):
        primary = OCIRegistryClient("https://primary.example.com")
        primary.pull_bundle = AsyncMock(side_effect=RuntimeError("down"))

        with tempfile.TemporaryDirectory() as tmpdir:
            service = BundleDistributionService(primary, cache_dir=tmpdir)
            lkg_manifest = _make_manifest()
            service._lkg_manifest = lkg_manifest
            service._lkg_path = "/tmp/lkg.tar.gz"

            manifest, path = await service.fetch("acgs/test", "v1.0.0", use_cache=False)
            assert manifest is lkg_manifest

    async def test_fetch_all_fail_no_lkg(self):
        primary = OCIRegistryClient("https://primary.example.com")
        primary.pull_bundle = AsyncMock(side_effect=RuntimeError("down"))

        with tempfile.TemporaryDirectory() as tmpdir:
            service = BundleDistributionService(primary, cache_dir=tmpdir)
            with pytest.raises(Exception, match="All registries failed"):
                await service.fetch("acgs/test", "v1.0.0", use_cache=False)

    async def test_fetch_path_traversal_rejected(self):
        """Verify the SECURITY path-traversal guard triggers when resolved path escapes cache_dir."""
        primary = OCIRegistryClient("https://primary.example.com")
        with tempfile.TemporaryDirectory() as tmpdir:
            service = BundleDistributionService(primary, cache_dir=tmpdir)
            # Monkey-patch cache_dir to a subdirectory so the default join escapes it
            nested = os.path.join(tmpdir, "deep", "nested")
            os.makedirs(nested, exist_ok=True)
            service.cache_dir = nested
            # A reference containing ".." that resolves outside nested/
            with pytest.raises((ValueError, Exception)):
                await service.fetch("repo", "../../escape", use_cache=False)


class TestBundleDistributionServiceABTest:
    """Cover get_ab_test_bundle."""

    async def test_ab_test_variant_found(self):
        primary = OCIRegistryClient("https://primary.example.com")
        manifest_obj = _make_manifest()
        primary.pull_bundle = AsyncMock(return_value=(manifest_obj, "/tmp/bundle.tar.gz"))

        with tempfile.TemporaryDirectory() as tmpdir:
            service = BundleDistributionService(primary, cache_dir=tmpdir)
            manifest, path = await service.get_ab_test_bundle(
                "acgs/test", "v1.0.0", "exp-1", "variant-a"
            )
            assert manifest.version == "1.0.0"

    async def test_ab_test_fallback_to_base(self):
        primary = OCIRegistryClient("https://primary.example.com")
        manifest_obj = _make_manifest()
        # First call (experiment tag) fails, second (base tag) succeeds
        primary.pull_bundle = AsyncMock(
            side_effect=[RuntimeError("not found"), (manifest_obj, "/tmp/bundle.tar.gz")]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            service = BundleDistributionService(primary, cache_dir=tmpdir)
            manifest, path = await service.get_ab_test_bundle(
                "acgs/test", "v1.0.0", "exp-1", "variant-b"
            )
            assert manifest.version == "1.0.0"


class TestOCIRegistryClientAdapter:
    """Cover OCIRegistryClientAdapter delegation."""

    async def test_adapter_push_bundle(self):
        inner = MagicMock()
        inner.push_bundle = AsyncMock(return_value=("sha256:abc", MagicMock()))
        adapter = OCIRegistryClientAdapter(inner)
        digest, artifact = await adapter.push_bundle("repo", "tag", "/path", MagicMock())
        assert digest == "sha256:abc"

    async def test_adapter_pull_bundle(self):
        inner = MagicMock()
        manifest = _make_manifest()
        inner.pull_bundle = AsyncMock(return_value=(manifest, "/tmp/out"))
        adapter = OCIRegistryClientAdapter(inner)
        m, p = await adapter.pull_bundle("repo", "tag", "/tmp/dest")
        assert m.version == "1.0.0"

    async def test_adapter_list_tags(self):
        inner = MagicMock()
        inner.list_tags = AsyncMock(return_value=["v1", "v2"])
        adapter = OCIRegistryClientAdapter(inner)
        tags = await adapter.list_tags("repo")
        assert tags == ["v1", "v2"]

    async def test_adapter_get_manifest(self):
        inner = MagicMock()
        inner.get_manifest = AsyncMock(return_value=None)
        adapter = OCIRegistryClientAdapter(inner)
        result = await adapter.get_manifest("repo", "ref")
        assert result is None


class TestGlobalDistributionService:
    """Cover initialize/close/get distribution service."""

    async def test_close_with_fallbacks(self):
        import enhanced_agent_bus.bundle_registry as br_mod

        primary = OCIRegistryClient("https://primary.example.com")
        fallback = OCIRegistryClient("https://fallback.example.com")
        primary.close = AsyncMock()
        fallback.close = AsyncMock()

        service = BundleDistributionService(primary, [fallback])
        old_val = br_mod._distribution_service
        br_mod._distribution_service = service
        try:
            await close_distribution_service()
            primary.close.assert_awaited_once()
            fallback.close.assert_awaited_once()
            assert br_mod._distribution_service is None
        finally:
            br_mod._distribution_service = old_val

    async def test_close_when_none(self):
        import enhanced_agent_bus.bundle_registry as br_mod

        old_val = br_mod._distribution_service
        br_mod._distribution_service = None
        try:
            await close_distribution_service()  # Should not raise
        finally:
            br_mod._distribution_service = old_val


class TestBundleManifestFromDictEdgeCases:
    """Cover from_dict with missing optional fields."""

    def test_from_dict_minimal(self):
        data = {"version": "2.0.0", "revision": "e" * 40}
        manifest = BundleManifest.from_dict(data)
        assert manifest.version == "2.0.0"
        assert manifest.roots == []
        assert manifest.signatures == []
        assert manifest.metadata == {}

    def test_from_dict_with_all_fields(self):
        data = {
            "version": "3.0.0",
            "revision": "f" * 40,
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "timestamp": "2025-01-01T00:00:00",
            "roots": ["root1"],
            "signatures": [{"keyid": "k", "sig": "s", "alg": "ed25519"}],
            "metadata": {"author": "test"},
        }
        manifest = BundleManifest.from_dict(data)
        assert manifest.roots == ["root1"]
        assert len(manifest.signatures) == 1


# ============================================================================
# SECTION 2: review_api.py coverage
# ============================================================================


class TestListAmendmentsEndpoint:
    """Cover list_amendments endpoint branches."""

    async def test_list_amendments_success_with_status_filter(self):
        mock_storage = AsyncMock()
        amendment = _make_amendment()
        mock_storage.list_amendments.return_value = ([amendment], 1)

        with _review_api_patch(
            "ConstitutionalStorageService",
            return_value=mock_storage,
        ):
            result = await list_amendments(
                status="proposed",
                proposer_agent_id=None,
                limit=10,
                offset=0,
                order_by="created_at",
                order="asc",
            )
            assert isinstance(result, AmendmentListResponse)
            assert result.total == 1

    async def test_list_amendments_no_filter(self):
        mock_storage = AsyncMock()
        mock_storage.list_amendments.return_value = ([], 0)

        with _review_api_patch(
            "ConstitutionalStorageService",
            return_value=mock_storage,
        ):
            result = await list_amendments(
                status=None,
                proposer_agent_id="agent-1",
                limit=50,
                offset=0,
                order_by="created_at",
                order="desc",
            )
            assert result.total == 0

    async def test_list_amendments_storage_error_500(self):
        mock_storage = AsyncMock()
        mock_storage.connect.side_effect = RuntimeError("DB down")

        with _review_api_patch(
            "ConstitutionalStorageService",
            return_value=mock_storage,
        ):
            with pytest.raises(Exception) as exc_info:
                await list_amendments(
                    status=None,
                    proposer_agent_id=None,
                    limit=50,
                    offset=0,
                    order_by="created_at",
                    order="desc",
                )
            assert exc_info.value.status_code == 500


class TestGetAmendmentEndpoint:
    """Cover get_amendment endpoint branches."""

    async def test_get_amendment_with_dict_proposed_changes(self):
        amendment = _make_amendment(
            proposed_changes={"rules": {"new": "value"}},
            governance_metrics_before={"score": 0.8},
            governance_metrics_after={"score": 0.9},
        )
        version = _make_version()
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = version

        mock_diff_obj = _make_semantic_diff()
        mock_diff_engine = AsyncMock()
        mock_diff_engine.compute_diff_from_content.return_value = mock_diff_obj

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "ConstitutionalDiffEngine",
                return_value=mock_diff_engine,
            ),
        ):
            result = await get_amendment("amend-1", include_diff=True, include_target_version=True)
            assert isinstance(result, AmendmentDetailResponse)
            assert result.governance_metrics_delta["score"] == pytest.approx(0.1)

    async def test_get_amendment_with_string_proposed_changes(self):
        amendment = _make_amendment()
        # Force proposed_changes to string to hit the isinstance(str) branch
        object.__setattr__(amendment, "proposed_changes", "2.0.0")
        version = _make_version()
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = version

        mock_diff_engine = AsyncMock()
        mock_diff_engine.compute_diff.return_value = _make_semantic_diff()

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "ConstitutionalDiffEngine",
                return_value=mock_diff_engine,
            ),
        ):
            result = await get_amendment("amend-1", include_diff=True, include_target_version=True)
            assert result.diff is not None

    async def test_get_amendment_no_diff_no_version(self):
        amendment = _make_amendment()
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment

        with _review_api_patch(
            "ConstitutionalStorageService",
            return_value=mock_storage,
        ):
            result = await get_amendment(
                "amend-1", include_diff=False, include_target_version=False
            )
            assert result.diff is None
            assert result.target_version is None

    async def test_get_amendment_not_found_404(self):
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = None

        with _review_api_patch(
            "ConstitutionalStorageService",
            return_value=mock_storage,
        ):
            with pytest.raises(Exception) as exc_info:
                await get_amendment("nonexistent")
            assert exc_info.value.status_code == 404

    async def test_get_amendment_storage_error_500(self):
        mock_storage = AsyncMock()
        mock_storage.connect.side_effect = RuntimeError("DB error")

        with _review_api_patch(
            "ConstitutionalStorageService",
            return_value=mock_storage,
        ):
            with pytest.raises(Exception) as exc_info:
                await get_amendment("amend-1")
            assert exc_info.value.status_code == 500


class TestApproveAmendmentEndpoint:
    """Cover approve_amendment endpoint branches."""

    async def test_approve_success_fully_approved(self):
        amendment = _make_amendment(
            status=AmendmentStatus.UNDER_REVIEW,
            impact_score=0.3,  # low impact => 1 required approval
        )
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment

        mock_maci = AsyncMock()
        mock_maci.validate_action.return_value = {"allowed": True}

        mock_hitl = MagicMock()
        mock_chain_config = MagicMock()
        mock_chain_config.required_approvals = 1
        mock_hitl._determine_approval_chain.return_value = mock_chain_config

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "ConstitutionalHITLIntegration",
                return_value=mock_hitl,
            ),
        ):
            mock_audit = AsyncMock()
            with (
                _review_api_patch(
                    "AuditClient",
                    return_value=mock_audit,
                ),
                _review_api_patch(
                    "AuditClientConfig",
                ),
            ):
                req = ApprovalRequest(approver_agent_id="judicial-agent")
                result = await approve_amendment("amend-1", req, x_agent_id="judicial-agent")
                assert isinstance(result, ApprovalResponse)
                assert result.success is True
                assert (
                    "fully approved" in result.next_steps[0].lower()
                    or "approved" in result.message.lower()
                )

    async def test_approve_pending_more_approvals(self):
        amendment = _make_amendment(
            status=AmendmentStatus.PROPOSED,
            impact_score=0.9,  # high impact => multiple approvals needed
        )
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment

        mock_maci = AsyncMock()
        mock_maci.validate_action.return_value = {"allowed": True}

        mock_hitl = MagicMock()
        mock_chain_config = MagicMock()
        mock_chain_config.required_approvals = 3
        mock_hitl._determine_approval_chain.return_value = mock_chain_config

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "ConstitutionalHITLIntegration",
                return_value=mock_hitl,
            ),
            _review_api_patch(
                "AuditClient",
                return_value=AsyncMock(),
            ),
            _review_api_patch(
                "AuditClientConfig",
            ),
        ):
            req = ApprovalRequest(approver_agent_id="judicial-agent")
            result = await approve_amendment("amend-1", req, x_agent_id=None)
            assert result.success is True
            assert amendment.status == AmendmentStatus.UNDER_REVIEW

    async def test_approve_maci_denied_403(self):
        mock_maci = AsyncMock()
        mock_maci.validate_action.return_value = {"allowed": False}

        with _review_api_patch(
            "MACIEnforcer",
            return_value=mock_maci,
        ):
            req = ApprovalRequest(approver_agent_id="bad-agent")
            with pytest.raises(Exception) as exc_info:
                await approve_amendment("amend-1", req, x_agent_id="bad-agent")
            assert exc_info.value.status_code == 403

    async def test_approve_not_found_404(self):
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = None

        mock_maci = AsyncMock()
        mock_maci.validate_action.return_value = {"allowed": True}

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "AuditClient",
                return_value=AsyncMock(),
            ),
            _review_api_patch(
                "AuditClientConfig",
            ),
        ):
            req = ApprovalRequest(approver_agent_id="judicial-agent")
            with pytest.raises(Exception) as exc_info:
                await approve_amendment("amend-1", req, x_agent_id="judicial-agent")
            assert exc_info.value.status_code == 404

    async def test_approve_wrong_status_400(self):
        amendment = _make_amendment(status=AmendmentStatus.REJECTED)
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment

        mock_maci = AsyncMock()
        mock_maci.validate_action.return_value = {"allowed": True}

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "AuditClient",
                return_value=AsyncMock(),
            ),
            _review_api_patch(
                "AuditClientConfig",
            ),
            _review_api_patch(
                "ConstitutionalHITLIntegration",
            ),
        ):
            req = ApprovalRequest(approver_agent_id="judicial-agent")
            with pytest.raises(Exception) as exc_info:
                await approve_amendment("amend-1", req, x_agent_id="judicial-agent")
            assert exc_info.value.status_code == 400

    async def test_approve_internal_error_500(self):
        mock_maci = AsyncMock()
        mock_maci.validate_action.return_value = {"allowed": True}

        mock_storage = AsyncMock()
        mock_storage.connect.side_effect = RuntimeError("boom")

        with (
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
        ):
            req = ApprovalRequest(approver_agent_id="judicial-agent")
            with pytest.raises(Exception) as exc_info:
                await approve_amendment("amend-1", req, x_agent_id="judicial-agent")
            assert exc_info.value.status_code == 500


class TestRejectAmendmentEndpoint:
    """Cover reject_amendment endpoint branches."""

    async def test_reject_success(self):
        amendment = _make_amendment(status=AmendmentStatus.UNDER_REVIEW)
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment

        mock_maci = AsyncMock()
        mock_maci.validate_action.return_value = {"allowed": True}

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "AuditClient",
                return_value=AsyncMock(),
            ),
            _review_api_patch(
                "AuditClientConfig",
            ),
        ):
            req = RejectionRequest(
                rejector_agent_id="judicial-agent",
                reason="This amendment does not meet governance quality standards",
            )
            result = await reject_amendment("amend-1", req, x_agent_id="judicial-agent")
            assert isinstance(result, ApprovalResponse)
            assert result.success is True
            assert amendment.status == AmendmentStatus.REJECTED
            assert len(result.next_steps) == 2

    async def test_reject_maci_denied_403(self):
        mock_maci = AsyncMock()
        mock_maci.validate_action.return_value = {"allowed": False}

        with _review_api_patch(
            "MACIEnforcer",
            return_value=mock_maci,
        ):
            req = RejectionRequest(
                rejector_agent_id="bad-agent",
                reason="Some reason that is long enough for validation",
            )
            with pytest.raises(Exception) as exc_info:
                await reject_amendment("amend-1", req, x_agent_id="bad-agent")
            assert exc_info.value.status_code == 403

    async def test_reject_not_found_404(self):
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = None

        mock_maci = AsyncMock()
        mock_maci.validate_action.return_value = {"allowed": True}

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "AuditClient",
                return_value=AsyncMock(),
            ),
            _review_api_patch(
                "AuditClientConfig",
            ),
        ):
            req = RejectionRequest(
                rejector_agent_id="judicial-agent",
                reason="Some reason that is long enough for validation",
            )
            with pytest.raises(Exception) as exc_info:
                await reject_amendment("amend-1", req, x_agent_id="judicial-agent")
            assert exc_info.value.status_code == 404

    async def test_reject_wrong_status_400(self):
        amendment = _make_amendment(status=AmendmentStatus.APPROVED)
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment

        mock_maci = AsyncMock()
        mock_maci.validate_action.return_value = {"allowed": True}

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "AuditClient",
                return_value=AsyncMock(),
            ),
            _review_api_patch(
                "AuditClientConfig",
            ),
        ):
            req = RejectionRequest(
                rejector_agent_id="judicial-agent",
                reason="Some reason that is long enough for validation",
            )
            with pytest.raises(Exception) as exc_info:
                await reject_amendment("amend-1", req, x_agent_id="judicial-agent")
            assert exc_info.value.status_code == 400

    async def test_reject_internal_error_500(self):
        mock_maci = AsyncMock()
        mock_maci.validate_action.return_value = {"allowed": True}

        mock_storage = AsyncMock()
        mock_storage.connect.side_effect = RuntimeError("DB exploded")

        with (
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
        ):
            req = RejectionRequest(
                rejector_agent_id="judicial-agent",
                reason="Some reason that is long enough for validation",
            )
            with pytest.raises(Exception) as exc_info:
                await reject_amendment("amend-1", req, x_agent_id="judicial-agent")
            assert exc_info.value.status_code == 500

    async def test_reject_uses_header_agent_id(self):
        """When x_agent_id is provided, it takes precedence."""
        amendment = _make_amendment(status=AmendmentStatus.PROPOSED)
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment

        mock_maci = AsyncMock()
        mock_maci.validate_action.return_value = {"allowed": True}

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "AuditClient",
                return_value=AsyncMock(),
            ),
            _review_api_patch(
                "AuditClientConfig",
            ),
        ):
            req = RejectionRequest(
                rejector_agent_id="body-agent",
                reason="Reason from body agent is long enough for validation",
            )
            result = await reject_amendment("amend-1", req, x_agent_id="header-agent")
            assert result.success is True
            # MACI was called with header agent
            mock_maci.validate_action.assert_awaited_once()
            call_kwargs = mock_maci.validate_action.call_args
            assert (
                call_kwargs.kwargs.get("agent_id") == "header-agent"
                or call_kwargs[1].get("agent_id") == "header-agent"
            )


class TestRollbackEndpoint:
    """Cover rollback_to_version endpoint."""

    async def test_rollback_not_available_501(self):
        with _review_api_patch("ROLLBACK_AVAILABLE", False):
            req = RollbackRequest(
                requester_agent_id="judicial-agent",
                justification="Critical governance degradation detected requiring immediate rollback action",
            )
            with pytest.raises(Exception) as exc_info:
                await rollback_to_version("v-1", req, x_agent_id="judicial-agent")
            assert exc_info.value.status_code == 501

    async def test_rollback_maci_denied_403(self):
        mock_maci = AsyncMock()
        mock_maci.validate_action.return_value = {"allowed": False}

        with _review_api_patch(
            "MACIEnforcer",
            return_value=mock_maci,
        ):
            req = RollbackRequest(
                requester_agent_id="bad-agent",
                justification="Critical governance degradation detected requiring immediate rollback action",
            )
            with pytest.raises(Exception) as exc_info:
                await rollback_to_version("v-1", req, x_agent_id="bad-agent")
            assert exc_info.value.status_code == 403

    async def test_rollback_target_not_found_404(self):
        mock_maci = AsyncMock()
        mock_maci.validate_action.return_value = {"allowed": True}

        mock_storage = AsyncMock()
        mock_storage.get_version.return_value = None

        with (
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "AuditClient",
                return_value=AsyncMock(),
            ),
            _review_api_patch(
                "AuditClientConfig",
            ),
        ):
            req = RollbackRequest(
                requester_agent_id="judicial-agent",
                justification="Critical governance degradation detected requiring immediate rollback action",
            )
            with pytest.raises(Exception) as exc_info:
                await rollback_to_version("v-nonexistent", req, x_agent_id="judicial-agent")
            assert exc_info.value.status_code == 404

    async def test_rollback_no_active_version_500(self):
        mock_maci = AsyncMock()
        mock_maci.validate_action.return_value = {"allowed": True}

        target_version = _make_version(version="1.0.0", version_id="v-target")
        mock_storage = AsyncMock()
        mock_storage.get_version.return_value = target_version
        mock_storage.get_active_version.return_value = None

        with (
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "AuditClient",
                return_value=AsyncMock(),
            ),
            _review_api_patch(
                "AuditClientConfig",
            ),
        ):
            req = RollbackRequest(
                requester_agent_id="judicial-agent",
                justification="Critical governance degradation detected requiring immediate rollback action",
            )
            with pytest.raises(Exception) as exc_info:
                await rollback_to_version("v-target", req, x_agent_id="judicial-agent")
            assert exc_info.value.status_code == 500

    async def test_rollback_same_version_400(self):
        mock_maci = AsyncMock()
        mock_maci.validate_action.return_value = {"allowed": True}

        version = _make_version(version="1.0.0", version_id="v-same")
        mock_storage = AsyncMock()
        mock_storage.get_version.return_value = version
        mock_storage.get_active_version.return_value = version

        with (
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "AuditClient",
                return_value=AsyncMock(),
            ),
            _review_api_patch(
                "AuditClientConfig",
            ),
        ):
            req = RollbackRequest(
                requester_agent_id="judicial-agent",
                justification="Critical governance degradation detected requiring immediate rollback action",
            )
            with pytest.raises(Exception) as exc_info:
                await rollback_to_version("v-same", req, x_agent_id="judicial-agent")
            assert exc_info.value.status_code == 400

    async def test_rollback_success(self):
        mock_maci = AsyncMock()
        mock_maci.validate_action.return_value = {"allowed": True}

        target = _make_version(version="1.0.0", version_id="v-target")
        current = _make_version(version="2.0.0", version_id="v-current", predecessor="v-old")

        mock_storage = AsyncMock()
        mock_storage.get_version.return_value = target
        mock_storage.get_active_version.return_value = current

        mock_diff_engine = AsyncMock()
        mock_diff_engine.compute_diff.return_value = _make_semantic_diff()

        mock_metrics = AsyncMock()
        mock_degradation = MagicMock()

        mock_saga_result = MagicMock()
        mock_saga_result.status.value = "completed"

        with (
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "ConstitutionalDiffEngine",
                return_value=mock_diff_engine,
            ),
            _review_api_patch(
                "GovernanceMetricsCollector",
                return_value=mock_metrics,
            ),
            _review_api_patch(
                "DegradationDetector",
                return_value=mock_degradation,
            ),
            _review_api_patch(
                "rollback_amendment",
                new_callable=AsyncMock,
                return_value=mock_saga_result,
            ),
            _review_api_patch(
                "AuditClient",
                return_value=AsyncMock(),
            ),
            _review_api_patch(
                "AuditClientConfig",
            ),
        ):
            req = RollbackRequest(
                requester_agent_id="judicial-agent",
                justification="Critical governance degradation detected requiring immediate rollback action",
            )
            result = await rollback_to_version("v-target", req, x_agent_id="judicial-agent")
            assert isinstance(result, RollbackResponse)
            assert result.success is True
            assert result.previous_version == "2.0.0"
            assert result.restored_version == "1.0.0"

    async def test_rollback_saga_failure(self):
        mock_maci = AsyncMock()
        mock_maci.validate_action.return_value = {"allowed": True}

        target = _make_version(version="1.0.0", version_id="v-target")
        current = _make_version(version="2.0.0", version_id="v-current", predecessor="v-old")

        mock_storage = AsyncMock()
        mock_storage.get_version.return_value = target
        mock_storage.get_active_version.return_value = current

        mock_diff_engine = AsyncMock()
        mock_diff_engine.compute_diff.return_value = None

        mock_metrics = AsyncMock()
        mock_degradation = MagicMock()

        mock_saga_result = MagicMock()
        mock_saga_result.status.value = "failed"
        mock_saga_result.errors = ["Saga step failed"]

        with (
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "ConstitutionalDiffEngine",
                return_value=mock_diff_engine,
            ),
            _review_api_patch(
                "GovernanceMetricsCollector",
                return_value=mock_metrics,
            ),
            _review_api_patch(
                "DegradationDetector",
                return_value=mock_degradation,
            ),
            _review_api_patch(
                "rollback_amendment",
                new_callable=AsyncMock,
                return_value=mock_saga_result,
            ),
            _review_api_patch(
                "AuditClient",
                return_value=AsyncMock(),
            ),
            _review_api_patch(
                "AuditClientConfig",
            ),
        ):
            req = RollbackRequest(
                requester_agent_id="judicial-agent",
                justification="Critical governance degradation detected requiring immediate rollback action",
            )
            with pytest.raises(Exception) as exc_info:
                await rollback_to_version("v-target", req, x_agent_id="judicial-agent")
            assert exc_info.value.status_code == 500

    async def test_rollback_internal_error_500(self):
        mock_maci = AsyncMock()
        mock_maci.validate_action.return_value = {"allowed": True}

        mock_storage = AsyncMock()
        mock_storage.connect.side_effect = RuntimeError("connection failed")

        with (
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "AuditClient",
                return_value=AsyncMock(),
            ),
            _review_api_patch(
                "AuditClientConfig",
            ),
        ):
            req = RollbackRequest(
                requester_agent_id="judicial-agent",
                justification="Critical governance degradation detected requiring immediate rollback action",
            )
            with pytest.raises(Exception) as exc_info:
                await rollback_to_version("v-target", req, x_agent_id="judicial-agent")
            assert exc_info.value.status_code == 500


class TestHealthCheckEndpoint:
    """Cover health_check endpoint."""

    async def test_health_check_returns_healthy(self):
        result = await health_check()
        assert result["status"] == "healthy"
        assert result["service"] == "constitutional-review-api"
        assert "timestamp" in result


class TestReviewApiResponseModels:
    """Cover response model construction for remaining branches."""

    def test_amendment_list_response_defaults(self):
        resp = AmendmentListResponse(amendments=[], total=0, limit=50, offset=0)
        assert resp.constitutional_hash == CONSTITUTIONAL_HASH
        assert resp.timestamp is not None

    def test_amendment_detail_response_defaults(self):
        amendment = _make_amendment()
        resp = AmendmentDetailResponse(amendment=amendment)
        assert resp.diff is None
        assert resp.governance_metrics_delta == {}

    def test_approval_response_defaults(self):
        amendment = _make_amendment()
        resp = ApprovalResponse(success=True, amendment=amendment, message="done")
        assert resp.next_steps == []
        assert resp.constitutional_hash == CONSTITUTIONAL_HASH

    def test_rollback_response_full(self):
        resp = RollbackResponse(
            success=True,
            rollback_id="rb-123",
            previous_version="2.0.0",
            restored_version="1.0.0",
            message="Rolled back successfully",
            justification="Degradation detected in compliance metrics",
            degradation_detected=True,
        )
        assert resp.degradation_detected is True
        assert resp.diff is None
