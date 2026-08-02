# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field
from typing import Any
import uuid


# ─── Core domain objects ──────────────────────────────────────────────────────

class DocumentMeta(BaseModel):
    """Metadata attached to a stored chunk."""
    source: str = "unknown"
    chunk_index: int = 0
    extra: dict[str, Any] = Field(default_factory=dict)


# ─── API request / response contracts ────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="The question to answer")
    top_k: int = Field(default=4, ge=1, le=20, description="Number of chunks to retrieve")


class SourceChunk(BaseModel):
    content: str
    metadata: dict[str, Any]


class QueryResponse(BaseModel):
    question: str
    answer: str
    sources: list[SourceChunk]


class IngestRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Raw text to ingest into the vector store")
    source: str = Field(default="manual", description="Label / filename for this content")


class IngestResponse(BaseModel):
    ingested: int
    message: str
