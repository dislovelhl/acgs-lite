"""
Context Window Optimization
Constitutional Hash: 608508a9bd224290

Reference: SPEC_ACGS2_ENHANCED_v2.3 Section 16.3 (Context Management)
"""

import re

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

# Constitutional Hash - immutable reference


class ContextWindowOptimizer:
    """
    Optimizes context window usage for LLM interactions.

    Implements intelligent context compression, prioritization,
    and token management to maximize efficiency.
    """

    # Approximate characters per token for estimation
    CHARS_PER_TOKEN = 4

    def __init__(self, max_tokens: int = 8000) -> None:
        """
        Initialize context window optimizer.

        Args:
            max_tokens: Maximum token budget for context
        """
        self.max_tokens = max_tokens

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for given text.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        return len(text) // self.CHARS_PER_TOKEN

    def compress_context(
        self,
        context: str,
        max_tokens: int | None = None,
        importance_threshold: float = 0.7,
    ) -> str:
        """
        Compress context to fit within token budget.

        Args:
            context: Original context string
            max_tokens: Optional override for max tokens
            importance_threshold: Minimum importance score to keep content

        Returns:
            Compressed context string
        """
        limit = max_tokens or self.max_tokens
        estimated_tokens = self.estimate_tokens(context)

        # No compression needed
        if estimated_tokens <= limit:
            return context

        lines = context.split("\n")
        if len(lines) <= 20:
            # Simple truncation for short content
            target_chars = limit * self.CHARS_PER_TOKEN
            if len(context) <= target_chars:
                return context
            return (
                context[: target_chars // 2]
                + "\n[...context compressed...]\n"
                + context[-target_chars // 2 :]
            )

        # Intelligent compression for longer content
        # Keep system instructions (start) and recent history (end)
        system_segment = lines[:5]
        recent_segment = lines[-10:]
        middle_segment = lines[5:-10]

        # Filter low-value content from middle
        distilled_middle = [line for line in middle_segment if not self._is_low_value(line)]

        # Further truncate if still over limit
        target_middle_tokens = limit - self.estimate_tokens(
            "\n".join(system_segment + recent_segment)
        )
        current_middle_tokens = self.estimate_tokens("\n".join(distilled_middle))

        if current_middle_tokens > target_middle_tokens and len(distilled_middle) > 50:
            keep_count = max(10, len(distilled_middle) // 2)
            distilled_middle = (
                distilled_middle[: keep_count // 2]
                + ["... [distilled] ..."]
                + distilled_middle[-keep_count // 2 :]
            )

        result = "\n".join(system_segment + distilled_middle + recent_segment)

        # Final safety truncation
        if self.estimate_tokens(result) > limit:
            target_chars = limit * self.CHARS_PER_TOKEN
            result = (
                result[: target_chars // 2]
                + "\n[...context compressed...]\n"
                + result[-target_chars // 2 :]
            )

        return result

    def prioritize_context(
        self,
        contexts: list[JSONDict],
        max_total_tokens: int,
    ) -> list[JSONDict]:
        """
        Prioritize and select contexts within token budget.

        Each context dict should have:
        - content: str
        - priority: int (higher = more important)
        - timestamp: int/float (for recency sorting)

        Args:
            contexts: List of context dictionaries
            max_total_tokens: Maximum total token budget

        Returns:
            Prioritized list of contexts that fit within budget
        """
        if not contexts:
            return []

        # Sort by priority (descending), then by timestamp (descending)
        sorted_contexts = sorted(
            contexts,
            key=lambda c: (c.get("priority", 0), c.get("timestamp", 0)),
            reverse=True,
        )

        selected = []
        total_tokens = 0

        for ctx in sorted_contexts:
            content = ctx.get("content", "")
            tokens = self.estimate_tokens(content)

            if total_tokens + tokens <= max_total_tokens:
                selected.append(ctx)
                total_tokens += tokens
            else:
                # Try to fit compressed version
                remaining = max_total_tokens - total_tokens
                if remaining > 50:  # Minimum useful context
                    compressed = self.compress_context(content, remaining)
                    if self.estimate_tokens(compressed) <= remaining:
                        ctx_copy = ctx.copy()
                        ctx_copy["content"] = compressed
                        ctx_copy["compressed"] = True
                        selected.append(ctx_copy)
                        break

        return selected

    def _is_low_value(self, line: str) -> bool:
        """
        Identify low-value lines (boilerplate, logs, noise).

        Args:
            line: Line to evaluate

        Returns:
            True if line is low-value
        """
        low_value_patterns = [
            r"^(DEBUG|INFO|TRACE|VERBOSE):",
            r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]",  # ISO Timestamps
            r"^Traceback",
            r"^\s*at\s+",  # Stack traces
            r"^\{.*\}$",  # Large JSON blobs
            r"^[=\-_]{5,}$",  # Separators
            r"^\s*$",  # Empty lines
            r"^#.*$",  # Comments (in some contexts)
            r"^(HTTP/|GET |POST |PUT |DELETE )",  # HTTP Request/Response lines
            r"^(Host:|User-Agent:|Accept:|Content-Type:|Content-Length:|Authorization:|X-)",  # HTTP Headers
            r"^[.*]{10,}$",  # Repetitive punctuation noise
            r"^(\+\+\+|---) ",  # Diff markers (if not critical)
        ]
        return any(re.search(pattern, line) for pattern in low_value_patterns)


# Legacy compatibility alias
class ContextCompressor(ContextWindowOptimizer):
    """Legacy compatibility wrapper for ContextWindowOptimizer."""

    def compress(self, context: str, importance_threshold: float = 0.7) -> str:
        """Legacy compress method."""
        return self.compress_context(context, importance_threshold=importance_threshold)


def compress_context(context: str, max_tokens: int = 4000) -> str:
    """
    Convenience functional API for context compression.

    Args:
        context: Context string to compress
        max_tokens: Maximum token budget

    Returns:
        Compressed context string
    """
    optimizer = ContextWindowOptimizer(max_tokens=max_tokens)
    return optimizer.compress_context(context)
