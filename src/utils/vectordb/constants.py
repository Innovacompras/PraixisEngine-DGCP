# ── Schema DDL ────────────────────────────────────────────────────────────────

CREATE_EXTENSION = "CREATE EXTENSION IF NOT EXISTS vector"
CREATE_UNACCENT = "CREATE EXTENSION IF NOT EXISTS unaccent"

# Requires .format(dims=EMBEDDING_DIMS) at the call site.
CREATE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS chunks (
        id          TEXT PRIMARY KEY,
        app         TEXT NOT NULL,
        collection  TEXT NOT NULL,
        source      TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        content     TEXT NOT NULL,
        embedding   vector({dims}),
        tsv         tsvector
    );

    CREATE INDEX IF NOT EXISTS chunks_app_col_idx
        ON chunks (app, collection);
    CREATE INDEX IF NOT EXISTS chunks_source_idx
        ON chunks (app, collection, source, chunk_index);
    CREATE INDEX IF NOT EXISTS chunks_fts_idx
        ON chunks USING gin (tsv);
    CREATE INDEX IF NOT EXISTS chunks_hnsw_idx
        ON chunks USING hnsw (embedding vector_cosine_ops);
"""

# ── Health ────────────────────────────────────────────────────────────────────

PING = "SELECT 1"

# ── Admin ─────────────────────────────────────────────────────────────────────

ALL_COLLECTIONS_ADMIN = """
    SELECT app, collection, COUNT(*) AS chunk_count
    FROM chunks
    GROUP BY app, collection
    ORDER BY app, collection
"""

VECTOR_STATS = """
    SELECT
        COUNT(DISTINCT app || ':' || collection) AS cols,
        COUNT(*) AS chunks
    FROM chunks
"""

# ── Collections ───────────────────────────────────────────────────────────────

LIST_COLLECTIONS = (
    "SELECT DISTINCT collection FROM chunks WHERE app = $1 ORDER BY collection"
)

LIST_FILES = (
    "SELECT DISTINCT source FROM chunks WHERE app = $1 AND collection = $2 ORDER BY source"
)

COLLECTION_EXISTS = (
    "SELECT 1 FROM chunks WHERE app = $1 AND collection = $2 LIMIT 1"
)

DELETE_COLLECTION = "DELETE FROM chunks WHERE app = $1 AND collection = $2"

DELETE_FILE = "DELETE FROM chunks WHERE app = $1 AND collection = $2 AND source = $3"

# ── Ingestion ─────────────────────────────────────────────────────────────────

INSERT_CHUNK = """
    INSERT INTO chunks (id, app, collection, source, chunk_index, content, embedding, tsv)
    VALUES ($1, $2, $3, $4, $5, $6, $7, to_tsvector('simple', unaccent($6)))
"""

# ── Retrieval ─────────────────────────────────────────────────────────────────

FULL_DOCUMENT = """
    SELECT content FROM chunks
    WHERE app = $1 AND collection = $2 AND source = $3
    ORDER BY chunk_index
"""

# Hybrid RRF: dense cosine + sparse FTS merged with Reciprocal Rank Fusion.
# $1=embedding  $2=app  $3=collection  $4=fetch_limit  $5=question
# $6=source_filter (NULL = no filter)  $7=final_limit
HYBRID_SEARCH = """
WITH semantic AS (
    SELECT id, source, content, chunk_index,
           ROW_NUMBER() OVER (ORDER BY embedding <=> $1::vector) AS rank
    FROM chunks
    WHERE app = $2 AND collection = $3
      AND ($6::text IS NULL OR source = $6::text)
    ORDER BY embedding <=> $1::vector
    LIMIT $4
),
keyword AS (
    SELECT id, source, content, chunk_index,
           ROW_NUMBER() OVER (ORDER BY ts_rank(tsv, query) DESC) AS rank
    FROM chunks, websearch_to_tsquery('simple', unaccent($5)) AS query
    WHERE app = $2 AND collection = $3
      AND ($6::text IS NULL OR source = $6::text)
      AND tsv @@ query
    ORDER BY ts_rank(tsv, query) DESC
    LIMIT $4
),
combined AS (
    SELECT
        id,
        COALESCE(s.source,      k.source)      AS source,
        COALESCE(s.content,     k.content)     AS content,
        COALESCE(s.chunk_index, k.chunk_index) AS chunk_index,
        COALESCE(1.0 / (60.0 + s.rank), 0.0)
            + COALESCE(1.0 / (60.0 + k.rank), 0.0) AS rrf_score
    FROM semantic s
    FULL OUTER JOIN keyword k USING (id)
)
SELECT source, content, chunk_index, rrf_score
FROM combined
ORDER BY rrf_score DESC
LIMIT $7
"""

# Fetch a contiguous slice of chunks from one document for window expansion.
# $1=app  $2=collection  $3=source  $4=index_low  $5=index_high
WINDOW_CHUNKS = """
    SELECT content
    FROM chunks
    WHERE app = $1 AND collection = $2 AND source = $3
      AND chunk_index BETWEEN $4 AND $5
    ORDER BY chunk_index
"""
