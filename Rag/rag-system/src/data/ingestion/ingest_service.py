"""
IngestService — splits raw text into chunks, embeds, and stores via IRetriever.

Responsibilities:
  • Accept raw text strings or file paths
  • Chunk with RecursiveCharacterTextSplitter (configurable size + overlap)
  • Delegate storage to whatever IRetriever is active (mock or qdrant)
"""
import logging
import os
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document as LCDocument

from src.core.retriever.retriever_factory import get_retriever
from src.config.settings import settings

logger = logging.getLogger(__name__)


def _get_splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )


def ingest_text(text: str, source: str = "manual") -> int:
    """
    Split `text` into chunks and ingest them into the active vector store.

    Returns the number of chunks ingested.
    """
    splitter = _get_splitter()
    docs: list[LCDocument] = splitter.create_documents(
        texts=[text],
        metadatas=[{"source": source}],
    )
    get_retriever().ingest(docs)
    logger.info(f"Ingested {len(docs)} chunks | source='{source}'")
    return len(docs)


def ingest_file(file_path: str) -> int:
    """
    Read a text file and ingest its contents.

    Returns the number of chunks ingested.
    """
    abs_path = os.path.abspath(file_path)
    logger.info(f"Ingesting file: {abs_path}")
    with open(abs_path, encoding="utf-8") as fh:
        text = fh.read()
    return ingest_text(text, source=abs_path)
