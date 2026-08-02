"""
Embedding service — wraps OllamaEmbeddings.
Swap the implementation here without touching anything else in the pipeline.
"""
from functools import lru_cache
# pyrefly: ignore [missing-import]
from langchain_ollama import OllamaEmbeddings
# pyrefly: ignore [missing-import]
from langchain_core.embeddings import Embeddings
from src.config.settings import settings
import logging

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_embeddings() -> Embeddings:
    """
    Return a cached Embeddings instance.

    Default: OllamaEmbeddings with `nomic-embed-text`.
    To swap (e.g., to OpenAI), replace this function's body only.
    """
    logger.info(
        f"Loading embeddings: model={settings.EMBED_MODEL} "
        f"base_url={settings.LLM_BASE_URL}"
    )
    return OllamaEmbeddings(
        base_url=settings.LLM_BASE_URL,
        model=settings.EMBED_MODEL,
    )
