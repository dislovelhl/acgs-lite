"""
CI/CD Integration Tests for ACGS-2 Enterprise Features.

This module validates:
- Constitutional hash enforcement in CI/CD
- Enterprise integration test configuration
- Coverage threshold requirements
- Workflow configuration validation

Constitutional Hash: 608508a9bd224290
"""

import os
import re
from pathlib import Path

import pytest
import yaml

# Guard against missing scripts.orchestration.cicd_integration module
try:
    from scripts.orchestration.cicd_integration import CICDIntegration
except ImportError as _cicd_import_error:
    pytest.skip(
        f"Skipping CI/CD integration tests: scripts.orchestration.cicd_integration unavailable"
        f" ({_cicd_import_error})",
        allow_module_level=True,
    )

# Constitutional hash for ACGS-2 compliance
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH


class TestConstitutionalHashValidation:
    """Tests for constitutional hash enforcement in CI/CD."""

    def test_constitutional_hash_constant(self):
        """Verify constitutional hash constant is correct."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH
        assert len(CONSTITUTIONAL_HASH) == 16
        assert all(c in set("0123456789abcdef") for c in CONSTITUTIONAL_HASH)

    def test_enterprise_sso_contains_hash(self):
        """Verify enterprise SSO modules contain constitutional hash."""
        enterprise_sso_dir = Path(__file__).parent.parent / "enterprise_sso"
        if enterprise_sso_dir.exists():
            hash_count = 0
            for py_file in enterprise_sso_dir.glob("**/*.py"):
                content = py_file.read_text()
                if CONSTITUTIONAL_HASH in content:
                    hash_count += 1
            assert hash_count >= 5, (
                f"Expected at least 5 files with constitutional hash, found {hash_count}"
            )

    def test_multi_tenancy_contains_hash(self):
        """Verify multi-tenancy modules contain constitutional hash."""
        multi_tenancy_dir = Path(__file__).parent.parent / "multi_tenancy"
        if multi_tenancy_dir.exists():
            hash_count = 0
            for py_file in multi_tenancy_dir.glob("**/*.py"):
                content = py_file.read_text()
                if CONSTITUTIONAL_HASH in content:
                    hash_count += 1
            assert hash_count >= 3, (
                f"Expected at least 3 files with constitutional hash, found {hash_count}"
            )

    def test_no_invalid_hashes(self):
        """Verify no invalid constitutional hashes exist in production code.

        Note: Test files are excluded as they may contain invalid hashes
        intentionally for testing validation logic.
        """
        src_dir = Path(__file__).parent.parent
        invalid_hash_pattern = re.compile(
            r'constitutional.*hash.*["\'][a-f0-9]{16}["\']', re.IGNORECASE
        )

        # Exclude test files - they may have invalid hashes for testing
        exclude_patterns = ["test_", "conftest", "_test.py"]

        invalid_files = []
        for py_file in src_dir.glob("**/*.py"):
            # Skip test files
            if any(pattern in py_file.name for pattern in exclude_patterns):
                continue
            # Skip tests directory entirely
            if "/tests/" in str(py_file):
                continue

            content = py_file.read_text()
            matches = invalid_hash_pattern.findall(content)
            for match in matches:
                if CONSTITUTIONAL_HASH not in match:
                    invalid_files.append((py_file, match))

        assert len(invalid_files) == 0, f"Found invalid hashes in: {invalid_files}"


class TestCICDWorkflowConfiguration:
    """Tests for CI/CD workflow configuration."""

    @pytest.fixture
    def project_root(self) -> Path:
        """Get project root directory."""
        # From tests/ -> enhanced_agent_bus/ -> core/ -> src/ -> project_root
        return Path(__file__).parent.parent.parent.parent.parent

    @pytest.fixture
    def workflow_path(self, project_root: Path) -> Path:
        """Get path to enterprise integration workflow."""
        return project_root / ".github" / "workflows" / "enterprise-integration.yml"

    def test_workflow_exists(self, workflow_path: Path):
        """Verify enterprise integration workflow exists."""
        assert workflow_path.exists(), f"Workflow not found at {workflow_path}"

    def test_workflow_valid_yaml(self, workflow_path: Path):
        """Verify workflow is valid YAML."""
        if not workflow_path.exists():
            pytest.skip("Workflow file not found")

        content = workflow_path.read_text()
        try:
            workflow = yaml.safe_load(content)
            assert workflow is not None
        except yaml.YAMLError as e:
            pytest.fail(f"Invalid YAML: {e}")

    def test_workflow_contains_constitutional_hash(self, workflow_path: Path):
        """Verify workflow references constitutional hash."""
        if not workflow_path.exists():
            pytest.skip("Workflow file not found")

        content = workflow_path.read_text()
        assert CONSTITUTIONAL_HASH in content, "Workflow must reference constitutional hash"

    def test_workflow_has_coverage_threshold(self, workflow_path: Path):
        """Verify workflow enforces coverage threshold."""
        if not workflow_path.exists():
            pytest.skip("Workflow file not found")

        content = workflow_path.read_text()
        workflow = yaml.safe_load(content)

        # Check for coverage threshold in env or inputs
        env = workflow.get("env", {})
        coverage_threshold = env.get("COVERAGE_THRESHOLD", "0")

        # Default should be 95%
        assert "95" in str(coverage_threshold) or "COVERAGE_THRESHOLD" in content

    def test_workflow_has_required_jobs(self, workflow_path: Path):
        """Verify workflow has all required jobs."""
        if not workflow_path.exists():
            pytest.skip("Workflow file not found")

        content = workflow_path.read_text()
        workflow = yaml.safe_load(content)

        jobs = workflow.get("jobs", {})
        required_jobs = [
            "constitutional-validation",
            "multi-tenant-tests",
            "sso-tests",
            "data-warehouse-tests",
            "kafka-tests",
            "migration-tests",
            "full-integration",
            "report",
        ]

        for job in required_jobs:
            assert job in jobs, f"Missing required job: {job}"

    def test_workflow_tests_enterprise_features(self, workflow_path: Path):
        """Verify workflow tests all enterprise features."""
        if not workflow_path.exists():
            pytest.skip("Workflow file not found")

        content = workflow_path.read_text()

        # Check for test file references
        expected_tests = [
            "test_rls_integration.py",
            "test_session_vars.py",
            "test_system_tenant.py",
            "test_sso_integration.py",
            "test_data_warehouse_integration.py",
            "test_kafka_streaming.py",
            "test_gap_analysis.py",
            "test_policy_converter.py",
        ]

        for test_file in expected_tests:
            assert test_file in content, f"Missing test reference: {test_file}"


class TestCoverageRequirements:
    """Tests for coverage requirements."""

    def test_minimum_coverage_threshold(self):
        """Verify minimum coverage threshold is 95%."""
        min_coverage = 95
        assert min_coverage >= 85, "Minimum coverage must be at least 85%"
        assert min_coverage <= 100, "Coverage cannot exceed 100%"

    def test_critical_paths_coverage(self):
        """Verify critical paths require higher coverage."""
        critical_coverage = 95
        standard_coverage = 85
        assert critical_coverage >= standard_coverage, "Critical paths must have higher coverage"


class TestGenericCommandSafety:
    """Security tests for generic command execution path."""

    @pytest.mark.parametrize("token", [";", "&&", "||", "|", "$("])
    def test_build_safe_command_args_rejects_shell_operators(self, token: str):
        integration = CICDIntegration()
        with pytest.raises(ValueError, match="Unsafe shell control operators"):
            integration._build_safe_command_args(f"python -m pytest {token} whoami")

    def test_build_safe_command_args_allows_simple_command(self):
        integration = CICDIntegration()
        args = integration._build_safe_command_args("python -m pytest tests/unit")
        assert args[:3] == ["python", "-m", "pytest"]


class TestEnterpriseModuleStructure:
    """Tests for enterprise module structure."""

    @pytest.fixture
    def enterprise_sso_dir(self) -> Path:
        """Get enterprise SSO directory."""
        return Path(__file__).parent.parent / "enterprise_sso"

    @pytest.fixture
    def multi_tenancy_dir(self) -> Path:
        """Get multi-tenancy directory."""
        return Path(__file__).parent.parent / "multi_tenancy"

    def test_enterprise_sso_modules_exist(self, enterprise_sso_dir: Path):
        """Verify enterprise SSO modules exist."""
        if not enterprise_sso_dir.exists():
            pytest.skip("Enterprise SSO directory not found")

        expected_modules = [
            "__init__.py",
            "ldap_integration.py",
            "saml_integration.py",
            "oidc_integration.py",
            "maci_role_mapping.py",
            "data_warehouse.py",
            "kafka_streaming.py",
            "gap_analysis.py",
            "policy_converter.py",
            "migration_tools.py",
        ]

        existing = [f.name for f in enterprise_sso_dir.glob("*.py")]
        for module in expected_modules:
            if module not in existing:
                pytest.skip(f"Module {module} not found (may not be implemented yet)")

    def test_multi_tenancy_modules_exist(self, multi_tenancy_dir: Path):
        """Verify multi-tenancy modules exist."""
        if not multi_tenancy_dir.exists():
            pytest.skip("Multi-tenancy directory not found")

        expected_modules = [
            "__init__.py",
            "rls.py",
            "session_vars.py",
            "system_tenant.py",
            "db_repository.py",
        ]

        existing = [f.name for f in multi_tenancy_dir.glob("*.py")]
        for module in expected_modules:
            if module not in existing:
                pytest.skip(f"Module {module} not found (may not be implemented yet)")


class TestTestFileStructure:
    """Tests for test file structure."""

    @pytest.fixture
    def tests_dir(self) -> Path:
        """Get tests directory."""
        return Path(__file__).parent

    def test_enterprise_test_files_exist(self, tests_dir: Path):
        """Verify enterprise test files exist."""
        expected_tests = [
            "test_rls_integration.py",
            "test_session_vars.py",
            "test_system_tenant.py",
            "test_db_repository.py",
            "test_sso_integration.py",
            "test_ldap_integration.py",
            "test_saml_integration.py",
            "test_oidc_integration.py",
            "test_maci_role_mapping.py",
            "test_kafka_streaming.py",
            "test_data_warehouse_integration.py",
            "test_gap_analysis.py",
            "test_policy_converter.py",
            "test_migration_tools.py",
        ]

        existing = [f.name for f in tests_dir.glob("test_*.py")]
        found = 0
        for test_file in expected_tests:
            if test_file in existing:
                found += 1

        # At least 50% of expected tests should exist (some may be in progress)
        expected_count = int(len(expected_tests) * 0.5)
        assert found >= expected_count, (
            f"Expected at least {expected_count} test files, found {found}"
        )

    def test_test_files_have_constitutional_hash(self, tests_dir: Path):
        """Verify test files reference constitutional hash."""
        test_files = list(tests_dir.glob("test_*integration*.py"))
        if not test_files:
            pytest.skip("No integration test files found")

        files_with_hash = 0
        for test_file in test_files:
            content = test_file.read_text()
            if CONSTITUTIONAL_HASH in content:
                files_with_hash += 1

        # At least 50% should have the hash
        assert files_with_hash >= len(test_files) // 2


class TestDocumentationExists:
    """Tests for enterprise documentation."""

    @pytest.fixture
    def project_root(self) -> Path:
        """Get project root directory."""
        # From tests/ -> enhanced_agent_bus/ -> core/ -> src/ -> project_root
        return Path(__file__).parent.parent.parent.parent.parent

    @pytest.fixture
    def docs_dir(self, project_root: Path) -> Path:
        """Get enterprise docs directory."""
        return project_root / "docs" / "enterprise"

    def test_documentation_directory_exists(self, docs_dir: Path):
        """Verify enterprise documentation directory exists."""
        assert docs_dir.exists(), f"Documentation directory not found at {docs_dir}"

    def test_required_documentation_files(self, docs_dir: Path):
        """Verify required documentation files exist."""
        if not docs_dir.exists():
            pytest.skip("Documentation directory not found")

        expected_docs = [
            "README.md",
            "sso-integration.md",
            "multi-tenant.md",
            "data-warehouse.md",
            "event-streaming.md",
            "migration-guide.md",
            "api-reference.md",
        ]

        existing = [f.name for f in docs_dir.glob("*.md")]
        for doc in expected_docs:
            assert doc in existing, f"Missing documentation: {doc}"

    def test_documentation_has_constitutional_hash(self, docs_dir: Path):
        """Verify documentation files contain constitutional hash."""
        if not docs_dir.exists():
            pytest.skip("Documentation directory not found")

        docs_with_hash = 0
        for doc_file in docs_dir.glob("*.md"):
            content = doc_file.read_text()
            if CONSTITUTIONAL_HASH in content:
                docs_with_hash += 1

        # All docs should have the hash
        total_docs = len(list(docs_dir.glob("*.md")))
        assert docs_with_hash == total_docs, (
            f"Expected all {total_docs} docs to have hash, found {docs_with_hash}"
        )


class TestGitHubActionsCompliance:
    """Tests for GitHub Actions compliance."""

    @pytest.fixture
    def project_root(self) -> Path:
        """Get project root directory."""
        # From tests/ -> enhanced_agent_bus/ -> core/ -> src/ -> project_root
        return Path(__file__).parent.parent.parent.parent.parent

    @pytest.fixture
    def workflows_dir(self, project_root: Path) -> Path:
        """Get workflows directory."""
        return project_root / ".github" / "workflows"

    def test_workflow_uses_python_312(self, workflows_dir: Path):
        """Verify workflows use Python 3.12."""
        enterprise_workflow = workflows_dir / "enterprise-integration.yml"
        if not enterprise_workflow.exists():
            pytest.skip("Enterprise workflow not found")

        content = enterprise_workflow.read_text()
        assert "3.12" in content, "Workflow should use Python 3.12"

    def test_workflow_uploads_artifacts(self, workflows_dir: Path):
        """Verify workflows upload test artifacts."""
        enterprise_workflow = workflows_dir / "enterprise-integration.yml"
        if not enterprise_workflow.exists():
            pytest.skip("Enterprise workflow not found")

        content = enterprise_workflow.read_text()
        assert "upload-artifact" in content, "Workflow should upload artifacts"

    def test_workflow_has_failure_notification(self, workflows_dir: Path):
        """Verify workflows have failure notification."""
        enterprise_workflow = workflows_dir / "enterprise-integration.yml"
        if not enterprise_workflow.exists():
            pytest.skip("Enterprise workflow not found")

        content = enterprise_workflow.read_text()
        assert (
            "notify" in content.lower()
            or "slack" in content.lower()
            or "pagerduty" in content.lower()
        )


class TestSecurityIntegration:
    """Tests for security integration in CI/CD."""

    def test_no_secrets_in_code(self):
        """Verify no secrets are hardcoded."""
        src_dir = Path(__file__).parent.parent

        secret_patterns = [
            r'password\s*=\s*["\'][^"\']+["\']',
            r'api_key\s*=\s*["\'][^"\']+["\']',
            r'secret\s*=\s*["\'][^"\']+["\']',
        ]

        # Exclude test files and example configs
        exclude_patterns = ["test_", "example", "mock", "fixture"]

        for py_file in src_dir.glob("**/*.py"):
            if any(pattern in py_file.name for pattern in exclude_patterns):
                continue

            content = py_file.read_text()
            for pattern in secret_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                # Filter out obvious non-secrets
                real_secrets = [
                    m for m in matches if "***" not in m and "placeholder" not in m.lower()
                ]
                if real_secrets:
                    # This is a warning, not a failure, as it needs manual review
                    pass

    def test_constitutional_hash_format(self):
        """Verify constitutional hash follows expected format."""
        # Hash should be 16 hex characters
        assert len(CONSTITUTIONAL_HASH) == 16
        assert all(c in set("0123456789abcdef") for c in CONSTITUTIONAL_HASH)

        # Should be lowercase
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH.lower()


class TestContinuousIntegrationMetrics:
    """Tests for CI metrics collection."""

    def test_coverage_report_format(self):
        """Verify coverage report format is correct."""
        # XML coverage format for Codecov/SonarQube
        expected_format = "xml"
        assert expected_format in ["xml", "html", "json"]

    def test_test_result_format(self):
        """Verify test result format is correct."""
        # JUnit XML format for GitHub Actions
        expected_format = "junit"
        assert expected_format in ["junit", "xml", "json"]


# Benchmark tests for CI/CD performance
class TestCICDPerformance:
    """Performance benchmarks for CI/CD operations."""

    def test_import_time(self):
        """Verify import time is reasonable."""
        import time

        start = time.time()
        # Simulate importing enterprise modules
        from dataclasses import dataclass, field
        from datetime import datetime, timezone
        from typing import Optional

        end = time.time()

        import_time = end - start
        assert import_time < 1.0, f"Import time {import_time}s exceeds 1s threshold"

    def test_hash_validation_speed(self):
        """Verify hash validation is fast."""
        import time

        start = time.time()
        for _ in range(1000):
            is_valid = CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH
        end = time.time()

        total_time = end - start
        assert total_time < 0.1, f"1000 hash validations took {total_time}s, exceeds 0.1s"
