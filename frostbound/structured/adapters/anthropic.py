from __future__ import annotations

import instructor
from anthropic import AsyncAnthropic
from anthropic.types import Message as AnthropicResponse

from frostbound.structured.adapters.base import BaseAdapter
from frostbound.structured.config import AnthropicProviderConfig


class AnthropicAdapter(BaseAdapter[AnthropicProviderConfig, AsyncAnthropic, AnthropicResponse]):
    def _create_client(self) -> AsyncAnthropic:
        return AsyncAnthropic(**self.provider_config.model_dump())

    def _with_instructor(self) -> instructor.AsyncInstructor:
        client: AsyncAnthropic = self.client
        return instructor.from_anthropic(client, mode=self.instructor_config.mode)
