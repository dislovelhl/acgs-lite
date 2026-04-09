from __future__ import annotations

import os


def read_file(filepath: str) -> list[str]:
    with open(filepath) as f:
        return f.readlines()


lines = read_file("packages/acgs-lite/src/acgs_lite/engine.py")


def get_chunk(start: int, end: int) -> str:
    return "".join(lines[start - 1 : end])


os.makedirs("packages/acgs-lite/src/acgs_lite/engine", exist_ok=True)

# 1. engine/rust.py
rust_content = get_chunk(1, 22) + get_chunk(23, 40)
with open("packages/acgs-lite/src/acgs_lite/engine/rust.py", "w") as f:
    f.write(rust_content)

# 2. engine/batch.py
batch_content = (
    get_chunk(1, 22)
    + """
from typing import Any
from .core import GovernanceEngine, ValidationResult
from acgs_lite.constitution import Severity
"""
    + "\n"
    + get_chunk(235, 286)
    + "\n\n"
    + """class BatchValidationMixin:
"""
)
# Extract validate_batch and validate_batch_report
batch_methods = get_chunk(1147, 1267)
# Un-indent batch_methods from 4 spaces to 4 spaces (already inside class)
batch_content += batch_methods

with open("packages/acgs-lite/src/acgs_lite/engine/batch.py", "w") as f:
    f.write(batch_content)

# 3. engine/core.py
core_imports = (
    get_chunk(1, 22)
    + """
from .rust import _HAS_RUST, _RUST_ALLOW, _RUST_DENY_CRITICAL, _RUST_DENY, _HAS_AHO

# Optional Aho-Corasick C extension for O(n) keyword scanning
if _HAS_AHO:
    import ahocorasick as _ac
"""
    + "\n"
    + get_chunk(42, 54)
    + "\n"
)

core_classes = get_chunk(56, 233)

# Modify GovernanceEngine to inherit from BatchValidationMixin
# We will just write it and replace the class signature
gov_engine_lines = lines[288:]
# Find class GovernanceEngine:
for i, line in enumerate(gov_engine_lines):
    if line.startswith("class GovernanceEngine:"):
        gov_engine_lines[i] = "class GovernanceEngine(BatchValidationMixin):\n"
        break

# Remove validate_batch and validate_batch_report from GovernanceEngine
# Their lines are 1148 to 1267 in the original file, which is offset 288 in gov_engine_lines
# original lines: 1148-1267
# array indices: 1147 to 1266
# In gov_engine_lines, index = original_line - 1 - 288 = original_line - 289
del gov_engine_lines[1147 - 289 : 1268 - 289]

core_gov_engine = "".join(gov_engine_lines)

core_content = (
    core_imports + core_classes + "\nfrom .batch import BatchValidationMixin\n\n" + core_gov_engine
)
with open("packages/acgs-lite/src/acgs_lite/engine/core.py", "w") as f:
    f.write(core_content)

# 4. engine/__init__.py
init_content = """from .core import Violation, ValidationResult, GovernanceEngine
from .batch import BatchValidationResult, BatchValidationMixin
from .rust import _HAS_RUST, _RUST_ALLOW, _RUST_DENY_CRITICAL, _RUST_DENY

__all__ = [
    "Violation", "ValidationResult", "GovernanceEngine",
    "BatchValidationResult", "BatchValidationMixin"
]
"""
with open("packages/acgs-lite/src/acgs_lite/engine/__init__.py", "w") as f:
    f.write(init_content)
