import asyncio
import os
from contextlib import asynccontextmanager
from src.utils.memory import redis_client

_SLOTS = int(os.getenv("GPU_CONCURRENCY", "2"))
_WAIT_TIMEOUT = float(os.getenv("GPU_WAIT_TIMEOUT", "30"))
_GPU_KEY = "gpu:in_use"

_semaphore = asyncio.Semaphore(_SLOTS)


class GPUBusyError(Exception):
    """Raised when all GPU slots remain occupied past GPU_WAIT_TIMEOUT seconds."""
    pass


async def _acquire() -> None:
    try:
        await asyncio.wait_for(_semaphore.acquire(), timeout=_WAIT_TIMEOUT)
    except asyncio.TimeoutError:
        raise GPUBusyError("All GPU slots are occupied. Please try again shortly.")


@asynccontextmanager
async def gpu_slot():
    """Blocks until a slot is free (up to GPU_WAIT_TIMEOUT seconds), then holds it for the duration."""
    await _acquire()
    await redis_client.incr(_GPU_KEY)
    try:
        yield
    finally:
        await redis_client.decr(_GPU_KEY)
        _semaphore.release()


async def acquire_gpu_slot() -> None:
    """
    Blocks until a slot is free (up to GPU_WAIT_TIMEOUT seconds).
    Used for streaming responses; must be paired with release_gpu_slot() in a finally block.
    """
    await _acquire()
    await redis_client.incr(_GPU_KEY)


async def release_gpu_slot() -> None:
    """Releases a slot previously acquired with acquire_gpu_slot()."""
    _semaphore.release()
    await redis_client.decr(_GPU_KEY)


async def get_gpu_status() -> dict:
    """Returns current GPU slot usage from Redis."""
    count = await redis_client.get(_GPU_KEY)
    in_use = int(count or 0)
    return {"slots_total": _SLOTS, "slots_in_use": in_use, "slots_available": max(0, _SLOTS - in_use)}


async def reset_gpu_counter() -> dict:
    """Resets the GPU slot counter and semaphore to zero. Use only when a crash left the counter stale."""
    global _semaphore
    _semaphore = asyncio.Semaphore(_SLOTS)
    await redis_client.set(_GPU_KEY, 0)
    return {"status": "success", "message": "GPU slot counter reset to 0.", "slots_total": _SLOTS}
