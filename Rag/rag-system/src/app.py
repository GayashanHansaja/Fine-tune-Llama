"""
app.py — FastAPI application entry point.

Startup sequence:
  1. Load settings from .env
  2. Report the policy-gate configuration
  3. Start accepting requests

The corpus is not loaded here — see `python -m scripts.seed_qdrant_policies`.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.policy_routes import router as policy_router
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
        f"Starting policy gate | llm={settings.LLM_MODEL} "
        f"| judge={settings.JUDGE_MODEL} | embed={settings.EMBED_MODEL}"
    )
    logger.info(
        f"Policy collection={settings.POLICY_COLLECTION} "
        f"| fail_closed={settings.POLICY_FAIL_CLOSED}"
    )

    # The corpus is loaded by `python -m scripts.seed_qdrant_policies`, not here.
    # Seeding on boot re-ingested its source file into the collection on every
    # restart, and an unbounded pile of duplicate chunks in a collection the gate
    # reads from is not something a policy decision should be exposed to.

    yield  # ← server is live here

    logger.info("Policy gate shutting down — goodbye!")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="ERP Finance Policy Gate",
    description=(
        "Decides whether a natural-language finance request is permitted under "
        "company policy, and returns what the caller needs to execute it.\n\n"
        "**Pipeline:** `prompt → intent → retrieve rules → deterministic checks "
        "→ judge → verdict`\n\n"
        "This service does not execute anything. `POST /api/policy/evaluate` "
        "returns a decision, the proposed action, the clauses it rests on, and "
        "any conditions the caller must satisfy first."
    ),
    version="2.0.0",
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

app.include_router(policy_router)


# ── Health endpoint ───────────────────────────────────────────────────────────

@app.get("/health", tags=["System"], summary="Health check")
def health():
    """
    Current configuration and policy-corpus size.

    Reports the policy collection specifically: the gate is only as good as the
    rules it can see, and a collection that is reachable but empty would
    otherwise look identical to a healthy one.
    """
    from src.core.policy.policy_retriever import get_policy_retriever

    try:
        chunks = get_policy_retriever().corpus_size()
        store = "ok" if chunks else "empty"
    except Exception as exc:  # noqa: BLE001 — health must report, not raise
        chunks, store = 0, f"unreachable: {type(exc).__name__}"

    return {
        "status": "ok" if store == "ok" else "degraded",
        "policy_store": store,
        "policy_collection": settings.POLICY_COLLECTION,
        "policy_chunks": chunks,
        "llm_model": settings.LLM_MODEL,
        "judge_model": settings.JUDGE_MODEL,
        "embed_model": settings.EMBED_MODEL,
        "fail_closed": settings.POLICY_FAIL_CLOSED,
    }
