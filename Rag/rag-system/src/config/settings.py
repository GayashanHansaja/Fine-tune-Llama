#pyrefly: ignore [missing-import]
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Ollama
    LLM_BASE_URL: str = "http://localhost:11434"
    LLM_MODEL: str = "llama3"
    EMBED_MODEL: str = "nomic-embed-text"
    EMBED_DIMENSION: int = 768      # must match the embedding model output size


    # Qdrant
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "rag_docs"
    QDRANT_API_KEY: str | None = None
    # Seconds. The client default (~5s) is too tight for a hosted cluster —
    # a timed-out read fails the decision closed, so it must not happen routinely.
    QDRANT_TIMEOUT: int = 60

    # Baseline splitter settings. Nothing in the gate uses these — they exist so
    # `scripts.verify_policy_chunking` can reproduce what a general character-window
    # splitter does to a policy clause, which is the comparison that justifies the
    # clause-aware chunker.
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50

    # Policy gate
    POLICY_COLLECTION: str = "policy_docs"   # kept separate from QDRANT_COLLECTION
    POLICY_TOP_K: int = 20                   # recall over precision — missing a rule allows it
    POLICY_CHUNK_SIZE: int = 1200            # large enough to keep a whole rule intact
    POLICY_CHUNK_OVERLAP: int = 200
    JUDGE_MODEL: str = "llama3.1:8b"         # deliberately larger than LLM_MODEL
    POLICY_FAIL_CLOSED: bool = True          # judge error/timeout ⇒ DENY, never allow

    # No tool-provider settings: this service returns a decision, it does not
    # execute. The caller holds the MCP/ERP credentials.

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Convenience singleton — import `settings` anywhere
settings: Settings = get_settings()
