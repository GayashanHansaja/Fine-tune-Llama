"""
QueryController — handles HTTP request/response logic.
Keeps route handlers thin; all business logic lives in services.
"""
import logging
# pyrefly: ignore [missing-import]
from fastapi import HTTPException

from src.core.rag.rag_service import get_rag_service
from src.data.ingestion.ingest_service import ingest_text
from src.types.document import (
    QueryRequest,
    QueryResponse,
    IngestRequest,
    IngestResponse,
)

logger = logging.getLogger(__name__)


async def handle_query(request: QueryRequest) -> QueryResponse:
    """Run the full RAG pipeline for a user question."""
    try:
        rag = get_rag_service()
        return await rag.query(question=request.question, top_k=request.top_k)
    except Exception as exc:
        logger.exception("Query pipeline error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def handle_ingest(request: IngestRequest) -> IngestResponse:
    """Chunk and ingest raw text into the active vector store."""
    try:
        count = ingest_text(request.text, source=request.source)
        return IngestResponse(
            ingested=count,
            message=f"Successfully ingested {count} chunk(s) from '{request.source}'.",
        )
    except Exception as exc:
        logger.exception("Ingest error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
