"""
RetrieverFactory — reads RETRIEVER from .env and returns the correct IRetriever.

This is the ONLY place that knows about concrete retriever implementations.
Everything else depends on IRetriever only.

Usage:
    from src.core.retriever.retriever_factory import get_retriever
    retriever = get_retriever()   # singleton
"""
import logging
from functools import lru_cache
from src.core.retriever.retriever_interface import IRetriever
from src.config.settings import settings

logger = logging.getLogger(__name__)

_SUPPORTED = ("mock", "qdrant")


@lru_cache(maxsize=1)
def get_retriever() -> IRetriever:
    """
    Return the configured IRetriever implementation (cached singleton).

    Switch backend:  change  RETRIEVER=mock|qdrant  in .env  →  restart server.
    No code changes required.
    """
    mode = settings.RETRIEVER.lower().strip()
    logger.info(f"RetrieverFactory → selecting backend: '{mode}'")

    if mode not in _SUPPORTED:
        raise ValueError(
            f"Unknown RETRIEVER='{mode}'. "
            f"Supported values: {_SUPPORTED}"
        )

    if mode == "qdrant":
        from src.core.retriever.qdrant_retriever import QdrantRetriever
        return QdrantRetriever()

    # Default → mock
    from src.core.retriever.mock_retriever import MockRetriever
    return MockRetriever()
