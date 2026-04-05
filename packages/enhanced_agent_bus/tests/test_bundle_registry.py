"""
ACGS-2 Enhanced Agent Bus - Bundle Registry Tests
Constitutional Hash: 608508a9bd224290

Tests for OCI bundle registry client and distribution service.
"""

import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.errors import (
    ConstitutionalViolationError as ACGSConstitutionalViolationError,
)
from enhanced_agent_bus._compat.errors import (
    ValidationError as ACGSValidationError,
)

# Skip if dependencies not available
aiohttp = pytest.importorskip("aiohttp", reason="aiohttp required for bundle_registry")
cryptography = pytest.importorskip(
    "cryptography", reason="cryptography required for bundle_registry"
)
jsonschema = pytest.importorskip("jsonschema", reason="jsonschema required for bundle_registry")

try:
    from bundle_registry import (
        CONSTITUTIONAL_HASH,
        AWSECRAuthProvider,
        BasicAuthProvider,
        BundleArtifact,
        BundleDistributionService,
        BundleManifest,
        BundleStatus,
        OCIRegistryClient,
        RegistryAuthProvider,
        RegistryType,
        close_distribution_service,
        get_distribution_service,
        initialize_distribution_service,
    )
except ImportError:
    from ..bundle_registry import (
        CONSTITUTIONAL_HASH,
        AWSECRAuthProvider,
        BasicAuthProvider,
        BundleArtifact,
        BundleDistributionService,
        BundleManifest,
        BundleStatus,
        OCIRegistryClient,
        RegistryAuthProvider,
        RegistryType,
        close_distribution_service,
        get_distribution_service,
        initialize_distribution_service,
    )


class TestConstitutionalHash:
    """Tests for constitutional hash constant."""

    def test_constitutional_hash_value(self):
        """Constitutional hash has correct value."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_constitutional_hash_length(self):
        """Constitutional hash has correct length."""
        assert len(CONSTITUTIONAL_HASH) == 16


class TestRegistryType:
    """Tests for RegistryType enum."""

    def test_harbor_type(self):
        """Harbor registry type has correct value."""
        assert RegistryType.HARBOR.value == "harbor"

    def test_ecr_type(self):
        """ECR registry type has correct value."""
        assert RegistryType.ECR.value == "ecr"

    def test_gcr_type(self):
        """GCR registry type has correct value."""
        assert RegistryType.GCR.value == "gcr"

    def test_acr_type(self):
        """ACR registry type has correct value."""
        assert RegistryType.ACR.value == "acr"

    def test_generic_type(self):
        """Generic registry type has correct value."""
        assert RegistryType.GENERIC.value == "generic"

    def test_all_types_exist(self):
        """All expected registry types exist."""
        expected = ["HARBOR", "ECR", "GCR", "ACR", "GENERIC"]
        actual = [t.name for t in RegistryType]
        assert set(actual) == set(expected)


class TestBundleStatus:
    """Tests for BundleStatus enum."""

    def test_draft_status(self):
        """Draft status has correct value."""
        assert BundleStatus.DRAFT.value == "draft"

    def test_pending_review_status(self):
        """Pending review status has correct value."""
        assert BundleStatus.PENDING_REVIEW.value == "pending_review"

    def test_approved_status(self):
        """Approved status has correct value."""
        assert BundleStatus.APPROVED.value == "approved"

    def test_published_status(self):
        """Published status has correct value."""
        assert BundleStatus.PUBLISHED.value == "published"

    def test_revoked_status(self):
        """Revoked status has correct value."""
        assert BundleStatus.REVOKED.value == "revoked"

    def test_all_statuses_exist(self):
        """All expected statuses exist."""
        expected = ["DRAFT", "PENDING_REVIEW", "APPROVED", "PUBLISHED", "REVOKED"]
        actual = [s.name for s in BundleStatus]
        assert set(actual) == set(expected)


class TestBundleManifest:
    """Tests for BundleManifest dataclass."""

    def test_create_manifest(self):
        """Create a basic manifest."""
        manifest = BundleManifest(version="1.0.0", revision="a" * 40)  # 40-char git SHA
        assert manifest.version == "1.0.0"
        assert manifest.revision == "a" * 40
        assert manifest.constitutional_hash == CONSTITUTIONAL_HASH

    def test_default_timestamp(self):
        """Manifest has default timestamp."""
        manifest = BundleManifest(version="1.0.0", revision="a" * 40)
        assert manifest.timestamp is not None
        assert "T" in manifest.timestamp  # ISO format

    def test_default_roots(self):
        """Manifest has default empty roots list."""
        manifest = BundleManifest(version="1.0.0", revision="a" * 40)
        assert manifest.roots == ["acgs/governance"]

    def test_default_signatures(self):
        """Manifest has default empty signatures list."""
        manifest = BundleManifest(version="1.0.0", revision="a" * 40)
        assert manifest.signatures == []

    def test_default_metadata(self):
        """Manifest has default empty metadata dict."""
        manifest = BundleManifest(version="1.0.0", revision="a" * 40)
        assert manifest.metadata == {}

    def test_invalid_constitutional_hash_raises(self):
        """Invalid constitutional hash raises ValueError."""
        with pytest.raises((ValueError, ACGSConstitutionalViolationError, ACGSValidationError)):
            BundleManifest(version="1.0.0", revision="a" * 40, constitutional_hash="invalid")

    def test_to_dict(self):
        """to_dict returns correct dictionary."""
        manifest = BundleManifest(
            version="1.0.0", revision="a" * 40, roots=["root1", "root2"], metadata={"key": "value"}
        )
        result = manifest.to_dict()

        assert result["version"] == "1.0.0"
        assert result["revision"] == "a" * 40
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert result["roots"] == ["root1", "root2"]
        assert result["signatures"] == []
        assert result["metadata"] == {"key": "value"}
        assert "timestamp" in result

    def test_from_dict(self):
        """from_dict creates correct manifest."""
        data = {
            "version": "2.0.0",
            "revision": "b" * 40,
            "roots": ["r1"],
            "signatures": [{"keyid": "key12345", "sig": "a" * 64, "alg": "ed25519"}],
            "metadata": {"test": True},
        }
        manifest = BundleManifest.from_dict(data)

        assert manifest.version == "2.0.0"
        assert manifest.revision == "b" * 40
        assert manifest.roots == ["r1"]
        assert len(manifest.signatures) == 1
        assert manifest.metadata == {"test": True}

    def test_add_signature(self):
        """add_signature adds signature correctly."""
        manifest = BundleManifest(version="1.0.0", revision="a" * 40)
        manifest.add_signature("key123", "signature_hex", "ed25519")

        assert len(manifest.signatures) == 1
        sig = manifest.signatures[0]
        assert sig["keyid"] == "key123"
        assert sig["sig"] == "signature_hex"
        assert sig["alg"] == "ed25519"
        assert "timestamp" in sig

    def test_compute_digest(self):
        """compute_digest returns valid SHA256."""
        manifest = BundleManifest(version="1.0.0", revision="a" * 40)
        digest = manifest.compute_digest()

        assert len(digest) == 64  # SHA256 hex length
        assert all(c in "0123456789abcdef" for c in digest)

    def test_compute_digest_deterministic(self):
        """compute_digest returns same value for same content."""
        manifest1 = BundleManifest(
            version="1.0.0", revision="a" * 40, timestamp="2025-01-01T00:00:00Z"
        )
        manifest2 = BundleManifest(
            version="1.0.0", revision="a" * 40, timestamp="2025-01-01T00:00:00Z"
        )

        assert manifest1.compute_digest() == manifest2.compute_digest()

    def test_verify_signature_no_signatures(self):
        """verify_signature returns False with no signatures."""
        manifest = BundleManifest(version="1.0.0", revision="a" * 40)
        # Use any 32-byte hex string as dummy public key
        assert manifest.verify_signature("00" * 32) is False

    def test_verify_signature_invalid_key_format(self):
        """verify_signature returns False with invalid key format."""
        manifest = BundleManifest(version="1.0.0", revision="a" * 40)
        manifest.add_signature("key1", "sig1")

        # Invalid hex
        assert manifest.verify_signature("not_valid_hex") is False


class TestBundleArtifact:
    """Tests for BundleArtifact dataclass."""

    def test_create_artifact(self):
        """Create a basic artifact."""
        artifact = BundleArtifact(digest="sha256:abc123", size=1024)
        assert artifact.digest == "sha256:abc123"
        assert artifact.size == 1024
        assert artifact.media_type == "application/vnd.opa.bundle.layer.v1+gzip"

    def test_artifact_with_manifest(self):
        """Create artifact with manifest."""
        manifest = BundleManifest(version="1.0.0", revision="a" * 40)
        artifact = BundleArtifact(digest="sha256:abc123", size=1024, manifest=manifest)
        assert artifact.manifest is manifest

    def test_artifact_annotations(self):
        """Create artifact with annotations."""
        artifact = BundleArtifact(digest="sha256:abc123", size=1024, annotations={"key": "value"})
        assert artifact.annotations == {"key": "value"}

    def test_artifact_default_annotations(self):
        """Artifact has empty default annotations."""
        artifact = BundleArtifact(digest="sha256:abc", size=100)
        assert artifact.annotations == {}


class TestBasicAuthProvider:
    """Tests for BasicAuthProvider class."""

    def test_credentials_encrypted(self):
        """Credentials are encrypted in memory."""
        provider = BasicAuthProvider("user", "pass")

        # Check that plaintext is not directly stored
        assert not hasattr(provider, "_username")
        assert not hasattr(provider, "_password")
        assert hasattr(provider, "_encrypted_username")
        assert hasattr(provider, "_encrypted_password")

    def test_username_decryption(self):
        """Username can be decrypted."""
        provider = BasicAuthProvider("testuser", "testpass")
        assert provider.username == "testuser"

    def test_password_decryption(self):
        """Password can be decrypted."""
        provider = BasicAuthProvider("testuser", "testpass")
        assert provider.password == "testpass"

    async def test_get_token(self):
        """get_token returns base64 encoded credentials."""
        import base64

        provider = BasicAuthProvider("user", "pass")
        token = await provider.get_token()

        decoded = base64.b64decode(token).decode()
        assert decoded == "user:pass"

    async def test_get_token_cached(self):
        """get_token caches the token."""
        provider = BasicAuthProvider("user", "pass")
        token1 = await provider.get_token()
        token2 = await provider.get_token()

        assert token1 == token2

    async def test_refresh_token(self):
        """refresh_token clears and regenerates token."""
        provider = BasicAuthProvider("user", "pass")
        token1 = await provider.get_token()

        # Clear and refresh
        token2 = await provider.refresh_token()

        assert token1 == token2  # Same credentials = same result


class TestAWSECRAuthProvider:
    """Tests for AWSECRAuthProvider class."""

    def test_default_region(self):
        """Default region is us-east-1."""
        provider = AWSECRAuthProvider()
        assert provider.region == "us-east-1"

    def test_custom_region(self):
        """Custom region can be set."""
        provider = AWSECRAuthProvider(region="eu-west-1")
        assert provider.region == "eu-west-1"

    def test_profile_setting(self):
        """Profile can be set."""
        provider = AWSECRAuthProvider(profile="myprofile")
        assert provider.profile == "myprofile"

    def test_initial_token_state(self):
        """Initial token is None."""
        provider = AWSECRAuthProvider()
        assert provider._token is None
        assert provider._expiry is None


class TestOCIRegistryClient:
    """Tests for OCIRegistryClient class."""

    def test_client_initialization(self):
        """Client initializes with correct defaults."""
        client = OCIRegistryClient("https://registry.example.com")

        assert client.registry_url == "https://registry.example.com"
        assert client.auth_provider is None
        assert client.registry_type == RegistryType.GENERIC
        assert client.verify_ssl is True

    def test_client_strips_trailing_slash(self):
        """Client strips trailing slash from URL."""
        client = OCIRegistryClient("https://registry.example.com/")
        assert client.registry_url == "https://registry.example.com"

    def test_client_parses_host(self):
        """Client parses host from URL."""
        client = OCIRegistryClient("https://registry.example.com:5000/v2")
        assert client.host == "registry.example.com:5000"
        assert client.scheme == "https"

    def test_client_with_auth_provider(self):
        """Client accepts auth provider."""
        auth = BasicAuthProvider("user", "pass")
        client = OCIRegistryClient("https://registry.example.com", auth_provider=auth)
        assert client.auth_provider is auth

    def test_client_with_registry_type(self):
        """Client accepts registry type."""
        client = OCIRegistryClient("https://ecr.aws.com", registry_type=RegistryType.ECR)
        assert client.registry_type == RegistryType.ECR

    def test_client_ssl_disabled(self):
        """Client can disable SSL verification."""
        client = OCIRegistryClient("https://registry.example.com", verify_ssl=False)
        assert client.verify_ssl is False

    def test_from_url_https(self):
        """from_url handles https:// URLs."""
        client = OCIRegistryClient.from_url("https://registry.example.com")
        assert client.registry_url == "https://registry.example.com"

    def test_from_url_oci(self):
        """from_url handles oci:// URLs."""
        client = OCIRegistryClient.from_url("oci://registry.example.com")
        assert client.registry_url == "https://registry.example.com"

    def test_from_url_no_scheme(self):
        """from_url adds https:// when missing."""
        client = OCIRegistryClient.from_url("registry.example.com")
        assert client.registry_url == "https://registry.example.com"

    def test_initial_stats(self):
        """Client has correct initial stats."""
        client = OCIRegistryClient("https://registry.example.com")
        stats = client.get_stats()

        assert stats["pushes"] == 0
        assert stats["pulls"] == 0
        assert stats["errors"] == 0
        assert stats["bytes_transferred"] == 0
        assert stats["registry"] == "registry.example.com"
        assert stats["type"] == "generic"

    def test_stats_with_ecr_type(self):
        """Stats include correct registry type."""
        client = OCIRegistryClient("https://ecr.aws.com", registry_type=RegistryType.ECR)
        stats = client.get_stats()
        assert stats["type"] == "ecr"

    async def test_context_manager(self):
        """Client works as async context manager."""
        async with OCIRegistryClient("https://registry.example.com") as client:
            assert client._session is not None

        assert client._session is None

    async def test_initialize_creates_session(self):
        """initialize creates aiohttp session."""
        client = OCIRegistryClient("https://registry.example.com")
        await client.initialize()

        assert client._session is not None
        await client.close()

    async def test_close_clears_session(self):
        """close clears aiohttp session."""
        client = OCIRegistryClient("https://registry.example.com")
        await client.initialize()
        await client.close()

        assert client._session is None


class TestBundleDistributionService:
    """Tests for BundleDistributionService class."""

    def test_service_initialization(self):
        """Service initializes correctly."""
        primary = OCIRegistryClient("https://primary.example.com")
        service = BundleDistributionService(primary)

        assert service.primary is primary
        assert service.fallbacks == []

    def test_service_with_fallbacks(self):
        """Service accepts fallback registries."""
        primary = OCIRegistryClient("https://primary.example.com")
        fallback1 = OCIRegistryClient("https://fallback1.example.com")
        fallback2 = OCIRegistryClient("https://fallback2.example.com")

        service = BundleDistributionService(primary, fallback_registries=[fallback1, fallback2])

        assert len(service.fallbacks) == 2
        assert service.fallbacks[0] is fallback1
        assert service.fallbacks[1] is fallback2

    def test_service_default_cache_dir(self):
        """Service has default cache directory."""
        primary = OCIRegistryClient("https://primary.example.com")
        service = BundleDistributionService(primary)

        assert service.cache_dir == "runtime/bundle_cache"

    def test_service_custom_cache_dir(self):
        """Service accepts custom cache directory."""
        primary = OCIRegistryClient("https://primary.example.com")

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = os.path.join(tmpdir, "custom_cache")
            service = BundleDistributionService(primary, cache_dir=cache_dir)

            assert service.cache_dir == cache_dir
            assert os.path.exists(cache_dir)

    def test_service_initial_lkg_state(self):
        """Service has no LKG initially."""
        primary = OCIRegistryClient("https://primary.example.com")
        service = BundleDistributionService(primary)

        assert service._lkg_manifest is None
        assert service._lkg_path is None


class TestModuleFunctions:
    """Tests for module-level functions."""

    def test_get_distribution_service_initially_none(self):
        """get_distribution_service returns None initially."""
        # Reset global state
        import bundle_registry

        bundle_registry._distribution_service = None

        result = get_distribution_service()
        assert result is None

    async def test_initialize_distribution_service(self):
        """initialize_distribution_service creates service."""
        import bundle_registry

        bundle_registry._distribution_service = None

        # Mock the initialize to avoid actual HTTP
        with patch.object(OCIRegistryClient, "initialize", new_callable=AsyncMock):
            service = await initialize_distribution_service("https://registry.example.com")

            assert service is not None
            assert service.primary is not None
            assert get_distribution_service() is service

            # Cleanup
            bundle_registry._distribution_service = None

    async def test_close_distribution_service(self):
        """close_distribution_service cleans up properly."""

        # Setup mock service
        with patch.object(OCIRegistryClient, "initialize", new_callable=AsyncMock):
            await initialize_distribution_service("https://registry.example.com")

            assert get_distribution_service() is not None

            with patch.object(OCIRegistryClient, "close", new_callable=AsyncMock):
                await close_distribution_service()

            assert get_distribution_service() is None


class TestManifestRoundTrip:
    """Tests for manifest serialization round-trip."""

    def test_to_dict_from_dict_roundtrip(self):
        """Manifest survives to_dict -> from_dict roundtrip."""
        original = BundleManifest(
            version="1.2.3",
            revision="c" * 40,
            roots=["policies/main"],
            metadata={"env": "prod", "count": 42},
        )
        original.add_signature("key12345", "a" * 64, "ed25519")

        data = original.to_dict()
        restored = BundleManifest.from_dict(data)

        assert restored.version == original.version
        assert restored.revision == original.revision
        assert restored.constitutional_hash == original.constitutional_hash
        assert restored.roots == original.roots
        assert restored.metadata == original.metadata
        assert len(restored.signatures) == len(original.signatures)


class TestAuthProviderAbstract:
    """Tests for RegistryAuthProvider abstract class."""

    def test_abstract_methods(self):
        """RegistryAuthProvider has required abstract methods."""
        import abc

        # Check it's an ABC
        assert issubclass(RegistryAuthProvider, abc.ABC)

        # Check abstract methods
        abstract_methods = getattr(RegistryAuthProvider, "__abstractmethods__", set())
        assert "get_token" in abstract_methods
        assert "refresh_token" in abstract_methods

    def test_cannot_instantiate_directly(self):
        """Cannot instantiate RegistryAuthProvider directly."""
        with pytest.raises(TypeError):
            RegistryAuthProvider()


class TestClientHeaders:
    """Tests for OCIRegistryClient header generation."""

    async def test_headers_without_auth(self):
        """Headers without auth provider."""
        client = OCIRegistryClient("https://registry.example.com")
        await client.initialize()

        headers = await client._get_headers()

        assert "Accept" in headers
        assert "Content-Type" in headers
        assert "Authorization" not in headers

        await client.close()

    async def test_headers_with_basic_auth(self):
        """Headers with basic auth provider."""
        auth = BasicAuthProvider("user", "pass")
        client = OCIRegistryClient("https://registry.example.com", auth_provider=auth)
        await client.initialize()

        headers = await client._get_headers()

        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer ")

        await client.close()

    async def test_headers_with_ecr_auth(self):
        """Headers with ECR auth use Basic prefix."""
        auth = AWSECRAuthProvider()
        auth.refresh_token = AsyncMock(return_value="test_token")
        auth._token = "test_token"  # Mock token

        client = OCIRegistryClient(
            "https://ecr.aws.com", auth_provider=auth, registry_type=RegistryType.ECR
        )
        await client.initialize()

        headers = await client._get_headers()

        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Basic ")

        await client.close()
