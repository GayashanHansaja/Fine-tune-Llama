"""
app.py — FastAPI application entry point.

Startup sequence:
  1. Load settings from .env
  2. Initialise the retriever (mock or qdrant)
  3. Seed the vector store from sample_docs.txt
  4. Start accepting requests
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.query_routes import router
from src.config.settings import settings
from src.data.ingestion.ingest_service import ingest_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)-8s]  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_SAMPLE_DOCS = os.path.join(
    os.path.dirname(__file__), "data", "documents", "sample_docs.txt"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup tasks before the server accepts requests."""
    logger.info(
        f"Starting RAG system | retriever={settings.RETRIEVER} "
        f"| llm={settings.LLM_MODEL} | embed={settings.EMBED_MODEL}"
    )

    # Seed sample docs on first run
    if os.path.exists(_SAMPLE_DOCS):
        try:
            n = ingest_file(_SAMPLE_DOCS)
            logger.info(f"Seeded {n} chunks from sample_docs.txt")
        except Exception as exc:
            logger.warning(f"Sample doc seeding skipped: {exc}")
    else:
        logger.warning(f"sample_docs.txt not found at {_SAMPLE_DOCS}")

    yield  # ← server is live here

    logger.info("RAG system shutting down — goodbye!")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Modular RAG API",
    description=(
        "A swappable Retrieval-Augmented Generation pipeline.\n\n"
        "**Pipeline:** `query → embed → retrieve → prompt → LLM → answer`\n\n"
        "Switch the vector backend by setting `RETRIEVER=mock|qdrant` in `.env`."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


# ── Health endpoint ───────────────────────────────────────────────────────────

@app.get("/health", tags=["System"], summary="Health check")
def health():
    """Returns current configuration and doc count."""
    from src.core.retriever.retriever_factory import get_retriever
    retriever = get_retriever()
    return {
        "status": "ok",
        "retriever": settings.RETRIEVER,
        "llm_model": settings.LLM_MODEL,
        "embed_model": settings.EMBED_MODEL,
        "docs_in_store": retriever.doc_count(),
    }
