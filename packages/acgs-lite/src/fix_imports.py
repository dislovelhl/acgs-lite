# fix analytics.py
path = "packages/acgs-lite/src/acgs_lite/constitution/analytics.py"
with open(path) as f:
    content = f.read()
if "from .core import Rule" not in content:
    content = content.replace(
        "from typing import Any", "from typing import Any\nfrom .core import Rule\n"
    )
with open(path, "w") as f:
    f.write(content)

# fix core.py
path = "packages/acgs-lite/src/acgs_lite/constitution/core.py"
with open(path) as f:
    content = f.read()
if "from .analytics import" not in content:
    content = content.replace(
        "from typing import Any",
        "from typing import Any\nfrom .analytics import _KW_NEGATIVE_RE, _NEGATIVE_VERBS_RE, _POSITIVE_VERBS_SET\n",
    )
with open(path, "w") as f:
    f.write(content)

# We need RuleSnapshot and ConstitutionBuilder locally in core.py methods to avoid circular imports.
content = content.replace(
    "RuleSnapshot.from_rule(",
    "from .versioning import RuleSnapshot\n        snapshot = RuleSnapshot.from_rule(",
)
content = content.replace(
    "b = ConstitutionBuilder(",
    "from .templates import ConstitutionBuilder\n        b = ConstitutionBuilder(",
)
with open(path, "w") as f:
    f.write(content)


# fix templates.py
path = "packages/acgs-lite/src/acgs_lite/constitution/templates.py"
with open(path) as f:
    content = f.read()
if "from .core import" not in content:
    content = content.replace(
        "from typing import Any",
        "from typing import Any\nfrom .core import Rule, Severity, Constitution\n",
    )
with open(path, "w") as f:
    f.write(content)

# fix versioning.py
path = "packages/acgs-lite/src/acgs_lite/constitution/versioning.py"
with open(path) as f:
    content = f.read()
if "from .core import Rule" not in content:
    content = content.replace(
        "from typing import Any",
        "from typing import Any, TYPE_CHECKING\nif TYPE_CHECKING:\n    from .core import Rule\n",
    )
with open(path, "w") as f:
    f.write(content)


# fix engine/batch.py
path = "packages/acgs-lite/src/acgs_lite/engine/batch.py"
with open(path) as f:
    content = f.read()
# Replace the broken imports
content = content.replace(
    "try:\n\nfrom typing import Any\nfrom .core import GovernanceEngine, ValidationResult",
    "from typing import Any\nfrom .core import GovernanceEngine, ValidationResult",
)
content = content.replace("# Optional Aho-Corasick C extension for O(n) keyword scanning\n", "")
with open(path, "w") as f:
    f.write(content)

# fix engine/core.py
path = "packages/acgs-lite/src/acgs_lite/engine/core.py"
with open(path) as f:
    content = f.read()
content = content.replace("try:\n\nfrom .rust", "from .rust")
with open(path, "w") as f:
    f.write(content)
