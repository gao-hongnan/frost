"""Configuration-driven object instantiation with Pydantic.

Combines Hydra-style object instantiation with Pydantic's settings management.
Automatically creates objects from YAML configs using the _target_ pattern.

Basic usage:
    from pydanticonf import BaseSettingsWithInstantiation, DynamicConfig

    class Settings(BaseSettingsWithInstantiation):
        model_config = SettingsConfigDict(yaml_file="config.yaml")
        database: DynamicConfig[Database]
        cache: DynamicConfig[Cache]

    settings = Settings()  # Objects are created automatically
"""

from __future__ import annotations

from frostbound.pydanticonf._instantiate import (
    clear_dependencies,
    get_registered_dependencies,
    instantiate,
    register_dependency,
)
from frostbound.pydanticonf.base import DynamicConfig
from frostbound.pydanticonf.factory import ConfigFactory
from frostbound.pydanticonf.settings import BaseSettingsWithInstantiation
from frostbound.pydanticonf.utils import deep_merge

__all__ = [
    "instantiate",
    "register_dependency",
    "clear_dependencies",
    "get_registered_dependencies",
    "DynamicConfig",
    "BaseSettingsWithInstantiation",
    "ConfigFactory",
    "deep_merge",
]
