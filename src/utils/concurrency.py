"""Global GPU concurrency control, enforced via Redis.

The cap is enforced by a Redis list used as a token bucket: acquiring a slot
pops a token (BLPOP, blocks up to GPU_WAIT_TIMEOUT), releasing pushes one
back. Every worker and every container replica shares the same queue, so
GPU_CONCURRENCY is a single global limit regardless of how many processes
are running.
"""
from contextlib import asynccontextmanager

from src.config import GPU_CONCURRENCY as _SLOTS, GPU_WAIT_TIMEOUT as _WAIT_TIMEOUT
from src.utils.store.client import gpu_redis_client as _redis

_GPU_QUEUE_KEY = "gpu:slots"
_GPU_INIT_KEY = "gpu:initialized"


class GPUBusyError(Exception):
    """Raised when no slot frees up within GPU_WAIT_TIMEOUT seconds."""
    pass


async def init_gpu() -> None:
    """Populates the slot queue if it has not been sized for the current GPU_CONCURRENCY.

    Called from the FastAPI lifespan hook on every process start. The sentinel
    key stores the slot count it was last filled with; matching values skip
    the rebuild, so multi-worker and multi-replica deployments do not multiply
    the configured slot count. A mismatch (e.g. GPU_CONCURRENCY changed in
    .env and the container was restarted) triggers a rebuild so config edits
    take effect without a manual ``/gpu/reset`` call.

    A consequence is that slots leaked by a hard crash persist across
    process restarts when GPU_CONCURRENCY is unchanged — recover them with
    ``POST /api/system/gpu/reset``.
    """
    existing = await _redis.get(_GPU_INIT_KEY)
    if existing == str(_SLOTS):
        return
    await _fill_queue()


async def reset_gpu_counter() -> dict:
    """Forcibly rebuilds the queue to exactly GPU_CONCURRENCY tokens.

    Use after a crash leaks slots, or after changing GPU_CONCURRENCY. Any
    in-flight request still holding an old token will push it back on
    release, transiently inflating the queue above the configured size
    until the next acquire drains the surplus.
    """
    await _fill_queue()
    return {"status": "success", "message": "GPU slot counter reset.", "slots_total": _SLOTS}


async def _fill_queue() -> None:
    pipe = _redis.pipeline()
    pipe.delete(_GPU_QUEUE_KEY)
    if _SLOTS > 0:
        pipe.rpush(_GPU_QUEUE_KEY, *(["1"] * _SLOTS))
    pipe.set(_GPU_INIT_KEY, str(_SLOTS))
    await pipe.execute()


async def _acquire() -> None:
    # BLPOP returns (key, value) when a token is popped, or None on timeout.
    result = await _redis.blpop([_GPU_QUEUE_KEY], timeout=_WAIT_TIMEOUT)
    if result is None:
        raise GPUBusyError("All GPU slots are occupied. Please try again shortly.")


async def _release() -> None:
    await _redis.rpush(_GPU_QUEUE_KEY, "1")


@asynccontextmanager
async def gpu_slot():
    """Blocks until a slot is free (up to GPU_WAIT_TIMEOUT seconds), then holds it for the duration."""
    await _acquire()
    try:
        yield
    finally:
        await _release()


async def acquire_gpu_slot() -> None:
    """Blocks until a slot is free (up to GPU_WAIT_TIMEOUT seconds).

    Used by streaming responses that must hold the slot across the entire
    stream; must be paired with ``release_gpu_slot()`` in a finally block.
    """
    await _acquire()


async def release_gpu_slot() -> None:
    """Releases a slot previously acquired with acquire_gpu_slot()."""
    await _release()


async def get_gpu_status() -> dict:
    """Returns current slot usage, computed live from the queue length."""
    available = int(await _redis.llen(_GPU_QUEUE_KEY))
    in_use = max(0, _SLOTS - available)
    return {"slots_total": _SLOTS, "slots_in_use": in_use, "slots_available": available}
