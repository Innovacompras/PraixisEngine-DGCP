import json
import datetime
from src.utils.store.client import redis_client

_MAX_EVENTS = 10_000
_GLOBAL_KEY = "audit:global"


async def log_event(action: str, details: dict, app_name: str | None = None) -> None:
    entry = json.dumps({
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "action": action,
        "app_name": app_name,
        "details": details,
    })
    pipe = redis_client.pipeline()
    pipe.rpush(_GLOBAL_KEY, entry)
    pipe.ltrim(_GLOBAL_KEY, -_MAX_EVENTS, -1)
    if app_name:
        app_key = f"audit:{app_name}"
        pipe.rpush(app_key, entry)
        pipe.ltrim(app_key, -_MAX_EVENTS, -1)
    await pipe.execute()


async def get_audit_log(app_name: str | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
    key = f"audit:{app_name}" if app_name else _GLOBAL_KEY
    total: int = await redis_client.llen(key)  # type: ignore[assignment]
    if total == 0 or offset >= total:
        return []
    start = max(0, total - offset - limit)
    end = total - offset - 1
    raw = await redis_client.lrange(key, start, end)
    return [json.loads(e) for e in reversed(raw)]
