"""
FastAPI dependency injection — lazy-singleton providers.

Each `get_*` function creates its provider on the first call and caches it,
so downstream routes share the same instance.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cached provider factories
# ---------------------------------------------------------------------------

@lru_cache()
def get_cleaning_pipeline():
    """Return a singleton CleaningPipeline instance."""
    from app.pipeline.cleaning import CleaningPipeline

    logger.info("Initialising CleaningPipeline")
    return CleaningPipeline()


@lru_cache()
def get_embedding_provider():
    """Return a singleton OllamaEmbeddingProvider instance."""
    from app.pipeline.embedding import OllamaEmbeddingProvider

    settings = get_settings()
    logger.info("Initialising OllamaEmbeddingProvider model=%s", settings.embedding_model)
    return OllamaEmbeddingProvider(
        base_url=settings.ollama_base_url,
        model=settings.embedding_model,
    )


@lru_cache()
def get_vector_store():
    """Return a singleton ChromaVectorStore instance."""
    from app.pipeline.storage import ChromaVectorStore

    settings = get_settings()
    logger.info("Initialising ChromaVectorStore dir=%s", settings.chroma_data_dir)
    return ChromaVectorStore(
        collection_name="rag_documents",
        persist_directory=settings.chroma_data_dir,
        embedding_provider=get_embedding_provider(),
    )


@lru_cache()
def get_retriever():
    """Return a singleton Retriever instance."""
    from app.pipeline.retrieval import Retriever

    logger.info("Initialising Retriever")
    return Retriever(vector_store=get_vector_store())


@lru_cache()
def get_llm_provider():
    """Return a singleton OllamaProvider instance."""
    from app.pipeline.generation import OllamaProvider

    settings = get_settings()
    logger.info("Initialising OllamaProvider model=%s", settings.llm_model)
    return OllamaProvider(
        base_url=settings.ollama_base_url,
        model=settings.llm_model,
    )
