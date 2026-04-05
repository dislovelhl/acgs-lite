"""Shim for src.core.shared.database.utils."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

try:
    from src.core.shared.database.utils import *  # noqa: F403
except ImportError:
    T = TypeVar("T")

    @dataclass
    class Pageable:
        page: int = 1
        size: int = 20
        sort_by: str = ""
        sort_order: str = "asc"

        @property
        def offset(self) -> int:
            return (self.page - 1) * self.size

    @dataclass
    class Page(Generic[T]):
        items: list[T] = field(default_factory=list)
        total: int = 0
        page: int = 1
        size: int = 20

        @property
        def total_pages(self) -> int:
            if self.size <= 0:
                return 0
            return (self.total + self.size - 1) // self.size

        @property
        def has_next(self) -> bool:
            return self.page < self.total_pages

        @property
        def has_prev(self) -> bool:
            return self.page > 1

    def paginate(items: list[Any], pageable: Pageable) -> Page[Any]:
        start = pageable.offset
        end = start + pageable.size
        return Page(
            items=items[start:end],
            total=len(items),
            page=pageable.page,
            size=pageable.size,
        )
