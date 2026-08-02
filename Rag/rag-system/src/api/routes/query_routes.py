"""
Query routes — registers /api/query and /api/ingest endpoints.
"""
# pyrefly: ignore [missing-import]
from fastapi import APIRouter

from src.api.controller.query_controller import handle_query, handle_ingest
from src.types.document import (
    QueryRequest,
    QueryResponse,
    IngestRequest,
    IngestResponse,
)

router = APIRouter(prefix="/api", tags=["RAG"])


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Run the RAG pipeline",
    description=(
        "Embed the question, retrieve relevant chunks, build a grounded prompt, "
        "call the local LLM, and return the answer with source references."
    ),
)
async def query(request: QueryRequest) -> QueryResponse:
    return await handle_query(request)


@router.post(
    "/ingest",
    response_model=IngestResponse,
    summary="Ingest text into the vector store",
    description=(
        "Split the provided text into chunks, embed each chunk, "
        "and store them in the active vector backend (mock or Qdrant)."
    ),
)
async def ingest(request: IngestRequest) -> IngestResponse:
    return await handle_ingest(request)
