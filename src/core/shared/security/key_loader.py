from __future__ import annotations

import os

from src.core.shared.errors.exceptions import ConfigurationError

_ALLOWED_KEY_DIRS: tuple[str, ...] = (
    "/etc/acgs2/keys",
    "/run/secrets",
    "/var/run/secrets",
    os.path.expanduser("~/.acgs2/keys"),
)
_EXTRA_KEY_DIRS = tuple(
    d.strip() for d in (os.getenv("ACGS2_KEY_DIRS") or "").split(os.pathsep) if d.strip()
)
_ALL_KEY_DIRS = _ALLOWED_KEY_DIRS + _EXTRA_KEY_DIRS


def load_key_material(raw_value: str, error_code: str = "KEY_FILE_READ_FAILED") -> str:
    """Load key material from a raw string or @-prefixed file path.

    If raw_value starts with '@', read the file at the path after '@'.
    Otherwise return raw_value as-is.
    """
    if raw_value.startswith("@"):
        file_path = raw_value[1:].strip()
        if not file_path:
            return ""
        resolved_path = os.path.realpath(file_path)
        if not any(resolved_path.startswith(allowed_dir) for allowed_dir in _ALL_KEY_DIRS):
            raise ConfigurationError(
                message=(
                    f"Key file path {resolved_path} is not in an allowed directory. "
                    f"Allowed: {', '.join(_ALL_KEY_DIRS)}"
                ),
                error_code=error_code,
            )
        try:
            with open(os.fspath(file_path), encoding="utf-8") as file_handle:
                return file_handle.read()
        except OSError as error:
            raise ConfigurationError(
                message=f"Failed loading key from file: {file_path}",
                error_code=error_code,
            ) from error
    return raw_value
