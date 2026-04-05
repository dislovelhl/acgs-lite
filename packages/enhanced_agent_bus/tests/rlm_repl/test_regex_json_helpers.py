"""
Tests for internal REPL helpers: _SafeRegex and JSON helpers.
Constitutional Hash: 608508a9bd224290
"""


class TestSafeRegex:
    def setup_method(self):
        from enhanced_agent_bus.rlm_repl import _SafeRegex

        self.regex = _SafeRegex(max_matches=5)

    def test_search_returns_match(self):
        m = self.regex.search(r"\d+", "abc 123")
        assert m is not None
        assert m.group() == "123"

    def test_search_returns_none_on_no_match(self):
        m = self.regex.search(r"\d+", "no digits")
        assert m is None

    def test_findall_capped_at_max_matches(self):
        results = self.regex.findall(r"\d+", "1 2 3 4 5 6 7")
        assert len(results) == 5

    def test_finditer_respects_max_matches(self):
        matches = list(self.regex.finditer(r"\d", "1234567890"))
        assert len(matches) == 5

    def test_sub_basic(self):
        result = self.regex.sub(r"\d", "X", "a1b2c3")
        assert "1" not in result
        assert "X" in result

    def test_split_basic(self):
        parts = self.regex.split(r",", "a,b,c,d,e,f")
        assert "a" in parts
        assert "b" in parts


class TestSafeJsonHelpers:
    def test_json_loads_valid(self):
        from enhanced_agent_bus.rlm_repl import _safe_json_loads

        result = _safe_json_loads('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_dumps_basic(self):
        from enhanced_agent_bus.rlm_repl import _safe_json_dumps

        result = _safe_json_dumps({"key": "value"})
        assert '"key"' in result
        assert '"value"' in result

    def test_json_dumps_non_serializable_uses_default(self):
        from datetime import datetime

        from enhanced_agent_bus.rlm_repl import _safe_json_dumps

        result = _safe_json_dumps({"ts": datetime(2024, 1, 1)})
        assert "2024" in result
