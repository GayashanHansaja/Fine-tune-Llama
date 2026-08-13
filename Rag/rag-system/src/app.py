"""
app.py — FastAPI application entry point.

Startup sequence:
  1. Load settings from .env
  2. Initialise the retriever (mock or qdrant)
  3. Seed the vector store from sample_docs.txt
  4. Start accepting requests
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.policy_routes import router as policy_router
from src.api.routes.query_routes import router
from src.config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)-8s]  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup tasks before the server accepts requests."""
    logger.info(
        f"Starting RAG system | retriever={settings.RETRIEVER} "
        f"| llm={settings.LLM_MODEL} | judge={settings.JUDGE_MODEL} "
        f"| embed={settings.EMBED_MODEL}"
    )
    logger.info(
        f"Policy gate | collection={settings.POLICY_COLLECTION} "
        f"| fail_closed={settings.POLICY_FAIL_CLOSED}"
    )

    # The corpus is loaded by `python -m scripts.seed_qdrant_policies`, not here.
    # Seeding on boot re-ingested sample_docs.txt into the data collection on every
    # restart, and an unbounded pile of duplicate chunks in a collection the gate
    # reads from is not something a policy decision should be exposed to.

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
app.include_router(policy_router)


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
