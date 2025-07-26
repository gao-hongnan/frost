from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, AsyncIterator, Generic, Literal, overload

from instructor import AsyncInstructor
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionDeveloperMessageParam,
    ChatCompletionFunctionMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionUserMessageParam,
)

from frostbound.structured.types import BaseModelT, BaseProviderConfigT, ClientT, MessageRole, ResponseT

if TYPE_CHECKING:
    from frostbound.structured.config import CompletionClientParams, CompletionResult, InstructorConfig, Message
    from frostbound.structured.hooks import CompletionTrace


class BaseAdapter(ABC, Generic[BaseProviderConfigT, ClientT, ResponseT]):
    def __init__(
        self,
        *,
        provider_config: BaseProviderConfigT,
        completion_params: CompletionClientParams,
        instructor_config: InstructorConfig,
    ) -> None:
        self.provider_config = provider_config
        self.completion_params = completion_params
        self.instructor_config = instructor_config
        self._client: ClientT | None = None
        self._instructor: AsyncInstructor | None = None

    @property
    def client(self) -> ClientT:
        if self._client is None:
            self._client = self._create_client()
        return self._client

    @property
    def instructor(self) -> AsyncInstructor:
        if self._instructor is None:
            self._instructor = self._with_instructor()
        return self._instructor

    @abstractmethod
    def _create_client(self) -> ClientT: ...

    @abstractmethod
    def _with_instructor(self) -> AsyncInstructor: ...

    def _format_messages(self, messages: list[Message]) -> list[ChatCompletionMessageParam]:
        formatted: list[ChatCompletionMessageParam] = []
        for msg in messages:
            match msg.role:
                case MessageRole.USER:
                    formatted.append(ChatCompletionUserMessageParam(role="user", content=msg.content))
                case MessageRole.ASSISTANT:
                    formatted.append(ChatCompletionAssistantMessageParam(role="assistant", content=msg.content))
                case MessageRole.SYSTEM:
                    formatted.append(ChatCompletionSystemMessageParam(role="system", content=msg.content))
                case MessageRole.FUNCTION:
                    if msg.name is not None:
                        formatted.append(
                            ChatCompletionFunctionMessageParam(role="function", name=msg.name, content=msg.content)
                        )
                case MessageRole.TOOL:
                    if msg.tool_call_id is not None:
                        formatted.append(
                            ChatCompletionToolMessageParam(
                                role="tool", content=msg.content, tool_call_id=msg.tool_call_id
                            )
                        )
                case MessageRole.DEVELOPER:
                    formatted.append(ChatCompletionDeveloperMessageParam(role="developer", content=msg.content))

        return formatted

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
    ) -> CompletionResult[BaseModelT, ResponseT]: ...

    async def acreate(
        self,
        messages: list[Message],
        response_model: type[BaseModelT],
        with_hooks: bool = False,
        **kwargs: Any,
    ) -> BaseModelT | CompletionResult[BaseModelT, ResponseT]:
        from frostbound.structured.hooks import ahook_instructor

        formatted_messages = self._format_messages(messages)

        captured: CompletionTrace[ResponseT]
        async with ahook_instructor(self.instructor, enable=with_hooks) as captured:
            response = await self.instructor.create(
                response_model=response_model,
                messages=formatted_messages,
                **self.instructor_config.model_dump(exclude={"mode"}),
                **self.completion_params.model_dump(),
                **kwargs,
            )
            return self._assemble(response, captured, with_hooks)

    @overload
    def astream(
        self,
        messages: list[Message],
        response_model: type[BaseModelT],
        *,
        with_hooks: Literal[False] = False,
    ) -> AsyncIterator[BaseModelT]: ...

    @overload
    def astream(
        self,
        messages: list[Message],
        response_model: type[BaseModelT],
        *,
        with_hooks: Literal[True],
    ) -> AsyncIterator[CompletionResult[BaseModelT, ResponseT]]: ...

    def astream(
        self,
        messages: list[Message],
        response_model: type[BaseModelT],
        with_hooks: bool = False,
    ) -> AsyncIterator[BaseModelT | CompletionResult[BaseModelT, ResponseT]]:
        formatted_messages = self._format_messages(messages)
        return self._astream(formatted_messages, response_model, with_hooks)

    async def _astream(
        self,
        formatted_messages: list[ChatCompletionMessageParam],
        response_model: type[BaseModelT],
        with_hooks: bool = False,
    ) -> AsyncIterator[BaseModelT | CompletionResult[BaseModelT, ResponseT]]:
        from frostbound.structured.hooks import ahook_instructor

        captured: CompletionTrace[ResponseT]
        async with ahook_instructor(self.instructor, enable=with_hooks) as captured:
            async for partial in self.instructor.create_partial(
                response_model=response_model,
                messages=formatted_messages,
                **self.instructor_config.model_dump(exclude={"mode"}),
                **self.completion_params.model_dump(),
            ):
                yield self._assemble(partial, captured, with_hooks)

    def _assemble(
        self,
        response: BaseModelT,
        captured: CompletionTrace[ResponseT],
        with_hooks: bool,
    ) -> BaseModelT | CompletionResult[BaseModelT, ResponseT]:
        from frostbound.structured.config import CompletionResult

        if not with_hooks:
            return response

        return CompletionResult(data=response, trace=captured)
