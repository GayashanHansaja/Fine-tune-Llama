#pyrefly: ignore [missing-import]
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Retriever backend
    RETRIEVER: str = "mock"         # "mock" | "qdrant"

    # Ollama
    LLM_BASE_URL: str = "http://localhost:11434"
    LLM_MODEL: str = "llama3"
    EMBED_MODEL: str = "nomic-embed-text"
    EMBED_DIMENSION: int = 768      # must match the embedding model output size


    # Qdrant
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "rag_docs"
    QDRANT_API_KEY: str | None = None

    # Pipeline tuning
    APP_PORT: int = 8000
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    TOP_K: int = 4

    # Policy gate
    POLICY_COLLECTION: str = "policy_docs"   # kept separate from QDRANT_COLLECTION
    POLICY_TOP_K: int = 20                   # recall over precision — missing a rule allows it
    POLICY_CHUNK_SIZE: int = 1200            # large enough to keep a whole rule intact
    POLICY_CHUNK_OVERLAP: int = 200
    JUDGE_MODEL: str = "llama3.1:8b"         # deliberately larger than LLM_MODEL
    POLICY_FAIL_CLOSED: bool = True          # judge error/timeout ⇒ DENY, never allow

    # Tool provider backend
    TOOL_PROVIDER: str = "mock"              # "mock" | "mcp"
    MCP_SERVER_URL: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Convenience singleton — import `settings` anywhere
settings: Settings = get_settings()
