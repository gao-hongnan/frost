from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from anthropic.types import Message as AnthropicResponse
    from google.generativeai.types import AsyncGenerateContentResponse
    from openai.types.chat import ChatCompletion

    from frostbound.structured.config import BaseProviderConfig, CompletionClientParams, Message

BaseModelT = TypeVar("BaseModelT", bound=BaseModel)
MessageT = TypeVar("MessageT", bound="Message")
BaseProviderConfigT = TypeVar("BaseProviderConfigT", bound="BaseProviderConfig")
ClientT = TypeVar("ClientT")
CompletionClientParamsT = TypeVar("CompletionClientParamsT", bound="CompletionClientParams")
ResponseT = TypeVar("ResponseT", "ChatCompletion", "AnthropicResponse", "AsyncGenerateContentResponse")


class Provider(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


class Capability(StrEnum):
    COMPLETION = "completion"
    EMBEDDING = "embedding"
    VISION = "vision"


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"
    TOOL = "tool"
    DEVELOPER = "developer"
