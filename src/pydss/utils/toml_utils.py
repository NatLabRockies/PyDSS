"""Compatibility helpers for reading and writing TOML."""

from enum import Enum
from pathlib import Path
from typing import Any, BinaryIO, TextIO

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib

import tomli_w


def _prepare_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {
            _prepare_value(key): _prepare_value(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return ["None" if item is None else _prepare_value(item) for item in value]
    return value


def load(source: str | Path | BinaryIO | TextIO) -> dict[str, Any]:
    """Load TOML from a path or an open file."""
    if isinstance(source, (str, Path)):
        with open(source, "rb") as file_obj:
            return tomllib.load(file_obj)
    content = source.read()
    if isinstance(content, str):
        return tomllib.loads(content)
    return tomllib.loads(content.decode())


def loads(content: str | bytes) -> dict[str, Any]:
    """Load TOML from a string or bytes."""
    if isinstance(content, bytes):
        content = content.decode()
    return tomllib.loads(content)


def dump(data: dict[str, Any], destination: str | Path | BinaryIO | TextIO) -> None:
    """Write TOML to a path or an open file."""
    prepared = _prepare_value(data)
    if isinstance(destination, (str, Path)):
        with open(destination, "wb") as file_obj:
            tomli_w.dump(prepared, file_obj)
        return
    tomli_w.dump(prepared, destination)
