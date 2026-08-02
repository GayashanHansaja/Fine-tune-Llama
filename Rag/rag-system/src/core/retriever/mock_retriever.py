"""
MockRetriever — in-memory vector store powered by LangChain's InMemoryVectorStore.

• Zero external dependencies (no Docker, no network calls beyond Ollama)
• Uses cosine similarity under the hood (LangChain default)
• Identical API to QdrantRetriever — swap by changing RETRIEVER in .env
"""
import logging
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.vectorstores.in_memory import InMemoryVectorStore
from src.core.retriever.retriever_interface import IRetriever
from src.core.embeddings.embedding_service import get_embeddings

logger = logging.getLogger(__name__)


class MockRetriever(IRetriever):
    """
    Default retriever — stores everything in process memory.
    Data is lost on restart (intentional for a dev/test backend).
    """

    def __init__(self) -> None:
        self._embeddings = get_embeddings()
        self._store: InMemoryVectorStore = InMemoryVectorStore(
            embedding=self._embeddings
        )
        self._count: int = 0
        logger.info("MockRetriever ready (in-memory, no persistence)")

    # ── IRetriever ────────────────────────────────────────────────────────────

    def ingest(self, docs: list[Document]) -> None:
        if not docs:
            return
        self._store.add_documents(docs)
        self._count += len(docs)
        logger.info(f"[MockRetriever] ingested {len(docs)} chunks | total={self._count}")

    def get_retriever(self, top_k: int = 4) -> BaseRetriever:
        return self._store.as_retriever(
            search_type="similarity",
            search_kwargs={"k": top_k},
        )

    def doc_count(self) -> int:
        return self._count
