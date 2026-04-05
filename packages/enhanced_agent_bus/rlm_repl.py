from __future__ import annotations

import ast
import asyncio
import builtins as py_builtins
import json
import os
import re
import sys
import time
from contextlib import redirect_stdout
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from io import StringIO
from typing import Any

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.errors import ACGSBaseError
from enhanced_agent_bus._compat.security.execution_time_limit import (
    ExecutionTimeout,
    python_execution_time_limit,
)

from .observability.structured_logging import get_logger

logger = get_logger(__name__)

SAFE_BUILTINS: set[str] = {
    "abs",
    "all",
    "any",
    "bool",
    "dict",
    "enumerate",
    "filter",
    "float",
    "int",
    "len",
    "list",
    "map",
    "max",
    "min",
    "range",
    "reversed",
    "round",
    "set",
    "sorted",
    "str",
    "sum",
    "tuple",
    "zip",
}

BLOCKED_PATTERNS: list[str] = [
    r"__import__\s*\(",
    r"\bexec\s*\(",
    r"\beval\s*\(",
    r"\bopen\s*\(",
    r"\bcompile\s*\(",
    r"\bsubprocess\b",
]

HARD_EXECUTION_TIMEOUT_SECONDS = 5.0
REPL_EXECUTION_ERRORS = (RuntimeError, ValueError, TypeError, KeyError, AttributeError, OSError)
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development").lower() == "production"
ENABLE_RLM_REPL = os.getenv("ENABLE_RLM_REPL", "").lower() in {"1", "true", "yes", "on"}

_DANGEROUS_NAMES = {
    "__builtins__",
    "__import__",
    "compile",
    "eval",
    "exec",
    "globals",
    "help",
    "input",
    "locals",
    "open",
    "os",
    "subprocess",
    "sys",
    "vars",
}


def is_repl_enabled() -> bool:
    if IS_PRODUCTION:
        if ENABLE_RLM_REPL:
            logger.warning("RLM REPL BLOCKED in production environment")
        return False
    return ENABLE_RLM_REPL


class REPLDisabledError(ACGSBaseError):
    http_status_code = 403
    error_code = "REPL_DISABLED"


class REPLSecurityLevel(str, Enum):
    STRICT = "strict"
    STANDARD = "standard"
    PERMISSIVE = "permissive"


@dataclass(slots=True)
class REPLConfig:
    security_level: REPLSecurityLevel = REPLSecurityLevel.STANDARD
    max_execution_time_seconds: float = 30.0
    max_memory_mb: int = 512
    max_output_length: int = 100_000
    allow_imports: bool = False
    allow_file_access: bool = False
    allow_network: bool = False
    allow_subprocess: bool = False
    max_context_size_mb: int = 100
    max_variables: int = 100
    enable_audit_trail: bool = True
    audit_all_operations: bool = True
    enable_rate_limiting: bool = True
    max_operations_per_minute: int = 60
    max_operations_per_hour: int = 500
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass(slots=True)
class REPLOperation:
    operation_id: str
    timestamp: datetime
    code: str
    result_preview: str
    execution_time_ms: float
    success: bool
    error: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.astimezone(UTC).isoformat()
        payload["code"] = self.code if len(self.code) <= 200 else f"{self.code[:200]}..."
        return payload


class _SafeRegex:
    def __init__(self, max_matches: int = 100) -> None:
        self.max_matches = max_matches

    def search(self, pattern: str, text: str, flags: int = 0):
        return re.search(pattern, text, flags)

    def findall(self, pattern: str, text: str, flags: int = 0) -> list[str]:
        return re.findall(pattern, text, flags)[: self.max_matches]

    def finditer(self, pattern: str, text: str, flags: int = 0):
        for index, match in enumerate(re.finditer(pattern, text, flags)):
            if index >= self.max_matches:
                break
            yield match

    def sub(self, pattern: str, repl: str, text: str, count: int = 0, flags: int = 0) -> str:
        return re.sub(pattern, repl, text, count=count, flags=flags)

    def split(self, pattern: str, text: str, maxsplit: int = 0, flags: int = 0) -> list[str]:
        return re.split(pattern, text, maxsplit=maxsplit, flags=flags)


def _safe_json_loads(payload: str) -> Any:
    return json.loads(payload)


def _safe_json_dumps(payload: Any) -> str:
    return json.dumps(payload, default=str, sort_keys=True)


class _FrozenBuiltinsDict(dict[str, Any]):
    def _blocked(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("safe builtins mapping is immutable")

    __setitem__ = _blocked
    __delitem__ = _blocked
    clear = _blocked
    pop = _blocked
    popitem = _blocked
    setdefault = _blocked
    update = _blocked


class RLMREPLEnvironment:
    def __init__(self, config: REPLConfig | None = None) -> None:
        if not is_repl_enabled():
            raise REPLDisabledError("RLM REPL is disabled")
        self.config = config or REPLConfig()
        self._operation_count = 0
        self._audit_trail: list[REPLOperation] = []
        self._contexts: dict[str, str] = {}
        self._rate_limit_violations = 0
        self._operation_timestamps: list[float] = []
        self._regex = _SafeRegex()
        self._namespace: dict[str, Any] = {}
        self._setup_safe_namespace()

    def _setup_safe_namespace(self) -> None:
        safe_builtins = _FrozenBuiltinsDict(
            {name: getattr(py_builtins, name) for name in SAFE_BUILTINS}
        )
        self._namespace = {
            "__builtins__": safe_builtins,
            "re": self._regex,
            "json_loads": _safe_json_loads,
            "json_dumps": _safe_json_dumps,
            "search": self._search_context,
            "slice_context": self._slice_context,
            "word_count": lambda text: len(str(text).split()),
            "line_count": lambda text: len(str(text).splitlines()),
            "find_all": self._find_all,
        }
        self._namespace.update(self._contexts)

    def _get_safe_globals(self) -> dict[str, Any]:
        return {"__builtins__": self._namespace["__builtins__"]}

    def _validate_code(self, code: str) -> list[str]:
        issues: list[str] = []
        for pattern in BLOCKED_PATTERNS:
            if re.search(pattern, code):
                issues.append(f"Blocked pattern detected: {pattern}")
        try:
            tree = ast.parse(code, mode="eval")
        except SyntaxError:
            try:
                tree = ast.parse(code, mode="exec")
            except SyntaxError as exc:
                return [f"Syntax error: {exc.msg}"]
        try:
            self._validate_ast_security(tree)
        except ValueError as exc:
            issues.append(str(exc))
        return issues

    def _validate_ast_security(self, tree: ast.AST) -> None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if not self.config.allow_imports:
                    raise ValueError("SECURITY: Import statements not allowed")
            if isinstance(node, ast.Name):
                if node.id == "_" or node.id.startswith("_output"):
                    continue
                if node.id.startswith("__"):
                    raise ValueError("SECURITY: Dunder names are not allowed")
                if node.id in _DANGEROUS_NAMES:
                    raise ValueError(f"SECURITY: Name {node.id!r} is not allowed")
            if isinstance(node, ast.Attribute):
                if node.attr == "_output":
                    continue
                if node.attr.startswith("__"):
                    raise ValueError("SECURITY: Dunder attribute access is not allowed")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if "__import__" in node.value:
                    logger.warning("Suspicious REPL string literal detected")

    def _check_rate_limit(self) -> str | None:
        if not self.config.enable_rate_limiting:
            return None
        now = time.time()
        self._operation_timestamps = [ts for ts in self._operation_timestamps if now - ts < 3600]
        per_minute = [ts for ts in self._operation_timestamps if now - ts < 60]
        if len(per_minute) >= self.config.max_operations_per_minute:
            self._rate_limit_violations += 1
            return "Rate limit exceeded: per-minute threshold reached"
        if len(self._operation_timestamps) >= self.config.max_operations_per_hour:
            self._rate_limit_violations += 1
            return "Rate limit exceeded: per-hour threshold reached"
        return None

    async def execute(self, code: str) -> dict[str, Any]:
        if not is_repl_enabled():
            raise REPLDisabledError("RLM REPL is disabled")
        rate_limit_error = self._check_rate_limit()
        if rate_limit_error is not None:
            return {"success": False, "error": rate_limit_error}

        started = time.perf_counter()
        timeout_seconds = min(
            self.config.max_execution_time_seconds, HARD_EXECUTION_TIMEOUT_SECONDS
        )
        operation_id = f"op_{self._operation_count}"
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._execute_sync, code),
                timeout=timeout_seconds,
            )
            success = True
            error = None
        except TimeoutError:
            result = None
            success = False
            error = f"Execution timed out after {timeout_seconds} seconds"
        except REPL_EXECUTION_ERRORS as exc:
            result = None
            success = False
            error = str(exc)

        self._operation_count += 1
        self._operation_timestamps.append(time.time())
        duration_ms = (time.perf_counter() - started) * 1000.0
        preview = "" if result is None else str(result)[:200]
        self._record_operation(operation_id, code, preview, duration_ms, success, error)

        if success:
            return {"success": True, "result": result}
        return {"success": False, "error": error}

    def _execute_sync(self, code: str) -> Any:
        issues = self._validate_code(code)
        if issues:
            raise ValueError("; ".join(issues))

        buffer = StringIO()
        timeout_seconds = min(
            self.config.max_execution_time_seconds, HARD_EXECUTION_TIMEOUT_SECONDS
        )
        try:
            with python_execution_time_limit(timeout_seconds), redirect_stdout(buffer):
                try:
                    compiled_eval = compile(code, "<rlm-repl>", "eval")
                except SyntaxError:
                    compiled_exec = compile(code, "<rlm-repl>", "exec")
                    # Security: exec is intentional here. All user input passes through
                    # _validate_code() first, which:
                    #   1. Rejects code matching BLOCKED_PATTERNS (import, open, exec, eval,
                    #      __import__, os, sys, subprocess, etc.)
                    #   2. Validates AST nodes to block disallowed constructs
                    # The namespace uses SAFE_BUILTINS (restricted allowlist, no __import__).
                    # Execution is bounded by python_execution_time_limit / HARD_EXECUTION_TIMEOUT_SECONDS.
                    exec(compiled_exec, self._namespace, self._namespace)  # noqa: S102 S307
                    if "_" in self._namespace:
                        return self._namespace["_"]
                    output = buffer.getvalue()
                    return output[: self.config.max_output_length]
                return eval(compiled_eval, self._namespace, self._namespace)  # noqa: S307 — sandboxed REPL with ExecutionTimeout guard and isolated namespace
        except ExecutionTimeout as exc:
            raise RuntimeError("Execution exceeded allowed time") from exc

    def set_context(self, name: str, content: str) -> None:
        size_bytes = len(content.encode("utf-8"))
        if size_bytes > self.config.max_context_size_mb * 1024 * 1024:
            raise ValueError("Context too large")
        if name not in self._contexts and len(self._contexts) >= self.config.max_variables:
            raise ValueError("Too many contexts")
        self._contexts[name] = content
        self._namespace[name] = content

    def get_context(self, name: str) -> str | None:
        return self._contexts.get(name)

    def list_contexts(self) -> list[str]:
        return sorted(self._contexts)

    def clear_context(self, name: str) -> bool:
        if name not in self._contexts:
            return False
        del self._contexts[name]
        self._namespace.pop(name, None)
        return True

    def _search_context(
        self, pattern: str, context_name: str | None = None
    ) -> list[dict[str, str | None]]:
        names = [context_name] if context_name in self._contexts else list(self._contexts)
        results: list[dict[str, str | None]] = []
        for name in names:
            content = self._contexts[name]
            for match in self._regex.finditer(pattern, content):
                start = max(0, match.start() - 50)
                end = min(len(content), match.end() + 50)
                results.append(
                    {
                        "context": name,
                        "match": match.group(0),
                        "surrounding": content[start:end],
                    }
                )
        return results

    def _slice_context(self, context_name: str, start: int, end: int) -> str:
        if context_name not in self._contexts:
            raise KeyError(f"Context {context_name!r} not found")
        return self._contexts[context_name][start:end]

    def _find_all(self, pattern: str, text: str) -> list[str]:
        return self._regex.findall(pattern, text)

    def _record_operation(
        self,
        operation_id: str,
        code: str,
        result_preview: str,
        execution_time_ms: float,
        success: bool,
        error: str | None = None,
    ) -> None:
        if not self.config.enable_audit_trail:
            return
        self._audit_trail.append(
            REPLOperation(
                operation_id=operation_id,
                timestamp=datetime.now(UTC),
                code=code,
                result_preview=result_preview,
                execution_time_ms=execution_time_ms,
                success=success,
                error=error,
                constitutional_hash=self.config.constitutional_hash,
            )
        )

    def get_audit_trail(self, limit: int | None = None) -> list[dict[str, Any]]:
        records = self._audit_trail[-limit:] if limit is not None else self._audit_trail
        return [record.to_dict() for record in records]

    def clear_audit_trail(self) -> None:
        self._audit_trail.clear()

    def get_metrics(self) -> dict[str, int]:
        total_context_size = sum(len(value) for value in self._contexts.values())
        return {
            "contexts_loaded": len(self._contexts),
            "total_context_size": total_context_size,
            "operations_executed": self._operation_count,
            "rate_limit_violations": self._rate_limit_violations,
        }

    def reset(self) -> None:
        self._contexts.clear()
        self._operation_count = 0
        self._operation_timestamps.clear()
        self._setup_safe_namespace()


def create_rlm_repl(config: REPLConfig | None = None) -> RLMREPLEnvironment:
    return RLMREPLEnvironment(config or REPLConfig())


def create_governance_repl() -> RLMREPLEnvironment:
    return RLMREPLEnvironment(REPLConfig(security_level=REPLSecurityLevel.STRICT))


_module = sys.modules.get(__name__)
if _module is not None:
    sys.modules.setdefault("enhanced_agent_bus.rlm_repl", _module)
    sys.modules.setdefault("packages.enhanced_agent_bus.rlm_repl", _module)
