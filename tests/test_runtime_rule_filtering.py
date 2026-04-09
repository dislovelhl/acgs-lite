from acgs_lite import Constitution, Rule, Severity
from acgs_lite.engine.core import GovernanceEngine


def test_runtime_filter_uses_explicit_timestamp_for_future_rule() -> None:
    engine = GovernanceEngine(
        Constitution.from_rules(
            [
                Rule(
                    id="FUTURE-DEPLOY",
                    text="Future deployment freeze",
                    severity=Severity.HIGH,
                    keywords=["deploy"],
                    valid_from="2099-01-01T00:00:00",
                )
            ]
        ),
        strict=False,
    )

    assert engine.validate("deploy model").violations == []
    assert [
        v.rule_id
        for v in engine.validate(
            "deploy model",
            context={"timestamp": "2100-01-01T00:00:00"},
        ).violations
    ] == ["FUTURE-DEPLOY"]


def test_runtime_filter_uses_explicit_timestamp_for_expired_rule() -> None:
    engine = GovernanceEngine(
        Constitution.from_rules(
            [
                Rule(
                    id="SUNSET-RULE",
                    text="Sunset secret handling gate",
                    severity=Severity.HIGH,
                    keywords=["secret"],
                    valid_until="2025-12-31T23:59:59",
                )
            ]
        ),
        strict=False,
    )

    assert [
        v.rule_id
        for v in engine.validate(
            "leak secret",
            context={"timestamp": "2025-06-01T00:00:00"},
        ).violations
    ] == ["SUNSET-RULE"]
    assert (
        engine.validate(
            "leak secret",
            context={"timestamp": "2026-01-01T00:00:00"},
        ).violations
        == []
    )
