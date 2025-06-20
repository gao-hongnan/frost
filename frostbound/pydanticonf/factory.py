"""Factory pattern for configuration-driven object creation.

Combines dependency injection, lazy instantiation, caching, and runtime overrides.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Generic, cast, overload
from weakref import WeakValueDictionary

from frostbound.pydanticonf._instantiate import instantiate, register_dependency
from frostbound.pydanticonf.base import DynamicConfig
from frostbound.pydanticonf.types import ConfigData, T

logger = logging.getLogger(__name__)


class ConfigFactory(Generic[T]):
    """Factory for configuration-driven object creation.

    Provides dependency injection, lazy instantiation, caching, and runtime overrides.
    Thread-safe with type safety via generics.

    Parameters
    ----------
    cache : bool, default=True
        Whether to cache instances created via get()

    Example
    -------
    >>> factory = ConfigFactory[Service]()
    ...     factory.register_config("prod", ServiceConfig(...))
    ...     service = factory.get("prod", debug=True)
    """

    def __init__(self, *, cache: bool = True) -> None:
        """Initialize a new ConfigFactory.

        Parameters
        ----------
        cache : bool, default=True
            Whether to cache instances created via get()
        """
        self._cache_enabled = cache
        self._configs: dict[str, DynamicConfig[T] | ConfigData] = {}
        self._dependencies: dict[str, Any] = {}
        self._cache: WeakValueDictionary[str, T] = WeakValueDictionary()
        self._lock = threading.RLock()

    def register_dependency(self, name: str, instance: Any) -> None:
        """Register a shared dependency for injection into created instances.

        Parameters
        ----------
        name : str
            Parameter name that matches the constructor argument
        instance : Any
            The dependency instance to inject
        """
        with self._lock:
            self._dependencies[name] = instance
            register_dependency(name, instance)

    def register_config(self, name: str, config: DynamicConfig[T] | ConfigData) -> None:
        """
        Register a named configuration for later instantiation.

        Registered configurations act as templates that can be instantiated
        multiple times with different runtime overrides.

        Parameters
        ----------
        name : str
            Unique name for this configuration
        config : DynamicConfig[T] | ConfigData
            The configuration to register

        Raises
        ------
        ValueError
            If a configuration with the same name already exists

        Examples
        --------
        >>> factory.register_config("dev", DevServiceConfig())
        >>> factory.register_config("prod", ProdServiceConfig())
        >>> # Later: factory.get("dev") or factory.get("prod")
        """
        with self._lock:
            if name in self._configs:
                raise ValueError(f"Configuration '{name}' already registered")
            self._configs[name] = config

    @overload
    def create(self, config: DynamicConfig[T], **overrides: Any) -> T: ...

    @overload
    def create(self, config: ConfigData, **overrides: Any) -> T: ...

    def create(self, config: DynamicConfig[T] | ConfigData, **overrides: Any) -> T:
        """
        Create an instance immediately from configuration with optional overrides.

        This method performs immediate instantiation without caching. Use this
        when you need a fresh instance or don't want caching behavior.

        Parameters
        ----------
        config : DynamicConfig[T] | ConfigData
            Configuration specifying how to create the instance
        **overrides : Any
            Runtime parameter overrides. Supports nested overrides using
            double underscore notation (e.g., `database__host="new.server"`)

        Returns
        -------
        T
            The created instance

        Examples
        --------
        >>> # Direct instantiation
        >>> service = factory.create(
        ...     ServiceConfig(_target_="myapp.Service"),
        ...     timeout=30
        ... )
        >>>
        >>> # With nested overrides
        >>> service = factory.create(config,
        ...     database__host="prod.server",
        ...     cache__ttl=3600
        ... )
        """
        config_with_overrides = self._apply_nested_overrides(config, overrides)
        all_overrides = self._dependencies.copy()
        with self._lock:
            result = instantiate(config_with_overrides, **all_overrides)
            return cast(T, result)

    @overload
    def get(self, name: str, /, **overrides: Any) -> T: ...

    @overload
    def get(self, config: DynamicConfig[T], /, **overrides: Any) -> T: ...

    @overload
    def get(self, config: ConfigData, /, **overrides: Any) -> T: ...

    def get(self, name_or_config: str | DynamicConfig[T] | ConfigData, /, **overrides: Any) -> T:
        """
        Get an instance, using cache if available (when caching is enabled).

        This method supports both named configurations (registered via
        `register_config`) and direct configuration objects. When caching
        is enabled, instances are cached based on the configuration and
        overrides.

        Parameters
        ----------
        name_or_config : str | DynamicConfig[T] | ConfigData
            Either a registered configuration name or a configuration object
        **overrides : Any
            Runtime parameter overrides

        Returns
        -------
        T
            The instance (may be cached if caching is enabled)

        Raises
        ------
        KeyError
            If a name is provided but no configuration is registered with that name
        TypeError
            If the argument is neither a string nor a valid configuration

        Examples
        --------
        >>> # Get by registered name (cached)
        >>> service = factory.get("default")
        >>> same_service = factory.get("default")  # Returns cached
        >>>
        >>> # Get with overrides (creates new cache entry)
        >>> dev_service = factory.get("default", debug=True)
        >>>
        >>> # Get from direct config (also cached if enabled)
        >>> service = factory.get(ServiceConfig(...))
        """
        with self._lock:
            # Determine config and cache key
            if isinstance(name_or_config, str):
                name = name_or_config
                if name not in self._configs:
                    raise KeyError(f"No configuration registered for '{name}'")
                config = self._configs[name]
                base_key = f"named:{name}"
            else:
                # Must be DynamicConfig or dict based on type signature
                config = name_or_config
                # Use config's string representation for cache key
                base_key = f"config:{str(config)}"

            # Check cache if enabled
            if self._cache_enabled:
                # Create cache key including overrides
                override_key = str(sorted(overrides.items())) if overrides else ""
                cache_key = f"{base_key}:{override_key}"

                if cache_key in self._cache:
                    return self._cache[cache_key]

                # Create instance
                instance = self.create(config, **overrides)

                # Try to cache - some objects (like dict, list) can't be weakly referenced
                try:
                    self._cache[cache_key] = instance
                except TypeError:
                    # Some objects (dict, list, int, str) can't be weakly referenced
                    logger.debug(f"Cannot cache instance of type {type(instance).__name__} - not weakly referenceable")

                return instance

            # No caching, just create
            return self.create(config, **overrides)

    def create_multiple(self, configs: list[DynamicConfig[T] | ConfigData], **common_overrides: Any) -> list[T]:
        """
        Create multiple instances from a list of configurations.

        This is a convenience method for batch instantiation with common
        overrides applied to all instances.

        Parameters
        ----------
        configs : list[DynamicConfig[T] | ConfigData]
            List of configurations to instantiate
        **common_overrides : Any
            Overrides to apply to all configurations

        Returns
        -------
        list[T]
            List of created instances in the same order as configs

        Examples
        --------
        >>> services = factory.create_multiple(
        ...     [config1, config2, config3],
        ...     environment="production",
        ...     log_level="INFO"
        ... )
        """
        return [self.create(config, **common_overrides) for config in configs]

    def clear_cache(self, name: str | None = None) -> None:
        """
        Clear cached instances.

        Parameters
        ----------
        name : str | None, default=None
            If provided, only clear cache entries for this configuration name.
            If None, clear all cached instances.

        Examples
        --------
        >>> factory.clear_cache()  # Clear all
        >>> factory.clear_cache("default")  # Clear only "default" entries
        """
        with self._lock:
            if name is None:
                self._cache.clear()
            else:
                # Clear all cache entries for the given name
                prefix = f"named:{name}:"
                keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
                for key in keys_to_remove:
                    del self._cache[key]

    def clear_dependencies(self) -> None:
        """Clear all registered dependencies."""
        with self._lock:
            self._dependencies.clear()

    def list_configs(self) -> list[str]:
        """
        List all registered configuration names.

        Returns
        -------
        list[str]
            Names of all registered configurations

        Examples
        --------
        >>> factory.register_config("dev", dev_config)
        >>> factory.register_config("prod", prod_config)
        >>> factory.list_configs()
        ['dev', 'prod']
        """
        with self._lock:
            return list(self._configs.keys())

    def _apply_nested_overrides(
        self, config: DynamicConfig[T] | ConfigData, overrides: dict[str, Any]
    ) -> DynamicConfig[T] | ConfigData:
        """
        Apply nested overrides to configuration.

        Converts database__host="value" to modifying config.database.host
        """
        # Create a working copy
        config_dict = config.model_dump(by_alias=True) if isinstance(config, DynamicConfig) else config.copy()

        # Separate flat and nested overrides
        for key, value in overrides.items():
            if "__" in key:
                # Handle nested override
                parts = key.split("__")
                current = config_dict

                # Navigate to the parent of the final key
                for part in parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    current = current[part]

                # Set the final value
                current[parts[-1]] = value
            else:
                # Direct override at top level
                config_dict[key] = value

        # Reconstruct the config object if it was a DynamicConfig
        if isinstance(config, DynamicConfig):
            # Create new instance with updated values
            return type(config)(**config_dict)

        return config_dict
