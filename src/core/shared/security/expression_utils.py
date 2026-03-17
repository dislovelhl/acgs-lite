"""
ACGS-2 Shared Expression Evaluation Utilities

Constitutional Hash: cdd01ef066bc6cf2

Safe expression evaluation and PII redaction utilities shared across components.
These functions prevent code injection while allowing necessary mathematical operations.
"""

import ast
import hashlib
import json
import operator

from src.core.shared.errors.exceptions import ValidationError as ACGSValidationError

# Safe math expression evaluator
SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


def _eval_node(node):
    """Safely evaluate an AST node."""
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return float(node.value)
    elif isinstance(node, ast.BinOp) and type(node.op) in SAFE_OPS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return SAFE_OPS[type(node.op)](left, right)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        operand = _eval_node(node.operand)
        return SAFE_OPS[type(node.op)](operand)
    else:
        raise ACGSValidationError(
            message=f"Unsupported expression node: {type(node).__name__}",
            error_code="EXPR_UNSUPPORTED_NODE",
        )


def safe_eval_expr(expr: str) -> float:
    """
    Safely evaluate arithmetic expression using AST parsing.

    This function prevents code injection by only allowing mathematical operations
    on numeric constants. No variables, function calls, or other Python constructs
    are permitted.

    Args:
        expr: Arithmetic expression string (e.g., "2 + 3 * 4")

    Returns:
        Result of the mathematical expression as a float

    Raises:
        ValueError: If expression contains unsupported operations or syntax
    """
    try:
        tree = ast.parse(expr, mode="eval")
        return _eval_node(tree.body)
    except (
        SyntaxError,
        ValueError,
        ACGSValidationError,
        ZeroDivisionError,
        OverflowError,
        TypeError,
    ) as e:
        raise ACGSValidationError(
            message=f"Invalid expression: {expr}", error_code="EXPR_INVALID"
        ) from e


def redact_pii(data: object) -> object:
    """
    Redact or hash potentially sensitive fields from audit payloads recursively.

    Removes or hashes fields that may contain PII or sensitive information
    while preserving audit trail integrity through hashing.

    Args:
        data: Data to redact (dict, list, or primitive)

    Returns:
        Redacted copy of the data
    """
    # Fields to redact completely (no traceability needed)
    sensitive_fields = {"content_preview", "content", "password", "api_key", "token", "secret"}
    # Fields to hash instead of removing (for traceability)
    hash_fields = {"metadata", "user_id", "email"}

    if isinstance(data, dict):
        redacted = {}
        for k, v in data.items():
            if k in sensitive_fields:
                continue
            if k in hash_fields and v is not None:
                if isinstance(v, (dict, list)):
                    # Hash the JSON representation for complex data
                    v_str = json.dumps(v, sort_keys=True)
                else:
                    v_str = str(v)
                redacted[k] = f"<redacted_hash:{hashlib.sha256(v_str.encode()).hexdigest()[:16]}>"
            else:
                redacted[k] = redact_pii(v)
        return redacted
    elif isinstance(data, list):
        return [redact_pii(item) for item in data]
    else:
        return data
