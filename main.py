try:
    from src import config  # noqa: F401 — loads .env and parses settings (single source of truth)
except Exception as e:
    raise RuntimeError(f"ERROR: Could not load configuration: {e}")

from contextlib import asynccontextmanager
from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded
from src.utils.system.limiter import limiter
from slowapi.extension import _rate_limit_exceeded_handler
from src.routes.main_router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.utils.concurrency import init_gpu
    await init_gpu()
    yield


app = FastAPI(
    title="Praixis - Business logic based API",
    description="Custom decoupled business logic API powered by a local OpenAI-compatible LLM.",
    version="1.0.0",
    docs_url="/swagger/docs",
    redoc_url="/docs",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
