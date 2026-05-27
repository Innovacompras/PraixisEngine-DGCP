import asyncio

from fastembed import TextEmbedding

from src.config import EMBEDDING_MODEL as _EMBEDDING_MODEL

_raw_embedder = TextEmbedding(model_name=_EMBEDDING_MODEL)


def _embed(texts: list[str]) -> list[list[float]]:
    return [emb.tolist() for emb in _raw_embedder.embed(texts)]


async def get_embedding(text: str) -> list[float]:
    result = await asyncio.to_thread(_embed, [text])
    return result[0]
