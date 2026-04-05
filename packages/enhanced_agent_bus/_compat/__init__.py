"""Compatibility shims for standalone PyPI installation.

Each module tries ``from src.core.shared.X import *`` (monorepo) first,
falls back to self-contained definitions (standalone wheel).
"""
