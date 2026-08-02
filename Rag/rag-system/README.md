# Modular RAG System

A production-ready **Retrieval-Augmented Generation** pipeline built with **Python**, **LangChain**, and **Ollama**.

```
query → embed → retrieve → build context → LLM → answer
```

The vector retrieval layer is **fully swappable** — switch from the in-memory mock to Qdrant by changing a single environment variable. No code changes needed.

---

## Architecture

```
src/
├── api/                       FastAPI routes + controllers
│   ├── controller/query_controller.py
│   └── routes/query_routes.py
├── core/
│   ├── embeddings/            OllamaEmbeddings wrapper
│   ├── retriever/             IRetriever interface + MockRetriever + QdrantRetriever
│   │   └── retriever_factory.py   ← THE swap point
│   ├── llm/                   ChatOllama wrapper
│   ├── prompt/                RAG ChatPromptTemplate
│   └── rag/                   LCEL chain orchestrator
├── data/
│   ├── documents/sample_docs.txt   auto-seeded on startup
│   └── ingestion/ingest_service.py
├── config/                    Settings (pydantic-settings) + Qdrant client
├── types/                     Pydantic v2 request/response models
└── app.py                     FastAPI entry point
```

---

## Quick Start

### 1. Prerequisites

| Tool | Purpose |
|------|---------|
| Python 3.11+ | Runtime |
| [Ollama](https://ollama.com) | Local LLM + embeddings |

```bash
# Pull required Ollama models
ollama pull llama3
ollama pull nomic-embed-text
```

### 2. Install

```bash
cd rag-system
pip install -r requirements.txt
```

### 3. Configure

Edit `.env` — defaults are already set for Ollama:

```env
RETRIEVER=mock          # in-memory, works out of the box
LLM_MODEL=llama3
EMBED_MODEL=nomic-embed-text
```

### 4. Run

```bash
uvicorn src.app:app --reload --port 8000
```

The server starts, seeds `sample_docs.txt` automatically, and is ready to answer questions.

- **Interactive docs**: http://localhost:8000/docs
- **Health check**: http://localhost:8000/health

---

## API Reference

### `GET /health`

```json
{
  "status": "ok",
  "retriever": "mock",
  "llm_model": "llama3",
  "embed_model": "nomic-embed-text",
  "docs_in_store": 24
}
```

### `POST /api/ingest`

Add your own documents:

```bash
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"text": "Your document content here.", "source": "my-doc.txt"}'
```

```json
{ "ingested": 3, "message": "Successfully ingested 3 chunk(s) from 'my-doc.txt'." }
```

### `POST /api/query`

Ask a question:

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is RAG?", "top_k": 4}'
```

```json
{
  "question": "What is RAG?",
  "answer": "RAG (Retrieval-Augmented Generation) is a technique that ...",
  "sources": [
    { "content": "...", "metadata": { "source": "sample_docs.txt" } }
  ]
}
```

---

## Switching to Qdrant

When the Qdrant instance is ready:

1. **Start Qdrant** (optional — local instance via Docker):
   ```bash
   docker compose -f docker/docker-compose.yml up -d
   ```

2. **Update `.env`**:
   ```env
   RETRIEVER=qdrant
   QDRANT_URL=http://<qdrant-host>:6333
   QDRANT_COLLECTION=rag_docs
   EMBED_DIMENSION=768
   ```

3. **Restart the server** — that's it. The Qdrant collection is auto-created.

> **No code changes required.** The `IRetriever` interface ensures both backends are interchangeable.

---

## Tuning

| Variable | Default | Effect |
|----------|---------|--------|
| `CHUNK_SIZE` | 500 | Characters per chunk |
| `CHUNK_OVERLAP` | 50 | Overlap between adjacent chunks |
| `TOP_K` | 4 | Chunks retrieved per query |
| `EMBED_DIMENSION` | 768 | Must match embedding model output |

---

## Project Structure Decisions

- **`IRetriever` ABC** — the single abstraction that decouples all other code from the vector store.
- **`retriever_factory.py`** — reads `RETRIEVER` env-var and returns the correct implementation.
- **LCEL chain** — `retriever | format_docs | prompt | llm | parser` — composable, async, streamable.
- **`pydantic-settings`** — all config in one place, validated on startup, no scattered `os.getenv` calls.
