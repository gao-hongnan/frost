"""BaseSettings with automatic object instantiation support."""

from __future__ import annotations

from pydantic_settings import BaseSettings
from pydantic_settings.sources import (
    PydanticBaseSettingsSource,
    YamlConfigSettingsSource,
)


class BaseSettingsWithInstantiation(BaseSettings):
    """BaseSettings that automatically instantiates DynamicConfig fields.

    Extends Pydantic BaseSettings to automatically create objects from:
    - DynamicConfig fields
    - Dict fields with '_target_' key

    Instantiation happens after all config loading and merging is complete.

    Example
    -------
    >>> from frost.pydanticonf import DynamicConfig
    >>> from pydantic_settings import SettingsConfigDict
    >>> from pydantic import BaseModel

    >>> class Settings(BaseSettingsWithInstantiation):
    ...     model_config = SettingsConfigDict(yaml_file="config.yaml")
    ...     database: DynamicConfig[BaseModel]

    >>> settings = Settings()  # database is instantiated automatically
    """

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Customize source order to add YAML support.

        Precedence: init_settings > env_settings > yaml_source > dotenv_settings > file_secret_settings
        """
        config = getattr(cls, "model_config", {})

        if not config.get("yaml_file"):
            return super().settings_customise_sources(
                settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
            )

        yaml_source = YamlConfigSettingsSource(
            settings_cls, yaml_file=config["yaml_file"], yaml_file_encoding=config.get("yaml_file_encoding", "utf-8")
        )

        return (
            init_settings,  # 1. Constructor args (highest precedence)
            env_settings,  # 2. Environment variables override YAML
            yaml_source,  # 3. YAML configuration (base + overrides)
            dotenv_settings,  # 4. .env file settings
            file_secret_settings,  # 5. Secret files (lowest precedence)
        )
