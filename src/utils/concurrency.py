import os
from contextlib import asynccontextmanager
from src.utils.memory import redis_client

_SLOTS = int(os.getenv("GPU_CONCURRENCY", "2"))
_GPU_KEY = "gpu:in_use"


class GPUBusyError(Exception):
    """Raised when all GPU slots are occupied and a new request cannot be served."""
    pass


@asynccontextmanager
async def gpu_slot():
    """Async context manager for non-streaming LLM calls. Raises GPUBusyError immediately if full."""
    count = await redis_client.incr(_GPU_KEY)
    if count > _SLOTS:
        await redis_client.decr(_GPU_KEY)
        raise GPUBusyError("All GPU slots are occupied. Please try again shortly.")
    try:
        yield
    finally:
        await redis_client.decr(_GPU_KEY)


async def acquire_gpu_slot() -> None:
    """
    Eagerly acquires a GPU slot for a streaming response.
    Must be paired with release_gpu_slot() in a generator finally-block.
    Raises GPUBusyError if all slots are occupied.
    """
    count = await redis_client.incr(_GPU_KEY)
    if count > _SLOTS:
        await redis_client.decr(_GPU_KEY)
        raise GPUBusyError("All GPU slots are occupied. Please try again shortly.")


async def release_gpu_slot() -> None:
    """Releases a slot previously acquired with acquire_gpu_slot()."""
    await redis_client.decr(_GPU_KEY)


async def get_gpu_status() -> dict:
    """Returns current GPU slot usage from Redis."""
    count = await redis_client.get(_GPU_KEY)
    in_use = int(count or 0)
    return {"slots_total": _SLOTS, "slots_in_use": in_use, "slots_available": max(0, _SLOTS - in_use)}


async def reset_gpu_counter() -> dict:
    """Resets the GPU slot counter to zero. Use only when a crash left the counter stale."""
    await redis_client.set(_GPU_KEY, 0)
    return {"status": "success", "message": "GPU slot counter reset to 0.", "slots_total": _SLOTS}
