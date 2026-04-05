"""Tests for TemplateRegistry (constitutional template marketplace)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from acgs_lite.constitution.template_registry import (
    TemplateMetadata,
    TemplateRegistry,
    get_registry,
)


def _make_template(*, name: str = "test-template", rule_count: int = 2) -> dict:
    return {
        "name": name,
        "version": "1.0.0",
        "description": f"Test template with {rule_count} rules",
        "rules": [
            {
                "id": f"R-{i}",
                "text": f"Rule {i} text",
                "severity": "high",
                "keywords": [f"keyword-{i}"],
                "category": "test",
            }
            for i in range(rule_count)
        ],
    }


class TestTemplateRegistration:
    def test_register_template(self):
        registry = TemplateRegistry(include_builtins=False)
        data = _make_template()
        meta = registry.register("my-template", data, author="test", domain="testing")

        assert meta.slug == "my-template"
        assert meta.name == "test-template"
        assert meta.author == "test"
        assert meta.domain == "testing"
        assert meta.rule_count == 2
        assert registry.count == 1

    def test_register_empty_slug_raises(self):
        registry = TemplateRegistry(include_builtins=False)
        with pytest.raises(ValueError, match="empty"):
            registry.register("", _make_template())

    def test_register_no_rules_raises(self):
        registry = TemplateRegistry(include_builtins=False)
        with pytest.raises(ValueError, match="no rules"):
            registry.register("empty", {"name": "empty", "rules": []})

    def test_register_overwrites_non_builtin(self):
        registry = TemplateRegistry(include_builtins=False)
        registry.register("slug", _make_template(rule_count=2))
        registry.register("slug", _make_template(rule_count=5))
        assert registry.get_metadata("slug").rule_count == 5

    def test_cannot_overwrite_builtin(self):
        registry = TemplateRegistry(include_builtins=True)
        builtins = registry.list_templates(author="built-in")
        if builtins:
            slug = builtins[0].slug
            with pytest.raises(ValueError, match="built-in"):
                registry.register(slug, _make_template(), author="community")

    def test_mutation_after_load_does_not_affect_registry(self):
        registry = TemplateRegistry(include_builtins=False)
        registry.register("safe", _make_template(name="original"))
        loaded = registry.load("safe")
        loaded["name"] = "mutated"
        assert registry.load("safe")["name"] == "original"


class TestTemplateLoading:
    def test_load_registered(self):
        registry = TemplateRegistry(include_builtins=False)
        data = _make_template()
        registry.register("my-template", data)

        loaded = registry.load("my-template")
        assert loaded["name"] == "test-template"
        assert len(loaded["rules"]) == 2

    def test_load_unknown_raises(self):
        registry = TemplateRegistry(include_builtins=False)
        with pytest.raises(KeyError, match="Unknown template"):
            registry.load("nonexistent")


class TestBuiltinTemplates:
    def test_builtins_loaded(self):
        registry = TemplateRegistry(include_builtins=True)
        assert registry.count >= 1  # At least "general" or "gitlab" should exist

    def test_builtin_has_metadata(self):
        registry = TemplateRegistry(include_builtins=True)
        templates = registry.list_templates()
        assert len(templates) >= 1
        for meta in templates:
            assert meta.slug
            assert meta.rule_count > 0
            assert meta.author == "built-in"


class TestFileLoading:
    def test_load_from_json_file(self):
        registry = TemplateRegistry(include_builtins=False)
        data = _make_template(name="json-template")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            loaded = registry.load_from_file(f.name)

        assert loaded["name"] == "json-template"
        assert registry.count == 1

    def test_load_from_yaml_file(self):
        try:
            import yaml
        except ImportError:
            pytest.skip("PyYAML not installed")

        registry = TemplateRegistry(include_builtins=False)
        data = _make_template(name="yaml-template")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            f.flush()
            loaded = registry.load_from_file(f.name)

        assert loaded["name"] == "yaml-template"

    def test_load_nonexistent_raises(self):
        registry = TemplateRegistry(include_builtins=False)
        with pytest.raises(FileNotFoundError):
            registry.load_from_file("/nonexistent/template.json")

    def test_load_unsupported_format_raises(self):
        registry = TemplateRegistry(include_builtins=False)
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"not a template")
            f.flush()
            with pytest.raises(ValueError, match="Unsupported"):
                registry.load_from_file(f.name)

    def test_load_from_directory(self):
        registry = TemplateRegistry(include_builtins=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                data = _make_template(name=f"dir-template-{i}")
                path = Path(tmpdir) / f"template-{i}.json"
                path.write_text(json.dumps(data))

            loaded = registry.load_from_directory(tmpdir)
            assert len(loaded) == 3
            assert registry.count == 3


class TestSearch:
    def test_list_by_domain(self):
        registry = TemplateRegistry(include_builtins=False)
        registry.register("hipaa", _make_template(), domain="healthcare")
        registry.register("gdpr", _make_template(), domain="privacy")
        registry.register("nist", _make_template(), domain="security")

        healthcare = registry.list_templates(domain="healthcare")
        assert len(healthcare) == 1
        assert healthcare[0].slug == "hipaa"

    def test_list_by_author(self):
        registry = TemplateRegistry(include_builtins=False)
        registry.register("t1", _make_template(), author="alice")
        registry.register("t2", _make_template(), author="bob")
        registry.register("t3", _make_template(), author="alice")

        alice = registry.list_templates(author="alice")
        assert len(alice) == 2

    def test_search_by_query(self):
        registry = TemplateRegistry(include_builtins=False)
        registry.register(
            "hipaa-strict",
            _make_template(),
            domain="healthcare",
            description="Strict HIPAA compliance for clinical AI",
        )
        registry.register(
            "eu-basic",
            _make_template(),
            domain="compliance",
            description="Basic EU AI Act assessment rules",
        )

        results = registry.search("hipaa")
        assert len(results) == 1
        assert results[0].slug == "hipaa-strict"

        results = registry.search("healthcare")
        assert len(results) == 1

    def test_search_no_results(self):
        registry = TemplateRegistry(include_builtins=False)
        results = registry.search("nonexistent")
        assert results == []


class TestUnregister:
    def test_unregister_existing(self):
        registry = TemplateRegistry(include_builtins=False)
        registry.register("temp", _make_template())
        assert registry.count == 1

        removed = registry.unregister("temp")
        assert removed is True
        assert registry.count == 0

    def test_unregister_nonexistent(self):
        registry = TemplateRegistry(include_builtins=False)
        removed = registry.unregister("nope")
        assert removed is False


class TestGlobalRegistry:
    def test_singleton(self):
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_has_builtins(self):
        r = get_registry()
        assert r.count >= 1


class TestTemplateMetadata:
    def test_to_dict(self):
        meta = TemplateMetadata(
            slug="test", name="Test", domain="testing",
            description="A test", author="tester", rule_count=5,
            tags=("a", "b"),
        )
        d = meta.to_dict()
        assert d["slug"] == "test"
        assert d["tags"] == ["a", "b"]
        assert d["rule_count"] == 5
