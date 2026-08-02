"""
IRetriever — the single abstraction that makes the vector layer swappable.

Any concrete retriever (Mock, Qdrant, Pinecone, Weaviate …) must implement
this interface.  The rest of the pipeline only knows about IRetriever.
"""
from abc import ABC, abstractmethod
# pyrefly: ignore [missing-import]
from langchain_core.documents import Document
# pyrefly: ignore [missing-import]
from langchain_core.retrievers import BaseRetriever


class IRetriever(ABC):

    @abstractmethod
    def ingest(self, docs: list[Document]) -> None:
        """
        Embed and persist a list of LangChain Documents.

        Called by IngestService.  Implementations must store the vectors so
        that subsequent `get_retriever()` calls can find them.
        """
        ...

    @abstractmethod
    def get_retriever(self, top_k: int = 4) -> BaseRetriever:
        """
        Return a LangChain-compatible retriever for use inside LCEL chains.

        The returned object is passed directly into:
            retriever | format_docs
        """
        ...

    @abstractmethod
    def doc_count(self) -> int:
        """Number of chunks currently stored."""
        ...
