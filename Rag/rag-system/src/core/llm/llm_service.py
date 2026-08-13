"""
LLM service — wraps ChatOllama for use in LCEL chains.

To swap to a different provider (OpenAI, Anthropic, …), replace the body of
`get_llm()` only.  Nothing else in the pipeline changes.
"""
import logging
from functools import lru_cache
# pyrefly: ignore [missing-import]
from langchain_ollama import ChatOllama
# pyrefly: ignore [missing-import]
from langchain_core.language_models import BaseChatModel
from src.config.settings import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    """
    Return a cached ChatOllama instance.

    Configuration (from .env):
      LLM_BASE_URL  — Ollama server URL (default: http://localhost:11434)
      LLM_MODEL     — model tag       (default: llama3)
    """
    logger.info(
        f"Loading LLM: model={settings.LLM_MODEL} "
        f"base_url={settings.LLM_BASE_URL}"
    )
    return ChatOllama(
        base_url=settings.LLM_BASE_URL,
        model=settings.LLM_MODEL,
        temperature=0.1,          # low temp → factual, grounded answers
        num_predict=1024,         # max tokens to generate
    )


@lru_cache(maxsize=1)
def get_judge_llm() -> BaseChatModel:
    """
    Return the cached model used for policy judgement.

    Separate from `get_llm()` on purpose: JUDGE_MODEL is deliberately larger than
    LLM_MODEL, and temperature is pinned to 0. A compliance verdict that varies
    between two identical requests cannot be defended in an audit.
    """
    logger.info(f"Loading judge LLM: model={settings.JUDGE_MODEL}")
    return ChatOllama(
        base_url=settings.LLM_BASE_URL,
        model=settings.JUDGE_MODEL,
        temperature=0.0,
        num_predict=768,
    )
