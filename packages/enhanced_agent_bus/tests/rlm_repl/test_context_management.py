"""
Tests for REPL context management and helper functions.
Constitutional Hash: 608508a9bd224290
"""

import pytest

from enhanced_agent_bus.tests.rlm_repl.conftest import _make_repl


class TestContextManagement:
    def test_set_and_get_context(self):
        repl = _make_repl()
        repl.set_context("doc", "hello world")
        assert repl.get_context("doc") == "hello world"

    def test_set_context_available_in_namespace(self):
        repl = _make_repl()
        repl.set_context("policy", "some policy text")
        assert repl._namespace["policy"] == "some policy text"

    def test_list_contexts(self):
        repl = _make_repl()
        repl.set_context("a", "text a")
        repl.set_context("b", "text b")
        contexts = repl.list_contexts()
        assert "a" in contexts
        assert "b" in contexts

    def test_get_nonexistent_context_returns_none(self):
        repl = _make_repl()
        assert repl.get_context("nonexistent") is None

    def test_clear_existing_context(self):
        repl = _make_repl()
        repl.set_context("x", "data")
        result = repl.clear_context("x")
        assert result is True
        assert repl.get_context("x") is None
        assert "x" not in repl._namespace

    def test_clear_nonexistent_context_returns_false(self):
        repl = _make_repl()
        result = repl.clear_context("does_not_exist")
        assert result is False

    def test_set_context_too_large_raises_value_error(self):
        from enhanced_agent_bus.rlm_repl import REPLConfig

        config = REPLConfig(max_context_size_mb=1)
        repl = _make_repl(config)
        big_content = "x" * (2 * 1024 * 1024)  # 2 MB
        with pytest.raises(ValueError, match="Context too large"):
            repl.set_context("big", big_content)

    def test_set_context_exceeds_max_variables_raises(self):
        from enhanced_agent_bus.rlm_repl import REPLConfig

        config = REPLConfig(max_variables=2)
        repl = _make_repl(config)
        repl.set_context("v1", "a")
        repl.set_context("v2", "b")
        with pytest.raises(ValueError, match="Too many contexts"):
            repl.set_context("v3", "c")


class TestHelperFunctions:
    def test_search_context_specific_context(self):
        repl = _make_repl()
        repl.set_context("doc", "the cat sat on the mat")
        results = repl._search_context("cat", "doc")
        assert len(results) == 1
        assert results[0]["match"] == "cat"
        assert results[0]["context"] == "doc"

    def test_search_context_all_contexts(self):
        repl = _make_repl()
        repl.set_context("a", "hello world")
        repl.set_context("b", "hello there")
        results = repl._search_context("hello")
        assert len(results) == 2

    def test_search_context_nonexistent_context_name_falls_back_to_all(self):
        repl = _make_repl()
        repl.set_context("a", "test data")
        results = repl._search_context("test", "nonexistent")
        assert len(results) == 1

    def test_search_context_no_match(self):
        repl = _make_repl()
        repl.set_context("doc", "hello world")
        results = repl._search_context("xyz")
        assert results == []

    def test_search_context_surrounding_snippet(self):
        repl = _make_repl()
        content = "a" * 60 + "TARGET" + "b" * 60
        repl.set_context("doc", content)
        results = repl._search_context("TARGET")
        assert results[0]["surrounding"] is not None
        assert "TARGET" in results[0]["surrounding"]

    def test_slice_context_basic(self):
        repl = _make_repl()
        repl.set_context("doc", "0123456789")
        result = repl._slice_context("doc", 2, 6)
        assert result == "2345"

    def test_slice_context_missing_raises_key_error(self):
        repl = _make_repl()
        with pytest.raises(KeyError, match="not found"):
            repl._slice_context("missing", 0, 5)

    def test_find_all_basic(self):
        repl = _make_repl()
        results = repl._find_all(r"\d+", "abc 123 def 456")
        assert "123" in results
        assert "456" in results

    def test_word_count_helper(self):
        repl = _make_repl()
        wc = repl._namespace["word_count"]
        assert wc("hello world foo") == 3

    def test_line_count_helper(self):
        repl = _make_repl()
        lc = repl._namespace["line_count"]
        assert lc("line1\nline2\nline3") == 3
