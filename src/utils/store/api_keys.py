import json
import hashlib
import datetime
from src.utils.store.client import redis_client


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
