FROM python:3.13-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies first — this layer is cached and only rebuilt when
# pyproject.toml or uv.lock change, not on every source edit.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev && rm -rf /root/.cache/uv

# Pre-download the fastembed model so the first request is not slow.
# Kept in the dependency layer so it is cached across source-only changes.
RUN uv run python -c "from fastembed import TextEmbedding; list(TextEmbedding(model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2').embed(['warmup']))"

# Copy the application source last so edits don't invalidate the layers above.
COPY . .
RUN uv sync --frozen --no-dev && rm -rf /root/.cache/uv

EXPOSE 8080

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
