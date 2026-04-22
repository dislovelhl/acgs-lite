"""Regression test for security finding SEC-001: unauthenticated WebSocket transport.

Origin
------
- First audited: security-audit-report.md (HIGH finding)
- Remediation claim: SYSTEMIC_IMPROVEMENT.md — "non-local WebSocket transport
  now requires TLS configuration"
- Status as of this test's existence: REMEDIATED (asserted here)

Contract
--------
- A `RemoteVoteClient` constructed with a non-loopback host and no `ssl_context`
  MUST fail loudly (raise) rather than silently proceed on plaintext `ws://`.
- Loopback addresses (127.0.0.1, localhost, ::1) MAY accept plaintext for dev.
- Rotating the security audit into pytest means this finding cannot regress
  without turning a test red.
"""

from __future__ import annotations

import pytest

from constitutional_swarm.remote_vote_transport import RemoteVoteClient

FINDING_ID = "SEC-001"
SEVERITY = "HIGH"
STATUS = "remediated"
TITLE = "Unauthenticated WebSocket transport"


@pytest.mark.security
class TestFindingSEC001:
    def test_non_localhost_without_tls_raises(self) -> None:
        with pytest.raises((ValueError, RuntimeError), match=r"(?i)tls|ssl|secure"):
            RemoteVoteClient(host="peer.example.com", port=8443, ssl_context=None)

    def test_non_localhost_with_tls_succeeds(self) -> None:
        import ssl

        ctx = ssl.create_default_context()
        client = RemoteVoteClient(host="peer.example.com", port=8443, ssl_context=ctx)
        assert client is not None

    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
    def test_loopback_without_tls_succeeds(self, host: str) -> None:
        client = RemoteVoteClient(host=host, port=8443, ssl_context=None)
        assert client is not None
