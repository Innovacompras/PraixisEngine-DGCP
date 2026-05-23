from typing import AsyncGenerator
from src.config import MODEL_NAME as _MODEL_NAME
from src.utils.ai_client import get_async_ai_client, record_llm_usage
from src.utils.documents.file_parser import chunk_text
from src.utils.store.sessions import get_or_create_session, persist_history
from src.utils.system.logger import logger
from src.utils.concurrency import release_gpu_slot
from src.services.llm_runner import stream_llm, map_calls

_client = get_async_ai_client()


async def generate_chat_stream(
    prompt: str,
    app_name: str,
    system_prompt: str | None = None,
    session_id: str | None = None,
    response_format: str = "text",
) -> AsyncGenerator[str, None]:
    """Streams the chat response token-by-token.

    The GPU slot is acquired by the controller before streaming starts and is
    released in the finally block here.
    """
    full_ai_response = ""
    active_session_id: str | None = None
    history: list | None = None
    try:
        active_session_id, history = await get_or_create_session(
            session_id=session_id,
            system_prompt=system_prompt,
            app_name=app_name,
        )

        history.append({"role": "user", "content": prompt})
        await persist_history(app_name=app_name, session_id=active_session_id, history=history)

        extra: dict = {}
        if response_format == "json":
            extra["response_format"] = {"type": "json_object"}

        response = await _client.chat.completions.create(  # type: ignore[call-overload]
            model=_MODEL_NAME,
            messages=history,  # type: ignore[arg-type]
            stream=True,
            stream_options={"include_usage": True},
            **extra,
        )

        yield f"[SESSION_ID:{active_session_id}]\n"

        usage_recorded = False
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content is not None:
                word = chunk.choices[0].delta.content
                full_ai_response += word
                yield word
            if not usage_recorded and getattr(chunk, "usage", None):
                await record_llm_usage(chunk, app_name)
                usage_recorded = True
    finally:
        if full_ai_response and active_session_id and history is not None:
            history.append({"role": "assistant", "content": full_ai_response})
            await persist_history(app_name=app_name, session_id=active_session_id, history=history)
        await release_gpu_slot()


async def generate_file_summary(
    document_text: str,
    task: str,
    tone: str,
    app_name: str,
) -> AsyncGenerator[str, None]:
    """Processes a document based on user instructions, streaming progress events
    then the result. Each LLM call manages its own GPU slot via the shared runner,
    so the caller must NOT pre-acquire a slot."""
    text_chunks = chunk_text(text=document_text, max_words_per_chunk=1500)
    system_setup = f"You are a highly capable AI. Your tone must be: {tone}."
    total = len(text_chunks)

    if total == 1:
        messages = [
            {"role": "system", "content": f"{system_setup}\n\nTask: {task}"},
            {"role": "user", "content": text_chunks[0]},
        ]
        async for token in stream_llm(messages, app_name):
            yield token
        return

    # MAP PHASE — chunks run concurrently (bounded by CHUNK_CONCURRENCY)
    map_prompt = (
        f"{system_setup}\n\n"
        f"Task: Extract the information from the following text necessary to ultimately accomplish this goal: '{task}'."
    )
    logger.info(f"Mapping {total} chunks...")
    yield f"[PROGRESS:mapping {total} chunks]\n"
    mini_results = await map_calls(
        [
            [
                {"role": "system", "content": map_prompt},
                {"role": "user", "content": chunk},
            ]
            for chunk in text_chunks
        ],
        app_name,
    )

    # REDUCE PHASE — stream the synthesised answer
    logger.info("Combining chunks for the final result...")
    yield f"[PROGRESS:reducing {total} chunks]\n"
    combined_text = "\n\n".join(mini_results)
    reduce_prompt = (
        f"{system_setup}\n\n"
        f"The following text is a collection of extracted notes from a larger document.\n"
        f"Final Task: {task}\n"
        f"Use the notes to complete the final task perfectly."
    )
    reduce_messages = [
        {"role": "system", "content": reduce_prompt},
        {"role": "user", "content": combined_text},
    ]
    async for token in stream_llm(reduce_messages, app_name):
        yield token
