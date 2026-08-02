"""
QdrantRetriever — production vector store backed by Qdrant.

Activation:  set  RETRIEVER=qdrant  in .env  (no code changes needed).
The collection is auto-created on first use.

Prerequisites:
  • Qdrant running at QDRANT_URL  (docker-compose up  or the other developer's instance)
  • The embedding model dimension must match EMBED_DIMENSION in .env
    Default: nomic-embed-text → 768
"""
import logging
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_qdrant import QdrantVectorStore
from qdrant_client.http.models import Distance, VectorParams

from src.core.retriever.retriever_interface import IRetriever
from src.core.embeddings.embedding_service import get_embeddings
from src.config.settings import settings
from src.config.qdrant_client import get_qdrant_client

logger = logging.getLogger(__name__)


class QdrantRetriever(IRetriever):
    """
    Production retriever — persists vectors in Qdrant.
    Drop-in replacement for MockRetriever.
    """

    def __init__(self) -> None:
        self._embeddings = get_embeddings()
        self._client = get_qdrant_client()
        self._collection = settings.QDRANT_COLLECTION
        self._ensure_collection()

        self._store = QdrantVectorStore(
            client=self._client,
            collection_name=self._collection,
            embedding=self._embeddings,
        )
        logger.info(
            f"QdrantRetriever ready | collection={self._collection} "
            f"url={settings.QDRANT_URL}"
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _ensure_collection(self) -> None:
        """Create the Qdrant collection if it doesn't exist yet."""
        existing = {c.name for c in self._client.get_collections().collections}
        if self._collection not in existing:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=settings.EMBED_DIMENSION,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(f"Created Qdrant collection: '{self._collection}'")
        else:
            logger.info(f"Using existing Qdrant collection: '{self._collection}'")

    # ── IRetriever ────────────────────────────────────────────────────────────

    def ingest(self, docs: list[Document]) -> None:
        if not docs:
            return
        self._store.add_documents(docs)
        logger.info(f"[QdrantRetriever] ingested {len(docs)} chunks")

    def get_retriever(self, top_k: int = 4) -> BaseRetriever:
        return self._store.as_retriever(
            search_type="similarity",
            search_kwargs={"k": top_k},
        )

    def doc_count(self) -> int:
        try:
            info = self._client.get_collection(self._collection)
            return info.points_count or 0
        except Exception:
            return -1
