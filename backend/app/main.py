"""
FastAPI application entry point.

CORS is configured for the Vite dev server (localhost:5173).  All API
routes are registered here, and a global exception handler ensures
consistent error responses.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.chat import router as chat_router
from app.api.upload import router as upload_router
from app.config import get_settings

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Warm up providers on startup, clean up on shutdown."""
    logger.info("Application starting up...")
    settings = get_settings()
    logger.info("Ollama base URL: %s", settings.ollama_base_url)
    logger.info("Embedding model:  %s", settings.embedding_model)
    logger.info("LLM model:        %s", settings.llm_model)

    # Optional warm-up: try to initialise providers eagerly.
    try:
        from app.api.dependencies import (
            get_cleaning_pipeline,
            get_embedding_provider,
            get_llm_provider,
            get_retriever,
            get_vector_store,
        )
        get_cleaning_pipeline()
        get_embedding_provider()
        get_vector_store()
        get_retriever()
        get_llm_provider()
        logger.info("All providers initialised successfully.")
    except ImportError:
        logger.warning("Pipeline modules not found — providers will be lazy-initialised on first request.")
    except Exception:
        logger.exception("Provider warm-up failed — continuing anyway.")

    yield  # Application runs here

    logger.info("Application shutting down.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
app = FastAPI(
    title="RAG Chatbot API",
    description="Backend API for the RAG-based knowledge-base chatbot.",
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — allow frontend dev server
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(chat_router)
app.include_router(upload_router)

# ---------------------------------------------------------------------------
# Static files (production — serve built frontend assets)
# ---------------------------------------------------------------------------
# Only enable in production: set ENABLE_STATIC=true
# In dev, the Vite dev server on :5173 handles the frontend.
if os.environ.get("ENABLE_STATIC", "").lower() == "true":
    frontend_dist = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
    if os.path.isdir(frontend_dist):
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")
        logger.info("Mounted frontend static files from %s", frontend_dist)


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler that returns a friendly JSON error body."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error. Please try again later.",
            "error_type": type(exc).__name__,
        },
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health() -> dict:
    """Simple health-check endpoint."""
    return {"status": "ok", "timestamp": time.time()}
