import asyncio
import secrets
from fastapi import HTTPException
from src.utils.memory import (
    redis_client,
    delete_all_app_sessions,
    get_usage,
    get_all_app_names,
    store_api_key,
    remove_api_key,
    list_all_api_keys,
)
from src.utils.vector_db import chroma_client
from src.utils.ai_client import get_ai_client
from src.utils.concurrency import get_gpu_status, reset_gpu_counter
from src.utils.audit import log_event, get_audit_log
from src.utils.logger import logger

# Sync client used only for the health-check ping (no LLM calls, no token tracking)
_llm_sync_client = get_ai_client()


async def get_health_status() -> dict:
    health_status = {"api": "online", "redis": "offline", "chromadb": "offline", "llm": "offline"}

    try:
        await redis_client.ping()  # type: ignore[misc]
        health_status["redis"] = "online"
    except Exception:
        logger.error("Redis health check failed.")

    try:
        await asyncio.to_thread(chroma_client.list_collections)
        health_status["chromadb"] = "online"
    except Exception:
        logger.error("ChromaDB health check failed.")

    try:
        await asyncio.to_thread(lambda: _llm_sync_client.with_options(timeout=5.0).models.list())
        health_status["llm"] = "online"
    except Exception:
        logger.error("LLM backend health check failed.")

    return health_status


async def get_system_stats() -> dict:
    active_sessions = 0
    async for _ in redis_client.scan_iter("chat:*"):
        active_sessions += 1

    def _count_vectors():
        cols = chroma_client.list_collections()
        return len(cols), sum(col.count() for col in cols)

    num_collections, total_vectors = await asyncio.to_thread(_count_vectors)

    return {
        "active_chat_sessions": active_sessions,
        "total_vector_collections": num_collections,
        "total_vector_chunks": total_vectors,
    }


async def generate_api_key(app_name: str) -> dict:
    raw_key = secrets.token_urlsafe(32)
    full_key = f"praxis_{raw_key}"
    await store_api_key(full_key, app_name)
    await log_event("KEY_GENERATED", {"app_name": app_name})
    logger.info(f"Generated new API Key for app: {app_name}")
    return {"app_name": app_name, "api_key": full_key, "message": "Store this key safely. It will not be shown again."}


async def revoke_api_key(api_key: str) -> dict:
    deleted = await remove_api_key(api_key)
    if not deleted:
        raise HTTPException(status_code=404, detail="API Key not found.")
    await log_event("KEY_REVOKED", {"key_preview": api_key[:14] + "..."})
    logger.info("Revoked an API Key.")
    return {"status": "success", "message": "API Key permanently revoked."}


async def list_api_keys() -> dict:
    entries = await list_all_api_keys()
    return {"total_keys": len(entries), "keys": entries}


async def delete_app_sessions(app_name: str) -> dict:
    """Force-expires all Redis sessions belonging to a specific app."""
    count = await delete_all_app_sessions(app_name)
    await log_event("SESSION_WIPED", {"sessions_deleted": count}, app_name=app_name)
    logger.info(f"Wiped {count} session(s) for app: {app_name}")
    return {"status": "success", "sessions_deleted": count, "app_name": app_name}


async def get_app_usage(app_name: str) -> dict:
    return await get_usage(app_name)


async def get_all_usage() -> dict:
    app_names = await get_all_app_names()
    return {"apps": [await get_usage(name) for name in app_names]}


async def get_gpu() -> dict:
    return await get_gpu_status()


async def reset_gpu() -> dict:
    result = await reset_gpu_counter()
    await log_event("GPU_RESET", {"reason": "manual admin reset"})
    return result


async def get_global_audit(limit: int = 100, offset: int = 0) -> dict:
    events = await get_audit_log(app_name=None, limit=limit, offset=offset)
    return {"total_returned": len(events), "events": events}


async def get_app_audit(app_name: str, limit: int = 100, offset: int = 0) -> dict:
    events = await get_audit_log(app_name=app_name, limit=limit, offset=offset)
    return {"app_name": app_name, "total_returned": len(events), "events": events}
