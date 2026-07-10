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
    """Return a singleton CleaningPipeline with default steps."""
    from app.pipeline.cleaning import (
        BasicCleaningStep,
        CleaningPipeline,
        DocxMetadataCleaningStep,
        QualityFilterStep,
        RAGChunkingStep,
        StructureCleaningStep,
    )

    logger.info("Initialising CleaningPipeline with default steps")
    pipeline = CleaningPipeline()
    pipeline.add_step(BasicCleaningStep())
    pipeline.add_step(StructureCleaningStep())
    pipeline.add_step(DocxMetadataCleaningStep())
    pipeline.add_step(QualityFilterStep())
    pipeline.add_step(RAGChunkingStep())
    return pipeline


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
    """Return a singleton Ollama LLM provider."""
    from app.pipeline.generation import OllamaProvider

    settings = get_settings()
    logger.info("Initialising OllamaProvider model=%s", settings.llm_model)
    return OllamaProvider(
        base_url=settings.ollama_base_url,
        model=settings.llm_model,
    )


@lru_cache()
def get_anthropic_provider():
    """Return a singleton Anthropic-compatible LLM provider."""
    from app.pipeline.generation import AnthropicProvider

    settings = get_settings()
    logger.info(
        "Initialising AnthropicProvider base_url=%s model=%s",
        settings.anthropic_base_url,
        settings.anthropic_model,
    )
    return AnthropicProvider(
        base_url=settings.anthropic_base_url,
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
    )
