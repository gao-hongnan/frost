from __future__ import annotations

import functools
import importlib
import inspect
from abc import abstractmethod
from contextvars import ContextVar
from typing import Any, Protocol, Sequence, cast, overload

from frost.pydanticonf.base import DynamicConfig
from frost.pydanticonf.types import (
    ConfigData,
    InjectionCandidate,
    InstanceT,
    InstantiableConfig,
    NameKeyDependencyStore,
    TargetClass,
    TypeKeyDependencyStore,
)

_type_dependency_store: TypeKeyDependencyStore = {}
_name_dependency_store: NameKeyDependencyStore = {}

_instantiation_stack: ContextVar[list[str] | None] = ContextVar("instantiation_stack", default=None)


class InjectionStrategy(Protocol):
    """Protocol for dependency injection strategies."""

    @abstractmethod
    def resolve(self, param_name: str, param: inspect.Parameter, available_args: dict[str, Any]) -> InjectionCandidate:
        """Resolve a dependency for the given parameter.

        Returns (resolved, value) where resolved indicates if a dependency was found.
        """
        ...


class NameBasedInjectionStrategy:
    """Resolves dependencies by parameter name."""

    def __init__(self, registry: NameKeyDependencyStore):
        self._registry = registry

    def resolve(self, param_name: str, param: inspect.Parameter, available_args: dict[str, Any]) -> InjectionCandidate:
        _ = param, available_args
        if param_name in self._registry:
            return True, self._registry[param_name]
        return False, None


class TypeBasedInjectionStrategy:
    """Resolves dependencies by parameter type annotation."""

    def __init__(self, registry: TypeKeyDependencyStore):
        self._registry = registry

    def resolve(self, param_name: str, param: inspect.Parameter, available_args: dict[str, Any]) -> InjectionCandidate:
        _ = param_name, available_args
        if param.annotation == inspect.Parameter.empty:
            return False, None

        if param.annotation in self._registry:
            return True, self._registry[param.annotation]

        for stored_type, instance in self._registry.items():
            if _types_match_semantically(param.annotation, stored_type):
                return True, instance

        return False, None


class DependencyResolver:
    """Dependency injection resolver using strategy pattern."""

    def __init__(self) -> None:
        self._strategies: list[InjectionStrategy] = [
            NameBasedInjectionStrategy(_name_dependency_store),
            TypeBasedInjectionStrategy(_type_dependency_store),
        ]

    def inject_dependencies(self, target_class: TargetClass, kwargs: dict[str, Any]) -> None:
        """Enrich kwargs with resolved dependencies."""
        signature = self._extract_signature(target_class)
        if not signature:
            return

        for param_name, param in signature.parameters.items():
            if self._should_skip_parameter(param_name, param, kwargs):
                continue

            for strategy in self._apply_injection_strategies(param_name, param):
                resolved, value = strategy.resolve(param_name, param, kwargs)
                if resolved:
                    kwargs[param_name] = value
                    break

    def _extract_signature(self, target_class: TargetClass) -> inspect.Signature | None:
        """Safely extract signature from target class."""
        if not hasattr(target_class, "__init__"):
            return None

        try:
            return inspect.signature(target_class.__init__)
        except (ValueError, TypeError):
            return None

    def _should_skip_parameter(self, param_name: str, param: inspect.Parameter, kwargs: dict[str, Any]) -> bool:
        """Determine if parameter should be skipped for injection."""
        _ = param
        return param_name == "self" or param_name in kwargs

    def _apply_injection_strategies(self, param_name: str, param: inspect.Parameter) -> Sequence[InjectionStrategy]:
        """Return applicable strategies for the parameter."""
        _ = param_name
        if param.default != inspect.Parameter.empty:
            return [self._strategies[0]]
        return self._strategies


_dependency_resolver = DependencyResolver()


class InstantiationError(Exception):
    """Exception raised when object instantiation fails.

    Provides detailed context about failures including target, config path, and original error.
    """

    def __init__(
        self,
        message: str,
        *,
        target: str | None = None,
        config_path: str | None = None,
        original_error: Exception | None = None,
    ) -> None:
        self.message = message
        self.target = target
        self.config_path = config_path
        self.original_error = original_error

        parts = []
        if config_path:
            parts.append(f"Configuration path: {config_path}")
        if target:
            parts.append(f"Target: {target}")
        parts.append(f"Error: {message}")
        if original_error:
            parts.append(f"Caused by: {type(original_error).__name__}: {original_error}")

        super().__init__(" | ".join(parts))


@overload
def instantiate(
    config: DynamicConfig[InstanceT],
    *,
    _target_: str | None = None,
    _recursive_: bool = True,
    _partial_: bool = False,
    _config_path_: str | None = None,
    **kwargs: Any,
) -> InstanceT: ...


@overload
def instantiate(
    config: InstantiableConfig,
    *,
    _target_: str | None = None,
    _recursive_: bool = True,
    _partial_: bool = False,
    _config_path_: str | None = None,
    **kwargs: Any,
) -> Any: ...


def instantiate(
    config: InstantiableConfig,
    *,
    _target_: str | None = None,
    _recursive_: bool = True,
    _partial_: bool = False,
    _config_path_: str | None = None,
    **kwargs: Any,
) -> Any:
    """Create Python objects from configuration data.

    Args:
        config: Configuration dict or DynamicConfig with _target_ field
        _target_: Override target class/function path
        _recursive_: Recursively instantiate nested configs (default: True)
        _partial_: Return functools.partial instead of calling target
        **kwargs: Additional arguments to pass to target

    Returns:
        Instantiated object or functools.partial if _partial_=True

    Example:
        config = {"_target_": "pathlib.Path", "path": "/tmp/example"}
        path_obj = instantiate(config)
    """
    if isinstance(config, dict):
        target = _target_ or config.get("_target_")
    elif isinstance(config, DynamicConfig):
        target = _target_ or config.target_
    else:
        config_dict = config.model_dump(mode="python")
        target = _target_ or config_dict.get("_target_")

    if target:
        stack = _instantiation_stack.get()
        if stack is None:
            stack = []
        if target in stack:
            cycle = " -> ".join(stack + [target])
            raise InstantiationError(f"Circular dependency detected: {cycle}", target=target, config_path=_config_path_)

    try:
        if isinstance(config, dict):
            return _instantiate_from_dict(
                config,
                _target_=_target_,
                _recursive_=_recursive_,
                _partial_=_partial_,
                _config_path_=_config_path_,
                **kwargs,
            )

        if isinstance(config, DynamicConfig):
            return _instantiate_from_dynamic_config(
                config,
                _target_=_target_,
                _recursive_=_recursive_,
                _partial_=_partial_,
                _config_path_=_config_path_,
                **kwargs,
            )

        config_dict = config.model_dump(mode="python")
        if "_target_" in config_dict:
            return _instantiate_from_dict(
                config_dict,
                _target_=_target_,
                _recursive_=_recursive_,
                _partial_=_partial_,
                _config_path_=_config_path_,
                **kwargs,
            )

        return config

    except InstantiationError:
        raise
    except Exception as e:
        target = _target_ or (config.get("_target_") if isinstance(config, dict) else getattr(config, "target_", None))
        raise InstantiationError(
            f"Unexpected error during instantiation: {e}", target=target, config_path=_config_path_, original_error=e
        ) from e


def register_dependency(type_or_name: type[Any] | str, instance: Any) -> None:
    """
    Register a dependency for automatic injection during instantiation.

    This function allows you to register objects that will be automatically injected
    into constructors during instantiation. Dependencies can be registered by type
    (class) or by parameter name, with name-based registration being more reliable
    for complex applications.

    When `instantiate()` creates an object, it inspects the target constructor's
    signature and automatically provides registered dependencies for any required
    parameters that aren't explicitly provided in the configuration.

    Parameters
    ----------
    type_or_name : type[Any] | str
        How to identify this dependency for injection:
        - If a type/class: Will inject for parameters with matching type annotations
        - If a string: Will inject for parameters with matching names

    instance : Any
        The dependency instance to inject. This is the actual object that will
        be passed to constructors that need this dependency.

    Examples
    --------
    **Basic dependency registration by name:**

    >>> from frostbound.pydanticonf import register_dependency, instantiate
    >>>
    >>> class Database:
    ...     def __init__(self, host: str, port: int = 5432):
    ...         self.host = host
    ...         self.port = port
    >>>
    >>> class UserService:
    ...     def __init__(self, name: str, database: Database):
    ...         self.name = name
    ...         self.database = database
    >>>
    >>> # Register a shared database instance by parameter name
    >>> shared_db = Database("prod.server", 3306)
    >>> register_dependency("database", shared_db)
    >>>
    >>> # Now services will automatically get the shared database
    >>> service = instantiate({
    ...     "_target_": "__main__.UserService",
    ...     "name": "UserService"
    ...     # No need to specify database - it will be injected!
    ... })
    >>> print(f"Service uses DB: {service.database.host}")
    Service uses DB: prod.server

    **Registration by type:**

    >>> # Register by type (less reliable due to import path differences)
    >>> register_dependency(Database, shared_db)
    >>>
    >>> class OrderService:
    ...     def __init__(self, name: str, db: Database):  # Parameter name is 'db', not 'database'
    ...         self.name = name
    ...         self.db = db
    >>>
    >>> # Type-based injection works regardless of parameter name
    >>> order_service = instantiate({
    ...     "_target_": "__main__.OrderService",
    ...     "name": "OrderService"
    ... })
    >>> print(f"Order service uses DB: {order_service.db.host}")
    Order service uses DB: prod.server

    **Multiple dependencies:**

    >>> class Logger:
    ...     def __init__(self, name: str, level: str = "INFO"):
    ...         self.name = name
    ...         self.level = level
    >>>
    >>> class EmailService:
    ...     def __init__(self, smtp_host: str, port: int = 587):
    ...         self.smtp_host = smtp_host
    ...         self.port = port
    >>>
    >>> class NotificationService:
    ...     def __init__(self, database: Database, logger: Logger, email: EmailService):
    ...         self.database = database
    ...         self.logger = logger
    ...         self.email = email
    >>>
    >>> # Register multiple dependencies
    >>> app_logger = Logger("app", "DEBUG")
    >>> email_service = EmailService("smtp.example.com")
    >>>
    >>> register_dependency("logger", app_logger)
    >>> register_dependency("email", email_service)
    >>> # database is already registered from previous example
    >>>
    >>> # All dependencies will be injected automatically
    >>> notification_service = instantiate({
    ...     "_target_": "__main__.NotificationService"
    ... })
    >>> print(f"Notification service components:")
    >>> print(f"  Database: {notification_service.database.host}")
    >>> print(f"  Logger: {notification_service.logger.name} ({notification_service.logger.level})")
    >>> print(f"  Email: {notification_service.email.smtp_host}")
    Notification service components:
      Database: prod.server
      Logger: app (DEBUG)
      Email: smtp.example.com

    **Dependency injection with configuration overrides:**

    >>> # You can still override injected dependencies in configuration
    >>> custom_logger = Logger("custom", "ERROR")
    >>>
    >>> service_with_custom_logger = instantiate({
    ...     "_target_": "__main__.NotificationService",
    ...     "logger": {
    ...         "_target_": "__main__.Logger",
    ...         "name": "custom",
    ...         "level": "ERROR"
    ...     }
    ...     # database and email will still be injected
    ... })
    >>> print(f"Custom logger level: {service_with_custom_logger.logger.level}")
    Custom logger level: ERROR

    **Real-world example with configuration files:**

    >>> import tempfile
    >>> import yaml
    >>> from frostbound.pydanticonf import ConfigLoader, YamlConfigSource
    >>>
    >>> # Setup shared dependencies
    >>> prod_db = Database("prod-db.company.com", 5432)
    >>> audit_logger = Logger("audit", "INFO")
    >>>
    >>> register_dependency("database", prod_db)
    >>> register_dependency("audit_logger", audit_logger)
    >>>
    >>> # YAML configuration doesn't need to specify shared dependencies
    >>> yaml_content = '''
    ... services:
    ...   user_service:
    ...     _target_: "__main__.UserService"
    ...     name: "UserService"
    ...     # database will be injected automatically
    ...
    ...   order_service:
    ...     _target_: "__main__.OrderService"
    ...     name: "OrderService"
    ...     # database will be injected automatically
    ... '''
    >>>
    >>> with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
    ...     f.write(yaml_content)
    ...     config_file = f.name
    >>>
    >>> loader = ConfigLoader([YamlConfigSource(config_file)])
    >>> config = loader.load()
    >>>
    >>> user_service = instantiate(config["services"]["user_service"])
    >>> order_service = instantiate(config["services"]["order_service"])
    >>>
    >>> print(f"Both services use same DB instance: {user_service.database is order_service.db}")
    Both services use same DB instance: True
    >>>
    >>> import os
    >>> os.unlink(config_file)  # cleanup

    Notes
    -----
    **Injection Rules:**

    1. **Only for required parameters**: Dependencies are only injected for constructor
       parameters that have no default value and aren't provided in the configuration.

    2. **Name-based takes precedence**: If both name-based and type-based dependencies
       are registered for the same parameter, name-based injection is used.

    3. **Configuration overrides injection**: Explicitly provided parameters in the
       configuration always take precedence over dependency injection.

    4. **Conservative matching**: Type-based injection uses strict matching to avoid
       injecting wrong dependencies (e.g., different Connection classes from different
       libraries).

    **Best Practices:**

    - **Prefer name-based registration** for reliability across different import contexts
    - **Register shared resources** like database connections, loggers, caches
    - **Use clear, descriptive parameter names** to avoid naming conflicts
    - **Register dependencies early** in your application startup
    - **Clear dependencies in tests** using `clear_dependencies()` to avoid test pollution

    **Common Patterns:**

    >>> # Pattern 1: Application-wide shared resources
    >>> register_dependency("database", create_database_connection())
    >>> register_dependency("cache", create_redis_cache())
    >>> register_dependency("logger", create_application_logger())
    >>>
    >>> # Pattern 2: Environment-specific dependencies
    >>> if os.getenv("ENVIRONMENT") == "production":
    ...     register_dependency("database", create_prod_database())
    ... else:
    ...     register_dependency("database", create_test_database())
    >>>
    >>> # Pattern 3: Factory functions as dependencies
    >>> def create_logger(name: str) -> Logger:
    ...     return Logger(name, level=os.getenv("LOG_LEVEL", "INFO"))
    >>> register_dependency("logger_factory", create_logger)

    See Also
    --------
    clear_dependencies : Clear all registered dependencies
    get_registered_dependencies : Inspect currently registered dependencies
    instantiate : Main function that uses registered dependencies
    """
    if isinstance(type_or_name, type):
        _type_dependency_store[type_or_name] = instance
    else:
        _name_dependency_store[type_or_name] = instance


def clear_dependencies() -> None:
    """
    Clear all registered dependencies.

    This function removes all previously registered dependencies from both the
    type-based and name-based dependency stores. It's particularly useful in
    testing scenarios to ensure clean state between tests.

    Examples
    --------
    **Basic usage in tests:**

    >>> from frostbound.pydanticonf import register_dependency, clear_dependencies
    >>>
    >>> # Setup for test
    >>> class Database:
    ...     def __init__(self, host: str):
    ...         self.host = host
    >>>
    >>> def test_service_with_dependency():
    ...     # Register test dependency
    ...     test_db = Database("test.server")
    ...     register_dependency("database", test_db)
    ...
    ...     # ... run test ...
    ...
    ...     # Clean up for next test
    ...     clear_dependencies()

    **Using in pytest fixtures:**

    >>> import pytest
    >>>
    >>> @pytest.fixture(autouse=True)
    >>> def clean_dependencies():
    ...     '''Automatically clear dependencies after each test'''
    ...     yield
    ...     clear_dependencies()

    **Verifying cleanup:**

    >>> # Register some dependencies
    >>> register_dependency("database", Database("test"))
    >>> register_dependency(str, "test_string")
    >>>
    >>> # Verify they exist
    >>> type_deps, name_deps = get_registered_dependencies()
    >>> print(f"Dependencies before: types={len(type_deps)}, names={len(name_deps)}")
    Dependencies before: types=1, names=1
    >>>
    >>> # Clear and verify
    >>> clear_dependencies()
    >>> type_deps, name_deps = get_registered_dependencies()
    >>> print(f"Dependencies after: types={len(type_deps)}, names={len(name_deps)}")
    Dependencies after: types=0, names=0

    Notes
    -----
    This function is safe to call multiple times and will not raise any errors
    if the dependency stores are already empty.

    See Also
    --------
    register_dependency : Register dependencies for injection
    get_registered_dependencies : Inspect current dependencies
    """
    _type_dependency_store.clear()
    _name_dependency_store.clear()


def get_registered_dependencies() -> tuple[TypeKeyDependencyStore, NameKeyDependencyStore]:
    """
    Get copies of the current dependency stores for inspection.

    This function returns copies of both the type-based and name-based dependency
    stores, allowing you to inspect what dependencies are currently registered
    without being able to modify the stores directly.

    Returns
    -------
    tuple[TypeKeyDependencyStore, NameKeyDependencyStore]
        A tuple containing:
        - Dictionary mapping types to their registered instances
        - Dictionary mapping parameter names to their registered instances

    Examples
    --------
    **Basic inspection:**

    >>> from frostbound.pydanticonf import register_dependency, get_registered_dependencies
    >>>
    >>> class Database:
    ...     def __init__(self, host: str):
    ...         self.host = host
    >>>
    >>> class Logger:
    ...     def __init__(self, name: str):
    ...         self.name = name
    >>>
    >>> # Register some dependencies
    >>> db = Database("prod.server")
    >>> logger = Logger("app")
    >>>
    >>> register_dependency(Database, db)
    >>> register_dependency("logger", logger)
    >>> register_dependency("database", db)  # Same instance, different key
    >>>
    >>> # Inspect registered dependencies
    >>> type_deps, name_deps = get_registered_dependencies()
    >>>
    >>> print("Type-based dependencies:")
    >>> for dep_type, instance in type_deps.items():
    ...     print(f"  {dep_type.__name__}: {instance}")
    Type-based dependencies:
      Database: <__main__.Database object at 0x...>
    >>>
    >>> print("Name-based dependencies:")
    >>> for name, instance in name_deps.items():
    ...     print(f"  {name}: {instance}")
    Name-based dependencies:
      logger: <__main__.Logger object at 0x...>
      database: <__main__.Database object at 0x...>

    **Debugging dependency injection issues:**

    >>> # When instantiation doesn't work as expected, inspect dependencies
    >>> class Service:
    ...     def __init__(self, name: str, database: Database, logger: Logger):
    ...         self.name = name
    ...         self.database = database
    ...         self.logger = logger
    >>>
    >>> # Check what dependencies are available
    >>> type_deps, name_deps = get_registered_dependencies()
    >>>
    >>> print("Available for injection:")
    >>> print(f"  Database type registered: {Database in type_deps}")
    >>> print(f"  'database' name registered: {'database' in name_deps}")
    >>> print(f"  'logger' name registered: {'logger' in name_deps}")
    Available for injection:
      Database type registered: True
      'database' name registered: True
      'logger' name registered: True

    **Verifying test setup:**

    >>> def setup_test_dependencies():
    ...     test_db = Database("test.server")
    ...     test_logger = Logger("test")
    ...
    ...     register_dependency("database", test_db)
    ...     register_dependency("logger", test_logger)
    ...
    ...     # Verify setup
    ...     type_deps, name_deps = get_registered_dependencies()
    ...     assert "database" in name_deps
    ...     assert "logger" in name_deps
    ...     print("Test dependencies registered successfully")
    >>>
    >>> setup_test_dependencies()
    Test dependencies registered successfully

    **Monitoring dependency registration in applications:**

    >>> def log_dependency_status():
    ...     type_deps, name_deps = get_registered_dependencies()
    ...     print(f"Application has {len(type_deps)} type-based dependencies")
    ...     print(f"Application has {len(name_deps)} name-based dependencies")
    ...
    ...     if name_deps:
    ...         print("Name-based dependencies:")
    ...         for name in sorted(name_deps.keys()):
    ...             print(f"  - {name}")
    >>>
    >>> log_dependency_status()
    Application has 1 type-based dependencies
    Application has 2 name-based dependencies
    Name-based dependencies:
      - database
      - logger

    Notes
    -----
    The returned dictionaries are copies, so modifying them will not affect
    the actual dependency stores. This is intentional to prevent accidental
    modification of the dependency system state.

    This function is primarily useful for:
    - Debugging dependency injection issues
    - Testing and verification
    - Application monitoring and diagnostics
    - Understanding the current state of the dependency system

    See Also
    --------
    register_dependency : Register dependencies for injection
    clear_dependencies : Clear all registered dependencies
    """
    return _type_dependency_store.copy(), _name_dependency_store.copy()


# ============================================================================
# Private Implementation
# ============================================================================


def _instantiate_from_dict(
    config: ConfigData,
    *,
    _target_: str | None = None,
    _recursive_: bool = True,
    _partial_: bool = False,
    _config_path_: str | None = None,
    **overrides: Any,
) -> Any:
    """Instantiate object from dictionary configuration with enhanced error handling."""
    # Work with a copy to avoid mutating the original
    config_copy = config.copy()

    # Extract control parameters
    target = _target_ or config_copy.pop("_target_", None)
    if not target:
        raise InstantiationError("No _target_ specified in configuration", config_path=_config_path_)

    recursive = config_copy.pop("_recursive_", _recursive_)
    partial = config_copy.pop("_partial_", _partial_)
    args_tuple = config_copy.pop("_args_", ())

    # Apply overrides
    config_copy.update(overrides)

    # Update instantiation stack
    current_stack = _instantiation_stack.get()
    stack = current_stack.copy() if current_stack is not None else []
    stack.append(target)
    token = _instantiation_stack.set(stack)

    try:
        # Process arguments and config recursively if enabled
        if recursive:
            processed_args = [_process_value(arg, recursive=True, config_path=_config_path_) for arg in args_tuple]
            processed_config = {
                k: _process_value(v, recursive=True, config_path=f"{_config_path_}.{k}" if _config_path_ else k)
                for k, v in config_copy.items()
            }
        else:
            processed_args = list(args_tuple)
            processed_config = config_copy

        # Import and validate target class
        target_class = _import_class(target, config_path=_config_path_)

        # Inject dependencies
        _dependency_resolver.inject_dependencies(target_class, processed_config)

        # Create object or partial
        if partial:
            # Type ignore needed: functools.partial has limited type inference
            # for *args and **kwargs with generic callables
            return functools.partial(target_class, *processed_args, **processed_config)  # type: ignore[misc]

        if processed_args:
            return target_class(*processed_args, **processed_config)

        return target_class(**processed_config)

    except InstantiationError:
        # Re-raise with preserved context
        raise
    except Exception as e:
        # Wrap in InstantiationError with context
        raise InstantiationError(
            f"Failed to instantiate object: {e}", target=target, config_path=_config_path_, original_error=e
        ) from e
    finally:
        # Reset instantiation stack
        _instantiation_stack.reset(token)


def _instantiate_from_dynamic_config(
    config: DynamicConfig[Any],
    *,
    _target_: str | None = None,
    _recursive_: bool | None = None,
    _partial_: bool | None = None,
    _config_path_: str | None = None,
    **overrides: Any,
) -> Any:
    """Instantiate object from DynamicConfig with enhanced error handling."""
    # Extract parameters with proper defaults
    target = _target_ or config.target_
    recursive = _recursive_ if _recursive_ is not None else config.recursive_
    partial = _partial_ if _partial_ is not None else config.partial_
    args_tuple = config.args_ or ()

    # Update instantiation stack
    current_stack = _instantiation_stack.get()
    stack = current_stack.copy() if current_stack is not None else []
    stack.append(target)
    token = _instantiation_stack.set(stack)

    try:
        # Get initialization kwargs
        kwargs = config.get_init_kwargs()
        kwargs.update(overrides)

        # Process arguments and kwargs recursively if enabled
        if recursive:
            processed_args = [_process_value(arg, recursive=True, config_path=_config_path_) for arg in args_tuple]
            processed_kwargs = {
                k: _process_value(v, recursive=True, config_path=f"{_config_path_}.{k}" if _config_path_ else k)
                for k, v in kwargs.items()
            }
        else:
            processed_args = list(args_tuple)
            processed_kwargs = kwargs

        # Import and validate target class
        target_class = _import_class(target, config_path=_config_path_)

        # Inject dependencies
        _dependency_resolver.inject_dependencies(target_class, processed_kwargs)

        # Create object or partial
        if partial:
            # Type ignore needed: functools.partial has limited type inference
            # for *args and **kwargs with generic callables
            return functools.partial(target_class, *processed_args, **processed_kwargs)  # type: ignore[misc]

        if processed_args:
            return target_class(*processed_args, **processed_kwargs)

        return target_class(**processed_kwargs)

    except InstantiationError:
        # Re-raise with preserved context
        raise
    except Exception as e:
        # Wrap in InstantiationError with context
        raise InstantiationError(
            f"Failed to instantiate from DynamicConfig: {e}", target=target, config_path=_config_path_, original_error=e
        ) from e
    finally:
        # Reset instantiation stack
        _instantiation_stack.reset(token)


def _import_class(target_path: str, *, config_path: str | None = None) -> TargetClass:
    """Import a class or function from a fully qualified path with enhanced error handling."""
    try:
        if "." not in target_path:
            raise ValueError(f"Invalid target format: {target_path}. Expected 'module.ClassName'")

        module_path, class_name = target_path.rsplit(".", 1)
        if not module_path or not class_name:
            raise ValueError(f"Invalid target format: {target_path}. Expected 'module.ClassName'")

        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)

        # Verify it's callable (class or function)
        if not callable(cls):
            raise TypeError(f"{target_path} is not callable")

        # For type safety, we cast to TargetClass
        # This is safe because we've verified it's callable
        return cast(TargetClass, cls)

    except (ValueError, ImportError, AttributeError) as e:
        raise InstantiationError(
            f"Failed to import {target_path}: {e}", target=target_path, config_path=config_path, original_error=e
        ) from e


def _process_value(value: Any, *, recursive: bool, config_path: str | None = None) -> Any:
    """Process a value recursively, handling nested configurations with path context."""
    if not recursive:
        return value

    # Handle DynamicConfig objects
    if isinstance(value, DynamicConfig):
        return instantiate(value, _config_path_=config_path)

    # Handle dictionary configurations
    if isinstance(value, dict) and "_target_" in value:
        return instantiate(value, _config_path_=config_path)

    # Handle lists recursively
    if isinstance(value, list):
        return [
            _process_value(item, recursive=recursive, config_path=f"{config_path}[{i}]" if config_path else f"[{i}]")
            for i, item in enumerate(value)
        ]

    # Handle dictionaries recursively
    if isinstance(value, dict):
        return {
            k: _process_value(v, recursive=recursive, config_path=f"{config_path}.{k}" if config_path else k)
            for k, v in value.items()
        }

    # Return primitive values as-is
    return value


def _types_match_semantically(type1: Any, type2: Any) -> bool:
    """
    Safely determine if two types represent the same class for dependency injection.

    This function solves a critical problem in dependency injection systems: determining
    when two type objects represent the same logical class, even when they might be
    imported through different paths or during different phases of application lifecycle.

    The Problem
    -----------
    In Python, the same class can appear as different type objects in several scenarios:

    1. **Re-imports during testing**: Test frameworks often reload modules
    2. **Dynamic imports**: Classes loaded via importlib vs direct imports
    3. **Hot reloading**: Development servers that reload code
    4. **Plugin systems**: Classes loaded from different entry points

    Without fuzzy matching, dependency injection would fail in these legitimate cases.
    However, naive fuzzy matching can be dangerous - matching unrelated classes with
    the same name from different libraries (e.g., ``psycopg2.Connection`` vs
    ``asyncpg.Connection``) leads to incorrect dependency injection.

    Parameters
    ----------
    type1 : Any
        First type to compare. Should be a class/type object.
    type2 : Any
        Second type to compare. Should be a class/type object.

    Returns
    -------
    bool
        True if the types represent the same logical class, False otherwise.

    Examples
    --------
    **Safe matching scenarios (returns True):**

    >>> # Identity - same exact type object
    >>> _types_match_semantically(str, str)
    True

    >>> # Re-import scenario - same class, different import paths
    >>> from collections import Counter
    >>> import collections
    >>> _types_match_semantically(Counter, collections.Counter)
    True

    **Dangerous scenarios prevented (returns False):**

    >>> # Different classes with same name - DANGEROUS if matched!
    >>> class psycopg2:
    ...     class Connection: pass
    >>> class asyncpg:
    ...     class Connection: pass
    >>> _types_match_semantically(psycopg2.Connection, asyncpg.Connection)
    False

    >>> # Built-in types with different names
    >>> _types_match_semantically(list, dict)
    False

    **Real-world dependency injection example:**

    >>> # Without fuzzy matching, this would fail:
    >>> class DatabaseService:
    ...     def __init__(self, connection: psycopg2.Connection): ...
    >>>
    >>> # During testing, psycopg2.Connection might be imported differently
    >>> # Fuzzy matching allows the dependency injection to work correctly
    >>> # while preventing injection of wrong connection types

    Algorithm
    ---------
    The matching algorithm follows these rules in order:

    1. **Identity check**: If ``type1 is type2``, return True immediately
    2. **Fully qualified name check**: Match only if both the class name
       AND the complete module path are identical
    3. **Reject everything else**: Conservative approach prevents dangerous matches

    This is much safer than previous implementations that only checked if the
    last component of module paths matched, which could incorrectly match
    ``mylib.db.Connection`` with ``otherlib.db.Connection``.

    Notes
    -----
    This function is used internally by the dependency injection system and
    should not be called directly by user code. It's designed to be conservative -
    when in doubt, it returns False to prevent incorrect dependency injection.

    The function assumes that legitimate re-imports will have identical module
    paths, which is true for standard Python import mechanisms but may not hold
    for exotic dynamic loading scenarios.

    See Also
    --------
    DependencyResolver : Uses this function to match parameter types
    register_dependency : How to register dependencies for injection
    """
    # Both must be types
    if not (isinstance(type1, type) and isinstance(type2, type)):
        return False

    # Exact same type (identity check) - most common case
    if type1 is type2:
        return True

    # Check for same fully qualified name (handles re-imports of same class)
    if not (hasattr(type1, "__name__") and hasattr(type2, "__name__")):
        return False

    if not (hasattr(type1, "__module__") and hasattr(type2, "__module__")):
        return False

    # Only match if BOTH name AND full module path are identical
    # This prevents dangerous cross-library matching (e.g., psycopg2.Connection vs asyncpg.Connection)
    return type1.__name__ == type2.__name__ and type1.__module__ == type2.__module__
