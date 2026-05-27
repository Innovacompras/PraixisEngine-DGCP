import asyncio
import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.utils.vectordb.pool import _get_pool
from src.utils.vectordb.embeddings import _embed
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
    embeddings = await asyncio.to_thread(_embed, chunks)

    rows = [
        (f"{filename}_{uuid.uuid4().hex[:6]}", app_name, collection_name, filename, i, chunk, emb)
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]

    async with _get_pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute(DELETE_FILE, app_name, collection_name, filename)
            await conn.executemany(INSERT_CHUNK, rows)
    return collection_name
