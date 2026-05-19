import uuid
import os
import json
import re
import hashlib
import datetime
import redis.asyncio as aioredis
from typing import List, Dict, Tuple
from src.utils.logger import logger

_REDIS = os.getenv("REDIS_URL", "rediss://localhost:6379/0")
redis_client = aioredis.Redis.from_url(_REDIS, decode_responses=True)

# Session expiry in seconds
_SESSION_TTL: int = int(os.getenv("SESSION_TTL", 86400))
# Max user+assistant message pairs to keep before trimming. System prompt is always preserved.
_MAX_HISTORY_PAIRS: int = int(os.getenv("MAX_HISTORY_PAIRS", 20))


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


async def record_usage(app_name: str, prompt_tokens: int, completion_tokens: int) -> None:
    pipe = redis_client.pipeline()
    pipe.incrby(f"usage:{app_name}:prompt_tokens", prompt_tokens)
    pipe.incrby(f"usage:{app_name}:completion_tokens", completion_tokens)
    pipe.incrby(f"usage:{app_name}:requests", 1)
    await pipe.execute()


async def get_usage(app_name: str) -> dict:
    pipe = redis_client.pipeline()
    pipe.get(f"usage:{app_name}:prompt_tokens")
    pipe.get(f"usage:{app_name}:completion_tokens")
    pipe.get(f"usage:{app_name}:requests")
    prompt, completion, requests = await pipe.execute()
    return {
        "app_name": app_name,
        "requests": int(requests or 0),
        "prompt_tokens": int(prompt or 0),
        "completion_tokens": int(completion or 0),
        "total_tokens": int(prompt or 0) + int(completion or 0),
    }


async def get_all_app_names() -> list[str]:
    """Returns every app_name that has a usage record."""
    app_names: set[str] = set()
    async for key in redis_client.scan_iter("usage:*:requests"):
        parts = str(key).split(":")
        if len(parts) >= 2:
            app_names.add(parts[1])
    return list(app_names)


def _hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def store_api_key(full_key: str, app_name: str) -> None:
    value = json.dumps({
        "app_name": app_name,
        "key_preview": full_key[:14] + "...",
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
    })
    await redis_client.set(f"apikey:{_hash_api_key(full_key)}", value)


async def lookup_api_key(full_key: str) -> str | None:
    data = await redis_client.get(f"apikey:{_hash_api_key(full_key)}")
    if not isinstance(data, str):
        return None
    try:
        return json.loads(data).get("app_name")
    except json.JSONDecodeError:
        return None


async def list_all_api_keys() -> list[dict]:
    keys = [key async for key in redis_client.scan_iter("apikey:*")]
    if not keys:
        return []
    values = await redis_client.mget(*keys)
    entries: list[dict] = []
    for redis_key, raw in zip(keys, values):
        if not isinstance(raw, str):
            continue
        try:
            data = json.loads(raw)
            entries.append({
                "app_name": data.get("app_name"),
                "key_preview": data.get("key_preview"),
                "created_at": data.get("created_at"),
                "key_hash": str(redis_key).split(":", 1)[1],
            })
        except (json.JSONDecodeError, AttributeError):
            pass
    return entries


async def remove_api_key_by_hash(key_hash: str) -> bool:
    return await redis_client.delete(f"apikey:{key_hash}") > 0  # type: ignore[operator]


async def delete_all_app_sessions(app_name: str) -> int:
    """Deletes all sessions for the given app. Returns the count of deleted keys."""
    keys = [key async for key in redis_client.scan_iter(f"chat:{app_name}:*")]
    if not keys:
        return 0
    return int(await redis_client.delete(*keys))  # type: ignore[arg-type]
