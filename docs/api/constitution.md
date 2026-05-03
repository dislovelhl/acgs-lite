# Constitution

The `Constitution` class is the core rule container. It loads governance rules from YAML, validates them, and exposes matching and amendment APIs.

For the HTTP lifecycle surface that manages constitution bundle state over
FastAPI, see [Constitution Lifecycle HTTP API](lifecycle.md).

## Class Reference

::: acgs_lite.constitution.constitution.Constitution
    options:
      members:
        - from_yaml
        - from_yaml_str
        - from_template
        - from_dict
        - from_rules
        - default
        - validate_rules
        - get_rule
        - apply_amendments
        - apply_amendments_with_report
        - compare
        - diff_summary
        - validate_integrity
      show_source: true

All members above are part of the **stable** API surface
(`acgs_lite.stability("Constitution") == "stable"`). Lifecycle types such as
`ConstitutionBundle` and `BundleStatus` are **beta** — see
[Constitution Lifecycle HTTP API](lifecycle.md).

## Rule model

::: acgs_lite.Rule
::: acgs_lite.RuleSnapshot
::: acgs_lite.ViolationAction
::: acgs_lite.AcknowledgedTension

`Rule`, `RuleSnapshot`, `ViolationAction`, and `AcknowledgedTension` are part
of the **stable** API surface and are imported directly from `acgs_lite`.

## ConstitutionBuilder

::: acgs_lite.ConstitutionBuilder

Programmatic builder for assembling a `Constitution` rule-by-rule when YAML
or template loading is not appropriate. **Stable** — covered by builder
fixtures in the test suite.

## ConstitutionDiff

::: acgs_lite.constitution.diffing.ConstitutionDiff

## AmendmentReviewReport

::: acgs_lite.constitution.diffing.AmendmentReviewReport

## Examples

### Load from YAML

```python
from acgs_lite import Constitution

constitution = Constitution.from_yaml("rules.yaml")
```

### Load from template

```python
constitution = Constitution.from_template("general")
# templates: "general", "healthcare", "finance", "security", "gitlab"
```

### Compare two constitutions

```python
diff = constitution.diff_summary(updated_constitution)
print(diff)
```
