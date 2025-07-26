from __future__ import annotations

from typing import TYPE_CHECKING, overload

from frostbound.structured.adapters.anthropic import AnthropicAdapter
from frostbound.structured.adapters.gemini import GeminiAdapter
from frostbound.structured.adapters.openai import OpenAIAdapter
from frostbound.structured.config import (
    AnthropicProviderConfig,
    GeminiProviderConfig,
    OpenAIProviderConfig,
)

if TYPE_CHECKING:
    from frostbound.structured.config import (
        AnthropicCompletionClientParams,
        CompletionClientParams,
        GeminiCompletionClientParams,
        InstructorConfig,
        OpenAICompletionClientParams,
        ProviderConfig,
    )


class AdapterFactory:
    @overload
    @classmethod
    def create(
        cls: type[AdapterFactory],
        *,
        provider_config: OpenAIProviderConfig,
        completion_params: OpenAICompletionClientParams,
        instructor_config: InstructorConfig,
    ) -> OpenAIAdapter: ...

    @overload
    @classmethod
    def create(
        cls: type[AdapterFactory],
        *,
        provider_config: AnthropicProviderConfig,
        completion_params: AnthropicCompletionClientParams,
        instructor_config: InstructorConfig,
    ) -> AnthropicAdapter: ...

    @overload
    @classmethod
    def create(
        cls: type[AdapterFactory],
        *,
        provider_config: GeminiProviderConfig,
        completion_params: GeminiCompletionClientParams,
        instructor_config: InstructorConfig,
    ) -> GeminiAdapter: ...

    @classmethod
    def create(
        cls: type[AdapterFactory],
        *,
        provider_config: ProviderConfig,
        completion_params: CompletionClientParams,
        instructor_config: InstructorConfig,
    ) -> OpenAIAdapter | AnthropicAdapter | GeminiAdapter:
        match provider_config:
            case OpenAIProviderConfig():
                return OpenAIAdapter(
                    provider_config=provider_config,
                    completion_params=completion_params,
                    instructor_config=instructor_config,
                )
            case AnthropicProviderConfig():
                return AnthropicAdapter(
                    provider_config=provider_config,
                    completion_params=completion_params,
                    instructor_config=instructor_config,
                )
            case GeminiProviderConfig():
                return GeminiAdapter(
                    provider_config=provider_config,
                    completion_params=completion_params,
                    instructor_config=instructor_config,
                )
