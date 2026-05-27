import redis.asyncio as aioredis
from src.config import REDIS_URL

redis_client = aioredis.Redis.from_url(REDIS_URL, decode_responses=True)

# Dedicated client for the GPU slot queue. Each waiting BLPOP holds a
# connection for up to GPU_WAIT_TIMEOUT seconds; isolating that traffic on its
# own pool keeps sessions/audit/usage/health-check ops from queueing behind it
# under sustained contention.
gpu_redis_client = aioredis.Redis.from_url(REDIS_URL, decode_responses=True)
