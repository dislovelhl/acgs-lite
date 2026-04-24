"""T-07/T-10 regression: TrajectoryMonitor thread safety + lock release.

- ``check_trajectory()`` is public and must be safe to call concurrently
  with ``check_checkpoint()``.
- The lock must NOT be held during rule evaluation so that an O(N log N)
  rule does not serialise concurrent throughput.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Sequence
from typing import Any

from acgs_lite.trajectory import (
    InMemoryTrajectoryStore,
    TrajectoryMonitor,
    TrajectorySession,
    TrajectoryViolation,
)


class _SlowRule:
    """Rule that sleeps to make any lock-holding regression observable."""

    def __init__(self, sleep_s: float) -> None:
        self.sleep_s = sleep_s
        self.calls = 0
        self.calls_lock = threading.Lock()

    def check(self, decisions: Sequence[dict[str, Any]]) -> TrajectoryViolation | None:
        with self.calls_lock:
            self.calls += 1
        time.sleep(self.sleep_s)
        return None


class TestTrajectoryMonitorThreadSafety:
    def test_check_trajectory_is_thread_safe(self) -> None:
        monitor = TrajectoryMonitor(rules=[], store=InMemoryTrajectoryStore())

        def worker(i: int) -> None:
            session = TrajectorySession(session_id=f"s{i}", agent_id="a")
            for j in range(20):
                session.add({"action_type": "x", "i": i, "j": j})
                monitor.check_trajectory(session)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    def test_rule_eval_runs_concurrently_across_threads(self) -> None:
        """Lock must be released before slow rule eval — otherwise total
        wall time is N * sleep instead of ~sleep when run in parallel."""
        slow = _SlowRule(sleep_s=0.05)
        monitor = TrajectoryMonitor(rules=[slow], store=InMemoryTrajectoryStore())

        def worker(i: int) -> None:
            session = TrajectorySession(session_id=f"s{i}", agent_id="a")
            session.add({"action_type": "x"})
            monitor.check_trajectory(session)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        start = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.perf_counter() - start

        assert slow.calls == 10
        # Serialised would be ~0.5 s; parallel should be well under 0.25 s.
        assert elapsed < 0.25, (
            f"Trajectory rule eval appears serialised under monitor lock: "
            f"{elapsed:.3f}s for 10 concurrent calls (expected <0.25s)"
        )

    def test_check_checkpoint_and_check_trajectory_interleave(self) -> None:
        monitor = TrajectoryMonitor(rules=[], store=InMemoryTrajectoryStore())
        errors: list[BaseException] = []

        def cp_worker() -> None:
            try:
                for i in range(50):
                    monitor.check_checkpoint(
                        session_id="shared",
                        agent_id="a",
                        decision={"action_type": "x", "i": i},
                    )
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        def tj_worker() -> None:
            try:
                session = TrajectorySession(session_id="other", agent_id="a")
                for i in range(50):
                    session.add({"action_type": "y", "i": i})
                    monitor.check_trajectory(session)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=cp_worker) for _ in range(4)] + [
            threading.Thread(target=tj_worker) for _ in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, f"Concurrent calls raised: {errors}"
