from __future__ import annotations

from typing import Any, Protocol, TypeAlias, TypeVar

from pydantic import BaseModel
from pydantic_settings import BaseSettings

T = TypeVar("T")

SettingsT = TypeVar("SettingsT", bound=BaseSettings)
InstanceT = TypeVar("InstanceT")

ConfigData: TypeAlias = dict[str, Any]
InitKwargs: TypeAlias = dict[str, Any]
MergeableDict: TypeAlias = dict[str, Any]

ModulePath: TypeAlias = str
ClassName: TypeAlias = str
ModuleClassPair: TypeAlias = tuple[ModulePath, ClassName]
PositionalArgs: TypeAlias = tuple[Any, ...]

TypeKeyDependencyStore: TypeAlias = dict[type[Any], Any]
NameKeyDependencyStore: TypeAlias = dict[str, Any]
InstantiableConfig: TypeAlias = BaseModel | ConfigData
TargetClass: TypeAlias = type[Any]
CallableTarget: TypeAlias = type[Any]
InjectionCandidate: TypeAlias = tuple[bool, Any]


class ConfigSource(Protocol):
    def load(self) -> ConfigData: ...
