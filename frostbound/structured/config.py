from __future__ import annotations

from typing import Annotated, Generic

import instructor
from pydantic import BaseModel, ConfigDict, Field

from frostbound.structured.hooks import CompletionTrace
from frostbound.structured.types import BaseModelT, Capability, MessageRole, Provider, ResponseT


class Message(BaseModel):
    role: MessageRole
    content: str
    name: str | None = None
    tool_call_id: str | None = None

    model_config = ConfigDict(frozen=True)


class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int

    model_config = ConfigDict(frozen=True)


class Allowable(BaseModel):
    model_config = ConfigDict(extra="allow")


class BaseProviderConfig(Allowable):
    provider: Provider = Field(exclude=True)
    api_key: str


class OpenAIProviderConfig(BaseProviderConfig):
    provider: Provider = Field(default=Provider.OPENAI, exclude=True)


class AnthropicProviderConfig(BaseProviderConfig):
    provider: Provider = Field(default=Provider.ANTHROPIC, exclude=True)


class GeminiProviderConfig(BaseProviderConfig):
    provider: Provider = Field(default=Provider.GEMINI, exclude=True)


ProviderConfig = Annotated[
    OpenAIProviderConfig | AnthropicProviderConfig | GeminiProviderConfig,
    Field(discriminator="provider"),
]


class BaseClientParams(Allowable):
    provider: Provider = Field(exclude=True)
    capability: Capability = Field(exclude=True)

    model: str


class OpenAICompletionClientParams(BaseClientParams):
    provider: Provider = Field(default=Provider.OPENAI, exclude=True)
    capability: Capability = Field(default=Capability.COMPLETION, exclude=True)


class OpenAIEmbeddingClientParams(BaseClientParams):
    provider: Provider = Field(default=Provider.OPENAI, exclude=True)
    capability: Capability = Field(default=Capability.EMBEDDING, exclude=True)


class OpenAIVisionClientParams(BaseClientParams):
    provider: Provider = Field(default=Provider.OPENAI, exclude=True)
    capability: Capability = Field(default=Capability.VISION, exclude=True)


class AnthropicCompletionClientParams(BaseClientParams):
    provider: Provider = Field(default=Provider.ANTHROPIC, exclude=True)
    capability: Capability = Field(default=Capability.COMPLETION, exclude=True)


class GeminiCompletionClientParams(BaseClientParams):
    provider: Provider = Field(default=Provider.GEMINI, exclude=True)
    capability: Capability = Field(default=Capability.COMPLETION, exclude=True)


CompletionClientParams = Annotated[
    OpenAICompletionClientParams | AnthropicCompletionClientParams | GeminiCompletionClientParams,
    Field(discriminator="provider"),
]


class InstructorConfig(Allowable):
    mode: instructor.Mode


class CompletionResult(BaseModel, Generic[BaseModelT, ResponseT]):
    data: BaseModelT
    trace: CompletionTrace[ResponseT]

    model_config = ConfigDict(arbitrary_types_allowed=True)
