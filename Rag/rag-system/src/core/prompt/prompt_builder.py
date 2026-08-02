"""
PromptBuilder — assembles the RAG ChatPromptTemplate.

The template instructs the LLM to:
  • answer ONLY from the provided context
  • admit when it doesn't know rather than hallucinate
  • cite sources when possible
"""
# pyrefly: ignore [missing-import]
from langchain_core.prompts import ChatPromptTemplate

_SYSTEM = """\
You are a knowledgeable assistant that answers questions strictly based on the context provided.

Rules:
1. Use ONLY the information in the context below to answer.
2. If the context does not contain enough information, respond with:
   "I don't have enough information in my knowledge base to answer this question."
3. Do NOT invent facts, figures, or details not present in the context.
4. Be concise and precise. Cite the source when it helps the user.

Context:
{context}
"""

_HUMAN = "{question}"


def build_rag_prompt() -> ChatPromptTemplate:
    """Return the standard RAG ChatPromptTemplate."""
    return ChatPromptTemplate.from_messages(
        [
            ("system", _SYSTEM),
            ("human", _HUMAN),
        ]
    )
