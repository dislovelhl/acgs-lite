# Constitution

The `Constitution` class is the core rule container. It loads governance rules from YAML, validates them, and exposes matching and amendment APIs.

## Class Reference

::: acgs_lite.constitution.constitution.Constitution
    options:
      members:
        - from_yaml
        - from_template
        - from_dict
        - validate
        - match
        - compare
        - diff_summary
        - apply_amendments_with_report
      show_source: true

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
# templates: "general", "healthcare", "finance", "legal", "enterprise"
```

### Compare two constitutions

```python
diff = constitution.diff_summary(updated_constitution)
print(diff)
```
