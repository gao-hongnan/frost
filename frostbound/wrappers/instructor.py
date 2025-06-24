from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator, Iterator, Literal, TypeAlias

import instructor
from instructor.hooks import HookName
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

MessageParam: TypeAlias = dict[str, Any]
HookNameStr: TypeAlias = Literal[
    "completion:kwargs", "completion:response", "completion:error", "completion:last_attempt", "parse:error"
]


class CompletionTrace(BaseModel):
    kwargs: dict[str, Any] = Field(default_factory=dict)
    messages: list[MessageParam] = Field(default_factory=list)
    raw_response: Any = None
    parsed_result: BaseModel | None = None
    error: Exception | None = None
    last_attempt_error: Exception | None = None
    parse_error: Exception | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


def _setup_hooks(
    client: instructor.Instructor | instructor.AsyncInstructor,
) -> tuple[CompletionTrace, list[tuple[HookNameStr | HookName, Any]]]:
    captured = CompletionTrace()

    def capture_kwargs(*_: Any, **kwargs: Any) -> None:
        captured.kwargs = kwargs
        captured.messages = kwargs.get("messages", [])

    def capture_response_data(response: Any) -> None:
        captured.raw_response = response

    def capture_error(error: Exception) -> None:
        captured.error = error

    def capture_last_attempt(error: Exception) -> None:
        captured.last_attempt_error = error

    def capture_parse_error(error: Exception) -> None:
        captured.parse_error = error

    hooks: list[tuple[HookNameStr | HookName, Any]] = [
        ("completion:kwargs", capture_kwargs),
        ("completion:response", capture_response_data),
        ("completion:error", capture_error),
        ("completion:last_attempt", capture_last_attempt),
        ("parse:error", capture_parse_error),
    ]

    for hook_name, handler in hooks:
        client.on(hook_name, handler)

    return captured, hooks


@contextmanager
def hook_instructor(
    client: instructor.Instructor | instructor.AsyncInstructor, enable: bool = True
) -> Iterator[CompletionTrace]:
    """
    Capture execution details from a synchronous instructor client.

    Use this context manager when working with synchronous instructor clients
    (instructor.Instructor) to capture messages, responses, and errors during
    completion operations.

    Parameters
    ----------
    client : instructor.Instructor | instructor.AsyncInstructor
        The instructor client instance to capture events from.
    enable : bool, optional
        Whether to enable hook capture. When False, returns an empty
        CompletionTrace without setting up any hooks. Default is True.

    Yields
    ------
    CompletionTrace
        An object containing:
        - kwargs: The complete kwargs passed to the completion API
        - messages: The list of messages sent to the LLM
        - raw_response: The raw API response
        - parsed_result: The parsed Pydantic model result
        - error: Any completion error that occurred
        - last_attempt_error: Error from the final retry attempt
        - parse_error: Any parsing/validation error

    Examples
    --------
    >>> import instructor
    >>> from openai import OpenAI
    >>>
    >>> client = instructor.from_openai(OpenAI())
    >>> with hook_instructor(client) as captured:
    ...     result = client.create(
    ...         response_model=MyModel,
    ...         messages=[{"role": "user", "content": "Hello"}]
    ...     )
    ...     print(captured.messages)  # Access captured messages
    ...     print(captured.kwargs)  # Access all completion kwargs
    ...     print(captured.raw_response)  # Access raw API response
    >>>
    >>> # Conditionally enable hooks based on debug mode
    >>> debug_mode = os.getenv("DEBUG", "").lower() == "true"
    >>> with hook_instructor(client, enable=debug_mode) as captured:
    ...     result = client.create(...)
    """
    if not enable:
        yield CompletionTrace()
        return

    captured, hooks = _setup_hooks(client)

    try:
        yield captured
    finally:
        for hook_name, handler in hooks:
            client.off(hook_name, handler)


@asynccontextmanager
async def ahook_instructor(client: instructor.AsyncInstructor, enable: bool = True) -> AsyncIterator[CompletionTrace]:
    """
    Capture execution details from an asynchronous instructor client.

    Use this async context manager when working with asynchronous instructor
    clients (instructor.AsyncInstructor) in async/await code. This is necessary
    when:
    - Your application uses asyncio for concurrent operations
    - You're working within an async function or coroutine
    - You need to make non-blocking API calls
    - You're handling multiple concurrent LLM requests

    Parameters
    ----------
    client : instructor.AsyncInstructor
        The async instructor client instance to capture events from.
    enable : bool, optional
        Whether to enable hook capture. When False, returns an empty
        CompletionTrace without setting up any hooks. Default is True.

    Yields
    ------
    CompletionTrace
        An object containing:
        - kwargs: The complete kwargs passed to the completion API
        - messages: The list of messages sent to the LLM
        - raw_response: The raw API response
        - parsed_result: The parsed Pydantic model result
        - error: Any completion error that occurred
        - last_attempt_error: Error from the final retry attempt
        - parse_error: Any parsing/validation error

    Examples
    --------
    >>> import asyncio
    >>> import instructor
    >>> from openai import AsyncOpenAI
    >>>
    >>> async def main():
    ...     client = instructor.from_openai(AsyncOpenAI())
    ...     async with ahook_instructor(client) as captured:
    ...         result = await client.create(
    ...             response_model=MyModel,
    ...             messages=[{"role": "user", "content": "Hello"}]
    ...         )
    ...         print(captured.messages)
    ...         print(captured.kwargs)  # Access all completion kwargs
    ...         print(captured.raw_response)
    >>>
    >>> asyncio.run(main())
    >>>
    >>> # Conditionally enable hooks based on debug mode
    >>> async def main_with_toggle():
    ...     debug_mode = os.getenv("DEBUG", "").lower() == "true"
    ...     client = instructor.from_openai(AsyncOpenAI())
    ...     async with ahook_instructor(client, enable=debug_mode) as captured:
    ...         result = await client.create(...)

    Notes
    -----
    The async version is required when using AsyncInstructor to properly
    handle the asynchronous event loop and ensure callbacks are registered
    and unregistered correctly in an async context.
    """
    if not enable:
        yield CompletionTrace()
        return

    captured, hooks = _setup_hooks(client)

    try:
        yield captured
    finally:
        for hook_name, handler in hooks:
            client.off(hook_name, handler)
