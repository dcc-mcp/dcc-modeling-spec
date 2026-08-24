"""Shared contract helpers for the host-neutral modeling specification tools."""

from __future__ import annotations

import math
from typing import Any


def failure(
    code: str,
    path: str,
    message: str,
    remediation: str,
    **details: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "code": code,
        "path": path,
        "message": message,
        "remediation": remediation,
    }
    item.update(details)
    return item


def is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )
