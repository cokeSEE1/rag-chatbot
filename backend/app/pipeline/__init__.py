"""
RAG Pipeline Modules.

Provides the full ingestion and query pipeline:
    cleaning -> embedding -> storage -> retrieval -> generation
"""

from .cleaning import (
    CleaningStep,
    CleaningPipeline,
    BasicCleaningStep,
    StructureCleaningStep,
    QualityFilterStep,
    RAGChunkingStep,
)

from .embedding import (
    EmbeddingProvider,
    OllamaEmbeddingProvider,
)

from .storage import (
    VectorStore,
    ChromaVectorStore,
)

from .retrieval import (
    Retriever,
)

from .generation import (
    LLMProvider,
    OllamaProvider,
    build_rag_prompt,
)

__all__ = [
    # cleaning
    "CleaningStep",
    "CleaningPipeline",
    "BasicCleaningStep",
    "StructureCleaningStep",
    "QualityFilterStep",
    "RAGChunkingStep",
    # embedding
    "EmbeddingProvider",
    "OllamaEmbeddingProvider",
    # storage
    "VectorStore",
    "ChromaVectorStore",
    # retrieval
    "Retriever",
    # generation
    "LLMProvider",
    "OllamaProvider",
    "build_rag_prompt",
]
