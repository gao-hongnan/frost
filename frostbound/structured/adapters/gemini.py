from __future__ import annotations

from typing import TYPE_CHECKING, Any, AsyncIterator, Literal, overload

import instructor
from google import generativeai as genai
from google.generativeai.generative_models import GenerativeModel
from google.generativeai.types import AsyncGenerateContentResponse, GenerationConfig
from openai.types.chat import ChatCompletionMessageParam

from frostbound.structured.adapters.base import BaseAdapter
from frostbound.structured.config import GeminiProviderConfig
from frostbound.structured.types import BaseModelT

if TYPE_CHECKING:
    from frostbound.structured.config import CompletionResult, Message
    from frostbound.structured.hooks import CompletionTrace


class GeminiAdapter(BaseAdapter[GeminiProviderConfig, GenerativeModel, AsyncGenerateContentResponse]):
    def _create_client(self) -> GenerativeModel:
        genai.configure(api_key=self.provider_config.api_key)
        model_name = self.completion_params.model

        config_params = self.completion_params.model_dump()
        generation_config = GenerationConfig(**config_params)

        return GenerativeModel(
            model_name=model_name,
            generation_config=generation_config,
        )

    def _with_instructor(self) -> instructor.AsyncInstructor:
        client: GenerativeModel = self.client
        return instructor.from_gemini(client=client, use_async=True, mode=self.instructor_config.mode)  # type: ignore[no-any-return]

    @overload
    async def acreate(
        self,
        messages: list[Message],
        response_model: type[BaseModelT],
        *,
        with_hooks: Literal[False] = False,
        **kwargs: Any,
    ) -> BaseModelT: ...

    @overload
    async def acreate(
        self,
        messages: list[Message],
        response_model: type[BaseModelT],
        *,
        with_hooks: Literal[True],
        **kwargs: Any,
    ) -> CompletionResult[BaseModelT, AsyncGenerateContentResponse]: ...

    async def acreate(
        self,
        messages: list[Message],
        response_model: type[BaseModelT],
        with_hooks: bool = False,
        **kwargs: Any,
    ) -> BaseModelT | CompletionResult[BaseModelT, AsyncGenerateContentResponse]:
        from frostbound.structured.hooks import ahook_instructor

        formatted_messages = self._format_messages(messages)

        captured: CompletionTrace[AsyncGenerateContentResponse]
        async with ahook_instructor(self.instructor, enable=with_hooks) as captured:
            # Don't pass completion_params - they're already configured in the client
            response = await self.instructor.create(
                response_model=response_model,
                messages=formatted_messages,
                **self.instructor_config.model_dump(exclude={"mode"}),
                **kwargs,
            )
            return self._assemble(response, captured, with_hooks)

    async def _astream(
        self,
        formatted_messages: list[ChatCompletionMessageParam],
        response_model: type[BaseModelT],
        with_hooks: bool = False,
    ) -> AsyncIterator[BaseModelT | CompletionResult[BaseModelT, AsyncGenerateContentResponse]]:
        from frostbound.structured.hooks import ahook_instructor

        captured: CompletionTrace[AsyncGenerateContentResponse]
        async with ahook_instructor(self.instructor, enable=with_hooks) as captured:
            # NOTE: Don't pass **self.completion_params.model_dump(), - they're already configured in the client
            async for partial in self.instructor.create_partial(
                response_model=response_model,
                messages=formatted_messages,
                **self.instructor_config.model_dump(exclude={"mode"}),
            ):
                yield self._assemble(partial, captured, with_hooks)
