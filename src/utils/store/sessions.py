import uuid
import json
import re
from typing import List, Dict, Tuple
from src.config import SESSION_TTL as _SESSION_TTL, MAX_HISTORY_PAIRS as _MAX_HISTORY_PAIRS
from src.utils.store.client import redis_client
from src.utils.system.logger import logger


def _get_redis_key(app_name: str, session_id: str) -> str:
    return f"chat:{app_name}:{session_id}"


def _trim_history(history: list) -> list:
    """Keeps the system prompt and the most recent MAX_HISTORY_PAIRS exchange pairs."""
    system = [m for m in history if m["role"] == "system"]
    messages = [m for m in history if m["role"] != "system"]
    max_messages = _MAX_HISTORY_PAIRS * 2
    if len(messages) > max_messages:
        messages = messages[-max_messages:]
    return system + messages


async def get_or_create_session(
    app_name: str,
    session_id: str | None = None,
    system_prompt: str | None = None,
) -> Tuple[str, List[Dict[str, str]]]:

    if not session_id or not re.fullmatch(r"[0-9a-f]{32}", session_id):
        session_id = None

    final_prompt = system_prompt or "You are a helpful institutional assistant."

    if session_id:
        redis_key = _get_redis_key(app_name, session_id)
        stored_data = await redis_client.get(redis_key)

        if isinstance(stored_data, str):
            history = json.loads(stored_data)

            if (system_prompt
                    and len(history) > 0
                    and history[0].get("role") == "system"
                    and history[0]["content"] != system_prompt):
                logger.warning(
                    f"Ignoring system_prompt override for existing session {session_id} "
                    f"(app: {app_name}). System prompt is fixed at session creation."
                )

            await redis_client.expire(redis_key, _SESSION_TTL)
            return session_id, history

    new_session_id = uuid.uuid4().hex
    new_redis_key = _get_redis_key(app_name, new_session_id)
    initial_history = [{"role": "system", "content": final_prompt}]
    await redis_client.setex(new_redis_key, _SESSION_TTL, json.dumps(initial_history))

    return new_session_id, initial_history


async def persist_history(app_name: str, session_id: str, history: list) -> None:
    """Trims and writes an in-memory history back to Redis in a single round-trip.

    Use this when the caller already holds the history (e.g. from
    get_or_create_session) to avoid a redundant read-modify-write round-trip.
    """
    redis_key = _get_redis_key(app_name, session_id)
    trimmed = _trim_history(history)
    await redis_client.setex(redis_key, _SESSION_TTL, json.dumps(trimmed))


async def get_session_history(app_name: str, session_id: str) -> list:
    redis_key = _get_redis_key(app_name, session_id)
    data = await redis_client.get(redis_key)
    if isinstance(data, str):
        return json.loads(data)
    return []


async def delete_session(app_name: str, session_id: str) -> bool:
    redis_key = _get_redis_key(app_name, session_id)
    return await redis_client.delete(redis_key) > 0  # type: ignore[operator]


async def get_all_active_sessions(app_name: str) -> list:
    prefix = f"chat:{app_name}:"
    prefix_length = len(prefix)
    keys = []
    async for key in redis_client.scan_iter(f"{prefix}*"):
        keys.append(str(key)[prefix_length:])
    return keys


async def delete_all_app_sessions(app_name: str) -> int:
    """Deletes all sessions for the given app. Returns the count of deleted keys."""
    keys = [key async for key in redis_client.scan_iter(f"chat:{app_name}:*")]
    if not keys:
        return 0
    return int(await redis_client.delete(*keys))  # type: ignore[arg-type]
