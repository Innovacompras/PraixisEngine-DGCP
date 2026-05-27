"""Single source of truth for configuration.

Every environment variable is read and parsed here exactly once. Import the
parsed values from this module instead of calling ``os.getenv`` elsewhere.
Importing this module also loads the ``.env`` file, so it is self-sufficient
regardless of import order.
"""
import os

from dotenv import find_dotenv, load_dotenv


def _load_dotenv() -> None:
    """Loads the .env file if present.

    A missing .env is fine — vars may be injected directly (Docker, k8s, CI).
    A present-but-unloadable .env is a hard error.
    """
    env_file = find_dotenv()
    if not env_file:
        return
    if not load_dotenv(env_file):
        raise RuntimeError(f"Found .env at '{env_file}' but failed to load it.")


_load_dotenv()

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# --- LLM backend ---
AI_API_URL: str = os.getenv("AI_API_URL", "http://localhost:8081")
AI_API_KEY: str = os.getenv("AI_API_KEY", "")
MODEL_NAME: str = os.getenv("MODEL_NAME", "gemma-api-test")

# --- Redis & sessions ---
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SESSION_TTL: int = int(os.getenv("SESSION_TTL", "86400"))          # seconds
MAX_HISTORY_PAIRS: int = int(os.getenv("MAX_HISTORY_PAIRS", "20")) # user+assistant turns kept

# --- GPU concurrency ---
GPU_CONCURRENCY: int = int(os.getenv("GPU_CONCURRENCY", "2"))
GPU_WAIT_TIMEOUT: float = float(os.getenv("GPU_WAIT_TIMEOUT", "30"))
CHUNK_CONCURRENCY: int = int(os.getenv("CHUNK_CONCURRENCY", "4"))

# --- Vector store ---
POSTGRES_URL: str = os.getenv("POSTGRES_URL", "postgresql://praixis:praixis@localhost:5432/praixis")
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
EMBEDDING_DIMS: int = int(os.getenv("EMBEDDING_DIMS", "384"))

# --- Admin auth (no defaults — must be set in the environment) ---
ADMIN_USERNAME: str | None = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD: str | None = os.getenv("ADMIN_PASSWORD")
