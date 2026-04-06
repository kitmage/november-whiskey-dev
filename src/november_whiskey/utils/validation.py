from __future__ import annotations


def normalize_email(value: str) -> str:
    return value.strip().lower()


def validate_email(value: str) -> bool:
    email = normalize_email(value)
    return "@" in email and "." in email.split("@")[-1]
