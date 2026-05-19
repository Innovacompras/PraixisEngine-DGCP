"""Shared LLM execution primitives.

Every call here wraps the request in a GPU slot via ``gpu_slot()`` and records
token usage. Streaming endpoints that acquire the GPU slot in their controller
(chat, rag_answer) must NOT use these helpers — they would double-acquire.
"""
import asyncio
import os
from typing import AsyncGenerator

from src.utils.ai_client import get_async_ai_client, record_llm_usage
from src.utils.concurrency import gpu_slot

_client = get_async_ai_client()
_MODEL_NAME = os.getenv("MODEL_NAME", "gemma-api-test")
_CHUNK_CONCURRENCY = int(os.getenv("CHUNK_CONCURRENCY", "4"))
_chunk_sem = asyncio.Semaphore(_CHUNK_CONCURRENCY)

Message = dict[str, str]


async def call_llm(messages: list[Message], app_name: str) -> str:
    """Single non-streaming LLM call. Raises on empty response."""
    async with gpu_slot():
        response = await _client.chat.completions.create(
            model=_MODEL_NAME,
            messages=messages,  # type: ignore[arg-type]
        )
    await record_llm_usage(response, app_name)
    content = response.choices[0].message.content
    if content is None:
        raise RuntimeError("LLM returned no content.")
    return content


async def stream_llm(messages: list[Message], app_name: str) -> AsyncGenerator[str, None]:
    """Streams an LLM response token-by-token, holding the GPU slot for the
    full stream duration."""
    async with gpu_slot():
        response = await _client.chat.completions.create(
            model=_MODEL_NAME,
            messages=messages,  # type: ignore[arg-type]
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content
            if getattr(chunk, "usage", None):
                await record_llm_usage(chunk, app_name)


async def map_calls(messages_list: list[list[Message]], app_name: str) -> list[str]:
    """Runs many non-streaming calls concurrently, bounded by CHUNK_CONCURRENCY.
    Results preserve input order."""
    async def _run(messages: list[Message]) -> str:
        async with _chunk_sem:
            return await call_llm(messages, app_name)

    return list(await asyncio.gather(*[_run(m) for m in messages_list]))
