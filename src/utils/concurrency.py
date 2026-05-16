import os
from contextlib import asynccontextmanager

_SLOTS = int(os.getenv("GPU_CONCURRENCY", "2"))
_in_use: int = 0


class GPUBusyError(Exception):
    """Raised when all GPU slots are occupied and a new request cannot be served."""
    pass


@asynccontextmanager
async def gpu_slot():
    """Async context manager for non-streaming LLM calls. Raises GPUBusyError immediately if full."""
    global _in_use
    if _in_use >= _SLOTS:
        raise GPUBusyError("All GPU slots are occupied. Please try again shortly.")
    _in_use += 1
    try:
        yield
    finally:
        _in_use -= 1


async def acquire_gpu_slot() -> None:
    """
    Eagerly acquires a GPU slot for a streaming response.

    Must be paired with release_gpu_slot() in a generator finally-block.
    Raises GPUBusyError if all slots are occupied.
    """
    global _in_use
    if _in_use >= _SLOTS:
        raise GPUBusyError("All GPU slots are occupied. Please try again shortly.")
    _in_use += 1


async def release_gpu_slot() -> None:
    """Releases a slot previously acquired with acquire_gpu_slot()."""
    global _in_use
    _in_use -= 1
