import asyncio

from fastembed import TextEmbedding

from src.config import EMBEDDING_MODEL as _EMBEDDING_MODEL

_embedder: TextEmbedding | None = None


def _get_embedder() -> TextEmbedding:
    global _embedder
    if _embedder is None:
        _embedder = TextEmbedding(model_name=_EMBEDDING_MODEL)
    return _embedder


def embed(texts: list[str]) -> list[list[float]]:
    return [e.tolist() for e in _get_embedder().embed(texts)]


async def get_embedding(text: str) -> list[float]:
    result = await asyncio.to_thread(embed, [text])
    return result[0]
