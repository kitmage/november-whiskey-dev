from __future__ import annotations

import os
from collections.abc import Iterable

SENSITIVE_ENV_TOKENS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "KEY",
    "API",
    "AUTH",
    "CREDENTIAL",
)


def _iter_sensitive_env_values(env_items: Iterable[tuple[str, str]]) -> list[str]:
    values: list[str] = []
    for key, value in env_items:
        if not value:
            continue
        upper_key = key.upper()
        if any(token in upper_key for token in SENSITIVE_ENV_TOKENS):
            values.append(value)
    return sorted(values, key=len, reverse=True)


def sanitize_error_text(message: str) -> str:
    sanitized = message
    for value in _iter_sensitive_env_values(os.environ.items()):
        sanitized = sanitized.replace(value, "[REDACTED]")
    return sanitized
