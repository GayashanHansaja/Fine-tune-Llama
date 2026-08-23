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
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

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


# ── Demo page ─────────────────────────────────────────────────────────────────

_DEMO_PAGE = Path(__file__).parent / "static" / "demo.html"


@app.get("/demo", tags=["System"], summary="Demo UI", include_in_schema=False)
def demo():
    """
    A single static page for demonstrating the gate by hand.

    Served from this app rather than opened as a file so it shares an origin with
    the API: a `file://` page is treated as a null origin, which CORS cannot
    whitelist. It is a demo surface, not part of the published contract.
    """
    return FileResponse(_DEMO_PAGE)


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

    openrouter = settings.MODEL_PROVIDER.strip().lower() in ("api", "openrouter")

    return {
        "status": "ok" if store == "ok" else "degraded",
        "policy_store": store,
        "policy_collection": settings.POLICY_COLLECTION,
        "policy_chunks": chunks,
        # Which backend is actually live. A deployment configured for OpenRouter
        # with no key still starts, and every request then denies on a failed
        # model call — a failure that reads as strict policy rather than as
        # missing configuration, so it is reported here instead.
        "model_provider": settings.MODEL_PROVIDER,
        "model_credentials": (
            "missing" if openrouter and not settings.API_KEY else "ok"
        ),
        "llm_model": settings.LLM_MODEL,
        "judge_model": settings.JUDGE_MODEL,
        "embed_model": (
            settings.API_EMBED_MODEL if openrouter else settings.EMBED_MODEL
        ),
        "embed_dimension": settings.EMBED_DIMENSION,
        "fail_closed": settings.POLICY_FAIL_CLOSED,
    }
