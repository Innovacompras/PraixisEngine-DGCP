import asyncio
import uuid

from src.utils.vectordb.pool import get_pool
from src.utils.vectordb.embeddings import embed
from src.utils.vectordb.chunking import character_chunk, semantic_chunk
from src.utils.vectordb.constants import DELETE_FILE, INSERT_CHUNK


async def add_file_to_rag_db(
    text: str,
    collection_name: str,
    filename: str,
    app_name: str,
    chunk_size: int = 2000,
    chunk_overlap: int = 150,
    chunking_strategy: str = "semantic",
) -> str:
    if chunking_strategy == "semantic":
        chunks = await asyncio.to_thread(semantic_chunk, text, max_chunk_chars=chunk_size)
    else:
        chunks = await asyncio.to_thread(character_chunk, text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    if not chunks:
        raise ValueError("Document produced no chunks; nothing to ingest.")
    embeddings = await asyncio.to_thread(embed, chunks)

    rows = [
        (f"{filename}_{uuid.uuid4().hex[:6]}", app_name, collection_name, filename, i, chunk, emb)
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]

    async with get_pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute(DELETE_FILE, app_name, collection_name, filename)
            await conn.executemany(INSERT_CHUNK, rows)
    return collection_name
