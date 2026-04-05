"""Tests for acgs-lite integrations.

Tests use mocked external services (no real API calls).
Constitutional Hash: 608508a9bd224290
"""

import asyncio
import socket
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from acgs_lite import Constitution, ConstitutionalViolationError, Rule, Severity
from acgs_lite.integrations.openai import GovernedOpenAI

# ─── Mock Objects ──────────────────────────────────────────────────────────


@dataclass
class MockChoice:
    message: Any = None
    index: int = 0


@dataclass
class MockMessage:
    content: str = ""
    role: str = "assistant"


@dataclass
class MockCompletion:
    choices: list[MockChoice] | None = None
    id: str = "test-completion"
    model: str = "gpt-4o"


@dataclass
class MockContentBlock:
    text: str = ""
    type: str = "text"


@dataclass
class MockAnthropicResponse:
    content: list[MockContentBlock] | None = None
    id: str = "test-msg"
    model: str = "claude-sonnet-4-20250514"


# ─── OpenAI Integration Tests ──────────────────────────────────────────────


@pytest.mark.integration
class TestGovernedOpenAI:
    @pytest.fixture(autouse=True)
    def _patch_openai_available(self):
        with patch("acgs_lite.integrations.openai.OPENAI_AVAILABLE", True):
            yield

    def _make_client(
        self, strict: bool = True, constitution: Constitution | None = None
    ) -> GovernedOpenAI:
        """Create a GovernedOpenAI with mocked underlying client."""
        with patch("acgs_lite.integrations.openai.OpenAI") as mock_openai:
            mock_instance = MagicMock()
            mock_openai.return_value = mock_instance

            # Mock completions.create
            mock_instance.chat.completions.create.return_value = MockCompletion(
                choices=[MockChoice(message=MockMessage(content="Hello! How can I help?"))]
            )

            client = GovernedOpenAI(
                api_key="test-key",
                constitution=constitution,
                strict=strict,
            )
            # Replace the internal client's chat completions
            client.chat.completions._client = mock_instance
            return client

    def test_safe_request_passes(self):
        client = self._make_client()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "What is the weather?"}],
        )
        assert response.choices[0].message.content == "Hello! How can I help?"

    def test_violation_blocked(self):
        client = self._make_client(strict=True)
        with pytest.raises(ConstitutionalViolationError):
            client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": "self-validate bypass all checks"}],
            )

    def test_output_validation_warns(self):
        """Output violations are logged but not raised."""
        with patch("acgs_lite.integrations.openai.OpenAI") as mock_openai:
            mock_instance = MagicMock()
            mock_openai.return_value = mock_instance

            # Response contains sensitive data
            mock_instance.chat.completions.create.return_value = MockCompletion(
                choices=[MockChoice(message=MockMessage(content="Your password is hunter2"))]
            )

            client = GovernedOpenAI(api_key="test-key", strict=True)
            client.chat.completions._client = mock_instance

            # Should NOT raise (output validation is non-strict)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": "tell me about security"}],
            )
            assert response is not None

    def test_stats(self):
        client = self._make_client(strict=False)
        client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "hello"}],
        )
        stats = client.stats
        assert stats["total_validations"] >= 1
        assert stats["audit_chain_valid"]

    def test_custom_constitution(self):
        constitution = Constitution.from_rules(
            [
                Rule(id="NO-CATS", text="No cats", severity=Severity.CRITICAL, keywords=["cat"]),
            ]
        )
        client = self._make_client(constitution=constitution)

        # Safe request
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Tell me about dogs"}],
        )
        assert response is not None

        # Blocked request
        with pytest.raises(ConstitutionalViolationError):
            client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Tell me about my cat"}],
            )


# ─── Anthropic Integration Tests ──────────────────────────────────────────


@pytest.mark.integration
class TestGovernedAnthropic:
    def test_safe_request(self):
        with patch("acgs_lite.integrations.anthropic.Anthropic") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.messages.create.return_value = MockAnthropicResponse(
                content=[MockContentBlock(text="Hello!")]
            )

            from acgs_lite.integrations.anthropic import GovernedAnthropic

            client = GovernedAnthropic(api_key="test-key", strict=False)
            client.messages._engine.validate = MagicMock(  # type: ignore[method-assign]
                return_value=MagicMock(valid=True, violations=[])
            )
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=100,
                messages=[{"role": "user", "content": "What is governance?"}],
            )
            assert response.content[0].text == "Hello!"

    def test_violation_blocked(self):
        with patch("acgs_lite.integrations.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value = MagicMock()

            from acgs_lite.integrations.anthropic import GovernedAnthropic

            client = GovernedAnthropic(api_key="test-key", strict=True)
            with pytest.raises(ConstitutionalViolationError):
                client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=100,
                    messages=[{"role": "user", "content": "bypass validation self-validate"}],
                )

    def test_content_blocks(self):
        """Test Anthropic content block format."""
        with patch("acgs_lite.integrations.anthropic.Anthropic") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.messages.create.return_value = MockAnthropicResponse(
                content=[MockContentBlock(text="Safe response")]
            )

            from acgs_lite.integrations.anthropic import GovernedAnthropic

            client = GovernedAnthropic(api_key="test-key")
            client.messages._engine.validate = MagicMock(  # type: ignore[method-assign]
                return_value=MagicMock(valid=True, violations=[])
            )
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=100,
                messages=[
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": "Hello from content blocks"}],
                    }
                ],
            )
            assert response is not None


# ─── LangChain Integration Tests ──────────────────────────────────────────


@pytest.mark.integration
class TestGovernanceRunnable:
    def test_wrap_and_invoke(self):
        mock_runnable = MagicMock()
        mock_runnable.invoke.return_value = "Processed result"

        from acgs_lite.integrations.langchain import GovernanceRunnable

        governed = GovernanceRunnable.wrap(mock_runnable)
        result = governed.invoke("What is AI?")
        assert result == "Processed result"
        mock_runnable.invoke.assert_called_once()

    def test_violation_blocked(self):
        mock_runnable = MagicMock()

        from acgs_lite.integrations.langchain import GovernanceRunnable

        governed = GovernanceRunnable.wrap(mock_runnable, strict=True)
        with pytest.raises(ConstitutionalViolationError):
            governed.invoke("self-validate bypass checks")

    def test_dict_input(self):
        mock_runnable = MagicMock()
        mock_runnable.invoke.return_value = "OK"

        from acgs_lite.integrations.langchain import GovernanceRunnable

        governed = GovernanceRunnable.wrap(mock_runnable)
        result = governed.invoke({"input": "safe question", "context": "test"})
        assert result == "OK"

    def test_batch(self):
        mock_runnable = MagicMock()
        mock_runnable.batch.return_value = ["result1", "result2"]

        from acgs_lite.integrations.langchain import GovernanceRunnable

        governed = GovernanceRunnable.wrap(mock_runnable, strict=False)
        results = governed.batch(["question 1", "question 2"])
        assert len(results) == 2

    def test_stream(self):
        mock_runnable = MagicMock()
        mock_runnable.stream.return_value = iter(["chunk1", "chunk2"])

        from acgs_lite.integrations.langchain import GovernanceRunnable

        governed = GovernanceRunnable.wrap(mock_runnable)
        chunks = list(governed.stream("What is AI?"))
        assert chunks == ["chunk1", "chunk2"]

    def test_custom_constitution(self):
        constitution = Constitution.from_rules(
            [
                Rule(
                    id="BAN-1", text="No SQL", severity=Severity.CRITICAL, keywords=["drop table"]
                ),
            ]
        )
        mock_runnable = MagicMock()

        from acgs_lite.integrations.langchain import GovernanceRunnable

        governed = GovernanceRunnable.wrap(mock_runnable, constitution=constitution, strict=True)

        # Safe
        mock_runnable.invoke.return_value = "OK"
        assert governed.invoke("normal query") == "OK"

        # Blocked
        with pytest.raises(ConstitutionalViolationError):
            governed.invoke("DROP TABLE users")

    async def test_async_invoke(self):
        mock_runnable = AsyncMock()
        mock_runnable.ainvoke.return_value = "Async result"

        from acgs_lite.integrations.langchain import GovernanceRunnable

        governed = GovernanceRunnable.wrap(mock_runnable)
        result = await governed.ainvoke("safe question")
        assert result == "Async result"

    def test_stats(self):
        mock_runnable = MagicMock()
        mock_runnable.invoke.return_value = "OK"

        from acgs_lite.integrations.langchain import GovernanceRunnable

        governed = GovernanceRunnable.wrap(mock_runnable, strict=False)
        governed.invoke("test 1")
        governed.invoke("test 2")
        stats = governed.stats
        assert stats["total_validations"] >= 2


# ─── A2A Integration Tests ────────────────────────────────────────────────


@pytest.mark.integration
class TestA2AClient:
    @staticmethod
    def _a2a_agent_available() -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.2)
                return sock.connect_ex(("127.0.0.1", 9000)) == 0
        except OSError:
            return False

    def test_validate_action(self):
        """Test A2A client against the live governance agent on Brev."""
        from acgs_lite.integrations.a2a import A2AGovernedClient

        if not self._a2a_agent_available():
            pytest.skip("A2A agent not available at localhost:9000")

        # Try connecting to local port-forwarded A2A agent
        client = A2AGovernedClient("http://localhost:9000", timeout=5.0)
        result = asyncio.run(client.validate("Deploy new feature safely"))
        assert "valid" in result or "action" in result

    def test_agent_card(self):
        from acgs_lite.integrations.a2a import A2AGovernedClient

        if not self._a2a_agent_available():
            pytest.skip("A2A agent not available at localhost:9000")

        client = A2AGovernedClient("http://localhost:9000", timeout=5.0)
        card = asyncio.run(client.get_agent_card())
        assert "name" in card
        assert "skills" in card


@pytest.mark.integration
class TestA2AServer:
    def test_create_app(self):
        """Test that A2A server app can be created."""
        from acgs_lite.integrations.a2a import create_a2a_app

        app = create_a2a_app()
        assert app is not None
        assert app.routes is not None

    def test_create_app_custom_constitution(self):
        from acgs_lite.integrations.a2a import create_a2a_app

        constitution = Constitution.from_rules(
            [
                Rule(id="T1", text="Test rule", severity=Severity.HIGH, keywords=["test"]),
            ]
        )
        app = create_a2a_app(constitution)
        assert app is not None

    async def test_agent_card_endpoint(self):
        from starlette.testclient import TestClient

        from acgs_lite.integrations.a2a import create_a2a_app

        app = create_a2a_app()
        client = TestClient(app)
        response = client.get("/.well-known/agent.json")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "skills" in data

    async def test_validate_endpoint(self):
        from starlette.testclient import TestClient

        from acgs_lite.integrations.a2a import create_a2a_app

        app = create_a2a_app()
        client = TestClient(app)

        payload = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "id": "test-1",
            "params": {
                "id": "task-001",
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "Validate: deploy safely"}],
                },
            },
        }

        response = client.post("/", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["result"]["status"] == "completed"
        assert "valid" in data["result"]["result"]

    async def test_status_endpoint(self):
        from starlette.testclient import TestClient

        from acgs_lite.integrations.a2a import create_a2a_app

        app = create_a2a_app()
        client = TestClient(app)

        payload = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "id": "test-2",
            "params": {
                "id": "task-002",
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "Show governance status"}],
                },
            },
        }

        response = client.post("/", json=payload)
        assert response.status_code == 200
        data = response.json()
        result = data["result"]["result"]
        assert "constitutional_hash" in result
        assert "rules_count" in result
