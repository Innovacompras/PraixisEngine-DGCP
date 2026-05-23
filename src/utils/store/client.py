import redis.asyncio as aioredis
from src.config import REDIS_URL

redis_client = aioredis.Redis.from_url(REDIS_URL, decode_responses=True)
