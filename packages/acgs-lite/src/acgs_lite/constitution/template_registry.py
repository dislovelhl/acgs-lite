"""Constitutional template registry for community and built-in governance templates.

Extends the built-in ``from_template()`` system with:
- A registry of community-contributed templates loadable via ``community/slug``
- File-based template loading from a local directory
- Template metadata (author, version, domain, description, rule count)
- Template listing and search

Usage::

    from acgs_lite import Constitution

    # Built-in (existing behavior)
    c = Constitution.from_template("healthcare")

    # Community registry (new)
    from acgs_lite.constitution.template_registry import TemplateRegistry
    registry = TemplateRegistry()
    registry.register("hipaa-strict", {...}, author="community", domain="healthcare")
    c = registry.load("hipaa-strict")

    # From file
    c = registry.load_from_file("path/to/template.yaml")

    # List available
    templates = registry.list_templates(domain="healthcare")
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TemplateMetadata:
    """Metadata for a registered constitutional template."""

    slug: str
    name: str
    domain: str
    description: str
    author: str = "built-in"
    version: str = "1.0.0"
    rule_count: int = 0
    tags: tuple[str, ...] = ()
    content_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "author": self.author,
            "version": self.version,
            "rule_count": self.rule_count,
            "tags": list(self.tags),
            "content_hash": self.content_hash,
        }


class TemplateRegistry:
    """Registry for constitutional governance templates.

    Supports built-in templates (from ``template_data.py``), community
    contributions, and file-based loading.
    """

    def __init__(self, *, include_builtins: bool = True) -> None:
        self._templates: dict[str, dict[str, Any]] = {}
        self._metadata: dict[str, TemplateMetadata] = {}

        if include_builtins:
            self._load_builtins()

    def _load_builtins(self) -> None:
        """Load built-in templates from template_data."""
        try:
            from .template_data import TEMPLATES
        except ImportError:
            return

        for domain, data in TEMPLATES.items():
            rules = data.get("rules", [])
            self._templates[domain] = data
            self._metadata[domain] = TemplateMetadata(
                slug=domain,
                name=data.get("name", domain),
                domain=domain,
                description=data.get("description", ""),
                author="built-in",
                version=data.get("version", "1.0.0"),
                rule_count=len(rules),
                tags=tuple(sorted({r.get("category", "") for r in rules if r.get("category")})),
                content_hash=_hash_template(data),
            )

    def register(
        self,
        slug: str,
        template_data: dict[str, Any],
        *,
        author: str = "community",
        domain: str = "",
        description: str = "",
        version: str = "1.0.0",
        tags: list[str] | None = None,
    ) -> TemplateMetadata:
        """Register a new constitutional template.

        Parameters
        ----------
        slug:
            Unique identifier (e.g., "hipaa-strict", "eu-ai-act-minimal").
        template_data:
            Dict compatible with ``Constitution.from_dict()``.
        author:
            Author name or organization.
        domain:
            Governance domain (healthcare, finance, security, etc.).

        Returns
        -------
        TemplateMetadata for the registered template.

        Raises
        ------
        ValueError: If slug is empty or template_data has no rules.
        """
        if not slug or not slug.strip():
            raise ValueError("Template slug cannot be empty")

        rules = template_data.get("rules", [])
        if not rules:
            raise ValueError(f"Template '{slug}' has no rules")

        # Protect built-in templates from overwrite
        existing = self._metadata.get(slug)
        if existing and existing.author == "built-in" and author != "built-in":
            raise ValueError(
                f"Cannot overwrite built-in template '{slug}'. "
                f"Use a different slug (e.g., 'community/{slug}')."
            )

        import copy
        self._templates[slug] = copy.deepcopy(template_data)
        meta = TemplateMetadata(
            slug=slug,
            name=template_data.get("name", slug),
            domain=domain or template_data.get("domain", "general"),
            description=description or template_data.get("description", ""),
            author=author,
            version=version,
            rule_count=len(rules),
            tags=tuple(tags or []),
            content_hash=_hash_template(template_data),
        )
        self._metadata[slug] = meta
        return meta

    def load(self, slug: str) -> dict[str, Any]:
        """Load a template by slug.

        Returns the raw template dict suitable for ``Constitution.from_dict()``.

        Raises
        ------
        KeyError: If slug is not registered.
        """
        if slug not in self._templates:
            available = ", ".join(sorted(self._templates.keys()))
            raise KeyError(f"Unknown template '{slug}'. Available: {available}")
        import copy
        return copy.deepcopy(self._templates[slug])

    def load_from_file(self, path: str | Path) -> dict[str, Any]:
        """Load a template from a YAML or JSON file.

        Automatically registers it under the filename stem as slug.
        """
        filepath = Path(path)
        if not filepath.exists():
            raise FileNotFoundError(f"Template file not found: {filepath}")

        text = filepath.read_text(encoding="utf-8")

        if filepath.suffix in (".yaml", ".yml"):
            try:
                import yaml
                data = yaml.safe_load(text)
            except ImportError:
                raise ImportError("PyYAML required for YAML templates: pip install pyyaml")
        elif filepath.suffix == ".json":
            data = json.loads(text)
        else:
            raise ValueError(f"Unsupported template format: {filepath.suffix} (use .yaml or .json)")

        if not isinstance(data, dict):
            raise ValueError(f"Template file must contain a dict, got {type(data).__name__}")

        slug = filepath.stem
        self.register(slug, data, author="file", domain=data.get("domain", ""))
        return data

    def load_from_directory(self, directory: str | Path) -> list[TemplateMetadata]:
        """Load all templates from a directory of YAML/JSON files.

        Returns metadata for all successfully loaded templates.
        """
        dirpath = Path(directory)
        if not dirpath.is_dir():
            raise NotADirectoryError(f"Not a directory: {dirpath}")

        loaded: list[TemplateMetadata] = []
        for filepath in sorted(dirpath.iterdir()):
            if filepath.suffix in (".yaml", ".yml", ".json") and filepath.is_file():
                try:
                    self.load_from_file(filepath)
                    slug = filepath.stem
                    if slug in self._metadata:
                        loaded.append(self._metadata[slug])
                except Exception as exc:
                    logger.warning("template_load_failed", extra={"path": str(filepath), "error": type(exc).__name__})

        return loaded

    def list_templates(
        self,
        *,
        domain: str | None = None,
        author: str | None = None,
    ) -> list[TemplateMetadata]:
        """List registered templates, optionally filtered by domain or author."""
        results = list(self._metadata.values())
        if domain:
            results = [m for m in results if m.domain == domain]
        if author:
            results = [m for m in results if m.author == author]
        return sorted(results, key=lambda m: m.slug)

    def search(self, query: str) -> list[TemplateMetadata]:
        """Search templates by name, description, domain, or tags."""
        query_lower = query.lower()
        results = []
        for meta in self._metadata.values():
            searchable = f"{meta.slug} {meta.name} {meta.description} {meta.domain} {' '.join(meta.tags)}".lower()
            if query_lower in searchable:
                results.append(meta)
        return sorted(results, key=lambda m: m.slug)

    def get_metadata(self, slug: str) -> TemplateMetadata | None:
        return self._metadata.get(slug)

    @property
    def count(self) -> int:
        return len(self._templates)

    def unregister(self, slug: str) -> bool:
        """Remove a template from the registry. Returns True if found."""
        if slug in self._templates:
            del self._templates[slug]
            self._metadata.pop(slug, None)
            return True
        return False


def _hash_template(data: dict[str, Any]) -> str:
    """Compute a content hash for a template dict."""
    canonical = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


# Global registry singleton
_global_registry: TemplateRegistry | None = None


def get_registry() -> TemplateRegistry:
    """Get the global template registry (lazy singleton)."""
    global _global_registry
    if _global_registry is None:
        _global_registry = TemplateRegistry()
    return _global_registry


__all__ = [
    "TemplateMetadata",
    "TemplateRegistry",
    "get_registry",
]
