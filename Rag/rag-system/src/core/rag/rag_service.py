"""
RagService — orchestrates the full pipeline using LangChain Expression Language (LCEL).

Pipeline:
    question
        ↓
    [retriever]  →  relevant chunks  →  format as context string
        ↓
    [prompt]     →  system + context + question
        ↓
    [LLM]        →  AI message
        ↓
    [parser]     →  plain string answer
"""
import logging
from langchain_core.documents import Document as LCDocument
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

from src.core.retriever.retriever_factory import get_retriever
from src.core.llm.llm_service import get_llm
from src.core.prompt.prompt_builder import build_rag_prompt
from src.config.settings import settings
from src.types.document import QueryResponse, SourceChunk

logger = logging.getLogger(__name__)


def _format_docs(docs: list[LCDocument]) -> str:
    """Concatenate page contents with a clear separator for the prompt."""
    return "\n\n---\n\n".join(
        f"[Source: {doc.metadata.get('source', 'unknown')}]\n{doc.page_content}"
        for doc in docs
    )


class RagService:
    """
    Thin orchestrator — wires embeddings → retrieval → prompt → LLM together.
    Depends only on IRetriever, not on any concrete vector store.
    """

    def __init__(self) -> None:
        self._retriever_impl = get_retriever()
        self._llm = get_llm()
        self._prompt = build_rag_prompt()
        logger.info("RagService initialized")

    def _lcel_chain(self, top_k: int):
        """Build the LCEL chain for a given top_k."""
        lc_retriever = self._retriever_impl.get_retriever(top_k=top_k)
        return (
            {
                "context": lc_retriever | _format_docs,
                "question": RunnablePassthrough(),
            }
            | self._prompt
            | self._llm
            | StrOutputParser()
        )

    async def query(self, question: str, top_k: int | None = None) -> QueryResponse:
        k = top_k if top_k is not None else settings.TOP_K
        logger.info(f"RAG query: top_k={k} | question='{question[:80]}'")

        # Retrieve source chunks separately so we can return them
        lc_retriever = self._retriever_impl.get_retriever(top_k=k)
        source_docs: list[LCDocument] = await lc_retriever.ainvoke(question)

        # Run the full LCEL chain for the answer
        chain = self._lcel_chain(top_k=k)
        answer: str = await chain.ainvoke(question)

        sources = [
            SourceChunk(
                content=doc.page_content[:300],   # trim for response payload
                metadata=doc.metadata,
            )
            for doc in source_docs
        ]

        return QueryResponse(answer=answer, sources=sources, question=question)


# ── Singleton ─────────────────────────────────────────────────────────────────
_instance: RagService | None = None


def get_rag_service() -> RagService:
    global _instance
    if _instance is None:
        _instance = RagService()
    return _instance
