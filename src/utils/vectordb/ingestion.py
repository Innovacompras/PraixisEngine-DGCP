import asyncio
import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.utils.vectordb.pool import get_pool
from src.utils.vectordb.embeddings import embed
from src.utils.vectordb.constants import DELETE_FILE, INSERT_CHUNK


async def add_file_to_rag_db(
    text: str,
    collection_name: str,
    filename: str,
    app_name: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 150,
) -> str:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", r"(?<=\. )", " ", ""],
        is_separator_regex=True,
    )
    chunks = splitter.split_text(text)
    # Guard against silently wiping the existing version if the splitter
    # returns nothing. The transaction below DELETEs before INSERTing, and an
    # empty executemany is a no-op, so without this check a "broken" re-upload
    # would drop the prior good copy.
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
