# CLAUDE.md — RAG Chatbot Backend

## Project Purpose

A local-first RAG (Retrieval-Augmented Generation) chatbot backend. Users upload documents (txt, md, pdf, docx), the system cleans, chunks, embeds, and stores them in ChromaDB, then answers natural-language questions by retrieving relevant chunks and passing them as context to an Ollama-hosted LLM.

**Tech stack**: FastAPI + ChromaDB + Ollama, all running locally.

## Architecture

### Pipeline Pattern

The RAG pipeline follows five stages, each in its own module under `app/pipeline/`:

```
Document Upload
  --> cleaning (CleaningPipeline: chain of CleaningStep ABCs)
    --> embedding (EmbeddingProvider ABC -> OllamaEmbeddingProvider)
      --> storage (VectorStore ABC -> ChromaVectorStore)
        --> retrieval (Retriever wrapping VectorStore)
          --> generation (LLMProvider ABC -> OllamaProvider + build_rag_prompt)
```

The upload endpoint (`POST /api/upload`) runs stages 1-4. The chat endpoint (`POST /api/chat`) runs stages 4-5.

### Strategy Pattern

Every swappable component is behind an abstract base class (ABC):

| ABC | Concrete | Module |
|-----|----------|--------|
| `CleaningStep` | `BasicCleaningStep`, `StructureCleaningStep`, `QualityFilterStep`, `RAGChunkingStep` | `pipeline/cleaning.py` |
| `EmbeddingProvider` | `OllamaEmbeddingProvider` | `pipeline/embedding.py` |
| `VectorStore` | `ChromaVectorStore` | `pipeline/storage.py` |
| `LLMProvider` | `OllamaProvider` | `pipeline/generation.py` |

`Retriever` is a concrete wrapper (not an ABC) — it composes a `VectorStore` and adds formatting/convenience methods.

### FastAPI Dependency Injection

All providers are created via `lru_cache`-decorated factory functions in `app/api/dependencies.py`. This ensures:

- **Lazy initialization**: first call creates the instance, subsequent calls return the cached singleton.
- **Shared state**: all routes use the same ChromaDB client, embedding provider, etc.
- **Testability**: routes use `Depends(get_*)` so mocks can be injected.

```python
# Example from dependencies.py
@lru_cache()
def get_llm_provider():
    settings = get_settings()
    return OllamaProvider(base_url=settings.ollama_base_url, model=settings.llm_model)

# In a route
@router.post("/chat")
async def chat(request: ChatRequest, llm=Depends(get_llm_provider)):
    ...
```

### Lifespan

`app/main.py` defines an `@asynccontextmanager` lifespan that eagerly warms up all providers on startup (calls each `get_*` factory) and logs their configuration. Failures during warm-up are caught and logged; the app still starts.

## Code Style

### Imports and Language

- **Python 3.13** target. Every `.py` file starts with `from __future__ import annotations` to enable PEP 604 `|` union syntax and deferred annotation evaluation.
- Imports are grouped: stdlib, third-party, local (`from app...`). The `TYPE_CHECKING` guard is used for circular-import-sensitive type-only imports (see `pipeline/storage.py` and `pipeline/retrieval.py`).

### Type Hints

All function signatures, method signatures, and class attributes have type hints. Examples:

- `list[dict[str, Any]]` for ChromaDB results
- `dict[str, Any]` for loosely-typed metadata
- `Iterator[str]` for streaming token generators
- `AsyncGenerator[str, None]` for SSE event generators

### Docstrings

Google-style docstrings throughout:

```python
def clean(self, text: str) -> str:
    """Apply this cleaning step and return the transformed text.

    Parameters
    ----------
    text : str
        The raw or partially-cleaned input text.

    Returns
    -------
    str
        The cleaned text.
    """
```

- Every public class, method, and function has a docstring.
- Module-level docstrings describe the module's purpose and provide a usage example in a `.. code-block::` or `Usage::` block.

### Logging

Every module gets its own logger:

```python
import logging
logger = logging.getLogger(__name__)
```

Log levels used: `INFO` for lifecycle events (init, ingestion counts), `DEBUG` for detailed filtering decisions, `WARNING` for retries and recoverable failures, `EXCEPTION` in try/except blocks via `logger.exception()`.

Format is set in `main.py`: `"%(asctime)s [%(levelname)s] %(name)s: %(message)s"`.

### ABCs and Abstract Methods

All provider interfaces use `ABC` and `@abstractmethod`. Abstract properties use the stacked decorator pattern:

```python
@property
@abstractmethod
def name(self) -> str: ...
```

Concrete implementations always have `@property` alone (not stacked with `@abstractmethod`).

### Singletons via lru_cache

Two patterns:

1. **Settings**: `config.py` — `@lru_cache()` on `get_settings()` returns a single `Settings` instance.
2. **Providers**: `dependencies.py` — `@lru_cache()` on each `get_*` factory returns a single provider instance.

Both use `lru_cache()` with no arguments (unbounded cache size, which is correct for exactly-one semantics).

### Pydantic Models

Request/response schemas live in `app/models/schemas.py`. Models use `Field(...)` with `description` for every field. Optional fields use `| None` with a default:

```python
class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User question")
    history: list[dict[str, str]] | None = Field(default=None, description="...")
```

### Error Handling

- **API routes**: try/except with `HTTPException` for known failure modes (unsupported file type, file too large, PDF not implemented). `ImportError` is caught separately to return 501 when pipeline modules are missing.
- **Global handler**: `main.py` registers a catch-all `@app.exception_handler(Exception)` that logs the full traceback and returns a 500 JSON response with `error_type`.
- **Pipeline steps**: `CleaningPipeline.clean()` wraps each step in try/except, logs the error, and continues with the pre-step text — individual step failure does not abort the entire pipeline.
- **Provider retries**: Both `OllamaEmbeddingProvider` and `OllamaProvider` have built-in retry with exponential backoff (`max_retries=3`, base delay 1s, doubling each attempt).

### Config Management

`app/config.py` loads `.env` from the backend root via `python-dotenv`. All settings are plain attributes on a `Settings` class (not Pydantic `BaseSettings`). Relative paths (`CHROMA_DATA_DIR`, `UPLOAD_DIR`) are resolved against the backend root directory. Every setting has a sensible default.

## Project Structure

```
backend/
├── .env                          # Actual env vars (gitignored)
├── .env.example                  # Documented template
├── requirements.txt              # Pinned dependencies
├── data/
│   ├── chroma/                   # ChromaDB persistent storage
│   └── uploads/                  # Saved original uploaded files
└── app/
    ├── __init__.py               # Empty
    ├── main.py                   # FastAPI app, CORS, lifespan, health check
    ├── config.py                 # Settings from env vars
    ├── api/
    │   ├── __init__.py           # Empty
    │   ├── dependencies.py       # lru_cache provider factories
    │   ├── chat.py               # POST /api/chat, POST /api/chat/stream
    │   └── upload.py             # POST /api/upload (ingest pipeline)
    ├── models/
    │   ├── __init__.py           # Empty
    │   └── schemas.py            # Pydantic: ChatRequest, ChatResponse, SourceDoc, UploadResponse
    └── pipeline/
        ├── __init__.py           # Re-exports all public symbols
        ├── cleaning.py           # CleaningStep ABC + 4 levels + CleaningPipeline
        ├── embedding.py          # EmbeddingProvider ABC + OllamaEmbeddingProvider
        ├── storage.py            # VectorStore ABC + ChromaVectorStore
        ├── retrieval.py          # Retriever (concrete wrapper)
        └── generation.py         # LLMProvider ABC + OllamaProvider + build_rag_prompt()
```

## Key Files and Their Roles

### `app/main.py` — Application Entry Point
- Creates the `FastAPI` instance with title/description/version.
- Configures CORS for `localhost:5173` (Vite dev server).
- Registers `chat_router` and `upload_router`.
- Defines the `lifespan` that warms up all providers on startup.
- Optionally mounts `frontend/dist` as static files when `ENABLE_STATIC=true`.
- Registers a global `Exception -> JSONResponse` handler.
- Exposes `GET /api/health`.

### `app/config.py` — Settings
- `Settings` class reads from environment variables (loaded from `../.env` via `python-dotenv`).
- `get_settings()` is `@lru_cache`-decorated for singleton access.
- Resolves relative `CHROMA_DATA_DIR` and `UPLOAD_DIR` paths against the backend root.
- Defaults: `OLLAMA_BASE_URL=http://localhost:11434`, `EMBEDDING_MODEL=bge-m3`, `LLM_MODEL=qwen2.5:7b`.

### `app/api/dependencies.py` — Provider Wiring
- Five `@lru_cache()` factories that lazy-init and cache singletons:
  - `get_cleaning_pipeline()` — assembles a `CleaningPipeline` with 4 default steps.
  - `get_embedding_provider()` — returns `OllamaEmbeddingProvider`.
  - `get_vector_store()` — returns `ChromaVectorStore` (collection `"rag_documents"`).
  - `get_retriever()` — returns `Retriever` wrapping the vector store.
  - `get_llm_provider()` — returns `OllamaProvider`.
- Each factory logs its initialization at INFO level.

### `app/api/upload.py` — Document Ingestion
- `POST /api/upload` accepts a file upload (multipart).
- Validates extension (`.txt`, `.md`, `.pdf`, `.docx`) and size (max 10 MB).
- Saves the original file to `UPLOAD_DIR` with a UUID-based name.
- Decodes text: direct for `.txt`/`.md`, stubs for `.pdf`/`.docx`.
- Runs the cleaning pipeline, then chunks via local `_chunk_text()` (paragraph-based with overlap).
- Embeds via `embedding_provider` and stores in `vector_store`.
- Returns `UploadResponse` with `file_id`, `filename`, `chunks_count`.
- `_chunk_text()` splits on double-newlines, merges short paragraphs until `chunk_size` (500 chars), adds `overlap` (50 chars) between chunks.

### `app/api/chat.py` — RAG Chat
- `POST /api/chat` — non-streaming: retrieves docs, builds context, calls `llm.generate()`, returns `ChatResponse`.
- `POST /api/chat/stream` — SSE streaming: same flow but yields `data: {"token": "..."}` events, then a sources array, then `[DONE]`.
- Both convert ChromaDB distances to scores (`1.0 - distance`).
- Error events in the stream are sent as `{"error": "..."}` then `[DONE]`.

### `app/models/schemas.py` — Data Models
- `SourceDoc` — `content`, `metadata`, `score`.
- `ChatRequest` — `query` (min_length=1), `history` (optional).
- `ChatResponse` — `answer`, `sources`.
- `UploadResponse` — `file_id`, `filename`, `chunks_count`, `status`.

### `app/pipeline/cleaning.py` — Text Cleaning Pipeline
- `CleaningStep` ABC with `name` property and `clean(text) -> str`.
- Four levels implemented:
  1. **BasicCleaningStep** — Unicode NFKC, line ending normalization, whitespace collapse, blank line dedup.
  2. **StructureCleaningStep** — Strip HTML tags, convert Markdown links/images to plain text.
  3. **QualityFilterStep** — Drop text below `min_length` (5) or above `max_whitespace_ratio` (0.95).
  4. **RAGChunkingStep** — Split into paragraphs, merge short ones (`< min_chunk_length` = 80).
- `CleaningPipeline` orchestrates steps sequentially, returns `{"text", "stats", "errors"}`.
- Steps are stateless; the same instance is safe to reuse.

### `app/pipeline/embedding.py` — Embedding Provider
- `EmbeddingProvider` ABC with `embed(texts)`, `embed_query(query)`, `dimension`.
- `OllamaEmbeddingProvider` calls Ollama's `/api/embeddings` endpoint.
- Embedding is done text-by-text (no batching in the Ollama API).
- Retry with exponential backoff (3 attempts, 1s base delay).
- Validates returned dimension against expected `_dimension` (1024 for bge-m3).
- Uses `requests.Session` for connection reuse.

### `app/pipeline/storage.py` — Vector Store
- `VectorStore` ABC with `add()`, `search()`, `delete()`, `count()`.
- `ChromaVectorStore` wraps `chromadb.PersistentClient`.
- Adapter pattern: `_ChromaEmbeddingAdapter` bridges `EmbeddingProvider` to ChromaDB's `EmbeddingFunction` protocol.
- `add()` auto-generates UUIDs if `ids` not provided, validates length consistency.
- `search()` returns `[{"id", "text", "metadata", "distance"}, ...]`.
- `reset()` drops and recreates the collection.
- Supports metadata filtering via `where` dict.

### `app/pipeline/retrieval.py` — Retriever
- Thin wrapper around `VectorStore.search()`.
- `default_top_k=5`, overridable per call.
- `format_context()` static method: formats results as `[Document N] (source: ...)\n{text}` blocks separated by `---`.

### `app/pipeline/generation.py` — LLM Generation
- `LLMProvider` ABC with `generate(messages)` and `generate_stream(messages)`.
- `OllamaProvider` calls Ollama's `/api/chat` endpoint.
- Non-streaming: returns `data["message"]["content"]`.
- Streaming: iterates NDJSON lines, yields `chunk["message"]["content"]` tokens, stops on `done: true`.
- Both have retry with exponential backoff (3 attempts, base 1s, timeout 120s for streaming).
- `build_rag_prompt()` assembles `[system, ...history, user_with_context]` messages list.
- Default system prompt instructs the model to answer only from context, cite document numbers, reply in the user's language, and be concise.

## How to Run

### Prerequisites

1. **Ollama** installed and running (default: `http://localhost:11434`).
2. Pull the required models:
   ```bash
   ollama pull bge-m3         # embedding model
   ollama pull qwen2.5:7b     # LLM (or deepseek-r1:7b, etc.)
   ```
3. Python 3.13 with dependencies:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

### Environment Variables

Copy `.env.example` to `.env` and customize if needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server address |
| `EMBEDDING_MODEL` | `bge-m3` | Embedding model name in Ollama |
| `LLM_MODEL` | `qwen2.5:7b` | Chat model name in Ollama |
| `CHROMA_DATA_DIR` | `./data/chroma` | ChromaDB persistence directory |
| `UPLOAD_DIR` | `./data/uploads` | Uploaded file storage |

### Start the Server

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

The API is available at `http://localhost:8000`. Health check: `GET /api/health`.

### Serve Frontend (Production)

Set `ENABLE_STATIC=true` to serve the built frontend from `frontend/dist/`:
```bash
ENABLE_STATIC=true uvicorn app.main:app --port 8000
```

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/upload` | Upload a document (multipart form) |
| `POST` | `/api/chat` | Non-streaming RAG chat |
| `POST` | `/api/chat/stream` | Streaming RAG chat (SSE) |

## Testing Approach

The project currently has **no test suite**. There are no test files, no pytest configuration, and no `conftest.py`.

When tests are added, the recommended approach based on the architecture:

- **Unit tests**: Each pipeline module's ABCs and concrete implementations can be tested in isolation. Mock `requests.Session` for providers, mock `chromadb.PersistentClient` for the vector store.
- **Integration tests**: Use `FastAPI`'s `TestClient` with dependency overrides (`app.dependency_overrides`) to inject mock providers.
- **Test organization**: Follow the same package structure — `tests/pipeline/test_cleaning.py`, `tests/api/test_chat.py`, etc.
- Use `pytest` with `pytest-asyncio` for async route tests.
- A `conftest.py` at `backend/tests/conftest.py` should provide fixtures for mock settings, mock providers, and a configured `TestClient`.

## Conventions

### Naming
- **Modules**: lowercase, descriptive (`cleaning.py`, `embedding.py`). One module = one pipeline stage.
- **Classes**: PascalCase. ABCs get plain names (`CleaningStep`), concrete implementations prefix with the technology/provider (`OllamaEmbeddingProvider`, `ChromaVectorStore`).
- **Functions/methods**: snake_case. Factory functions use `get_` prefix (`get_settings`, `get_llm_provider`).
- **Private helpers**: `_` prefix for module-internal functions (`_chunk_text`, `_read_text`, `_ChromaEmbeddingAdapter`). Stub extraction functions also get `_` prefix (`_extract_pdf_text`).

### Module Organization
Each pipeline module follows this structure:
1. Module docstring with `Usage::` example
2. Imports
3. `logger = logging.getLogger(__name__)`
4. ABC definition (if any)
5. Concrete implementation(s)
6. (Optional) convenience functions/constants

### Error Handling Pattern
- **API layer**: Catch specific exceptions, convert to `HTTPException` with appropriate status codes (400 for validation, 413 for size, 501 for not implemented). `ImportError` is caught separately for missing pipeline modules.
- **Pipeline layer**: Individual step failures are logged and skipped; the step's input text is preserved. Provider-level failures use retry logic; after exhausting retries, raise `RuntimeError`.
- **Global**: The catch-all handler in `main.py` ensures no unhandled exception leaks a traceback to the client.

### Dependency Injection Pattern
- Routes never instantiate providers directly.
- Provider selection is centralized in `app/api/dependencies.py`.
- To swap a provider (e.g., replace Ollama with OpenAI), change only the `get_*` factory — routes remain untouched.
- In tests, use `app.dependency_overrides`:
  ```python
  app.dependency_overrides[get_llm_provider] = lambda: mock_llm
  ```

### Config Management Pattern
- All config lives in `Settings`, populated from env vars with defaults.
- Only `get_settings()` (not `Settings()`) should be called throughout the codebase — this ensures the `.env` file is loaded exactly once.
- Relative paths are resolved against `backend/` at init time, so callers always get absolute paths.
