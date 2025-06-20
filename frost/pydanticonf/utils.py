"""Utility functions for pydanticonf."""

from __future__ import annotations

from frost.pydanticonf.types import MergeableDict


def deep_merge(base: MergeableDict, override: MergeableDict) -> MergeableDict:
    """Recursively merge two dictionaries with override precedence.

    Args:
        base: Base dictionary (lower precedence)
        override: Override dictionary (higher precedence)

    Returns:
        New merged dictionary without modifying inputs

    Example:
        base = {"a": 1, "b": {"x": 10, "y": 20}}
        override = {"b": {"y": 25, "z": 30}}
        result = deep_merge(base, override)
        # {'a': 1, 'b': {'x': 10, 'y': 25, 'z': 30}}
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result
