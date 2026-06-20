"""Shared request input bounds for event ingestion."""
from __future__ import annotations

import json
import math
from typing import Any

MAX_METADATA_KEYS = 100
MAX_METADATA_DEPTH = 4
MAX_METADATA_LIST_ITEMS = 50
MAX_METADATA_KEY_CHARS = 64
MAX_METADATA_STRING_CHARS = 2048
MAX_METADATA_SERIALIZED_BYTES = 16 * 1024


class InputBoundsError(ValueError):
    pass


def _check_primitive(value: Any, path: str) -> Any:
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InputBoundsError(f"{path} must be finite")
        return value
    if isinstance(value, str):
        if len(value) > MAX_METADATA_STRING_CHARS:
            raise InputBoundsError(f"{path} is too long")
        return value
    raise InputBoundsError(f"{path} must be a JSON primitive, list, or object")


def _sanitize_value(value: Any, *, path: str, depth: int) -> Any:
    if depth > MAX_METADATA_DEPTH:
        raise InputBoundsError(f"{path} is too deeply nested")
    if isinstance(value, dict):
        return _sanitize_object(value, path=path, depth=depth)
    if isinstance(value, list):
        if len(value) > MAX_METADATA_LIST_ITEMS:
            raise InputBoundsError(f"{path} has too many items")
        return [
            _sanitize_value(item, path=f"{path}[{idx}]", depth=depth + 1)
            for idx, item in enumerate(value)
        ]
    return _check_primitive(value, path)


def _sanitize_object(value: dict[Any, Any], *, path: str, depth: int) -> dict[str, Any]:
    if len(value) > MAX_METADATA_KEYS:
        raise InputBoundsError(f"{path} has too many entries")
    sanitized: dict[str, Any] = {}
    for raw_key, raw_item in value.items():
        if not isinstance(raw_key, str):
            raise InputBoundsError(f"{path} keys must be strings")
        key = raw_key.strip()
        if not key:
            raise InputBoundsError(f"{path} keys must not be blank")
        if len(key) > MAX_METADATA_KEY_CHARS:
            raise InputBoundsError(f"{path}.{key[:16]} key is too long")
        sanitized[key] = _sanitize_value(raw_item, path=f"{path}.{key}", depth=depth + 1)
    return sanitized


def sanitize_metadata(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InputBoundsError("metadata must be an object")
    sanitized = _sanitize_object(value, path="metadata", depth=0)
    encoded = json.dumps(sanitized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_METADATA_SERIALIZED_BYTES:
        raise InputBoundsError("metadata is too large")
    return sanitized
