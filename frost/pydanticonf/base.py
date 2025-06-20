from __future__ import annotations

from typing import Any, ClassVar, Generic, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, model_validator

from frost.pydanticonf.types import InitKwargs, InstanceT, ModuleClassPair, PositionalArgs


class DynamicConfig(BaseModel, Generic[InstanceT]):
    """Type-safe configuration for dynamic object instantiation.

    Pydantic model that specifies how to instantiate objects using the _target_ pattern.
    Supports automatic target inference, positional args, partial instantiation, and recursion.

    Example:
        class DatabaseConfig(DynamicConfig[Database]):
            host: str = "localhost"
            port: int = 5432

        config = DatabaseConfig(_target_="myapp.Database")
    """

    model_config = ConfigDict(
        populate_by_name=True,
        validate_default=True,
        extra="allow",  # Allow additional fields for flexible configuration
        arbitrary_types_allowed=True,  # Support complex types in configuration
        str_strip_whitespace=True,  # Clean string inputs
    )

    target_: str = Field(
        ...,
        alias="_target_",
        description="Fully qualified class/function path (e.g., 'myapp.models.Database')",
        min_length=1,
    )
    args_: PositionalArgs | None = Field(
        default=None, alias="_args_", description="Positional arguments to pass to the target constructor"
    )
    partial_: bool = Field(
        default=False, alias="_partial_", description="Return functools.partial instead of calling the target"
    )
    recursive_: bool = Field(
        default=True, alias="_recursive_", description="Recursively instantiate nested DynamicConfig objects"
    )

    _exclude_from_kwargs: ClassVar[frozenset[str]] = frozenset({"target_", "args_", "partial_", "recursive_"})

    @model_validator(mode="before")
    @classmethod
    def _auto_infer_target(cls, values: Any) -> Any:
        """Automatically infer _target_ from generic type parameter when possible.

        Tries to set _target_ based on the generic type argument. Falls back to
        requiring explicit _target_ if inference fails.
        """
        if not isinstance(values, dict):
            return values

        if "_target_" in values or "target_" in values:
            return values

        try:
            orig_bases = getattr(cls, "__orig_bases__", ())
            for base in orig_bases:
                origin = get_origin(base)
                if origin is DynamicConfig:
                    args = get_args(base)
                    if args and len(args) == 1:
                        target_type = args[0]
                        if isinstance(target_type, type):
                            module = getattr(target_type, "__module__", None)
                            name = getattr(target_type, "__qualname__", None)
                            if module and name:
                                values["_target_"] = f"{module}.{name}"
                                break
        except Exception:
            pass

        return values

    def get_module_and_class_name(self) -> ModuleClassPair:
        if not self.target_ or "." not in self.target_:
            raise ValueError(f"Invalid target format: {self.target_}. Expected 'module.ClassName'")

        module_path, class_name = self.target_.rsplit(".", 1)
        if not module_path or not class_name:
            raise ValueError(f"Invalid target format: {self.target_}. Expected 'module.ClassName'")

        return module_path, class_name

    def get_init_kwargs(self) -> InitKwargs:
        return {
            field_name: field_value for field_name, field_value in self if field_name not in self._exclude_from_kwargs
        }
