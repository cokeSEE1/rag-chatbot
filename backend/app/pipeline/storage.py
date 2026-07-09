"""
Vector Store Module.

Strategy-pattern abstraction over vector databases.  The default
implementation wraps ChromaDB (PersistentClient).

Usage::

    from pipeline.embedding import OllamaEmbeddingProvider
    from pipeline.storage import ChromaVectorStore

    embed_provider = OllamaEmbeddingProvider()
    store = ChromaVectorStore(
        collection_name="my_docs",
        persist_directory="./chroma_data",
        embedding_provider=embed_provider,
    )
    store.add(["doc text 1", "doc text 2"], metadatas=[{"src": "a"}, {"src": "b"}])
    results = store.search("query", top_k=3)
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import chromadb
from chromadb.api.types import EmbeddingFunction, Documents

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .embedding import EmbeddingProvider


# ---------------------------------------------------------------------------
# ChromaDB EmbeddingFunction adapter
# ---------------------------------------------------------------------------

class _ChromaEmbeddingAdapter(EmbeddingFunction):
    """Bridge between our :class:`EmbeddingProvider` and ChromaDB's API."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        self._provider = provider

    def __call__(self, input: Documents) -> list[list[float]]:  # type: ignore[override]
        return self._provider.embed(input)

    @staticmethod
    def name() -> str:  # type: ignore[override]
        return "pipeline_embedding_adapter"


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class VectorStore(ABC):
    """Abstract base for vector-store backends."""

    @abstractmethod
    def add(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ) -> list[str]:
        """Embed and store a batch of documents.

        Parameters
        ----------
        texts : list[str]
            Document texts to store.
        metadatas : list[dict] or None
            Metadata dicts, one per document (optional).
        ids : list[str] or None
            Unique IDs, auto-generated if omitted.

        Returns
        -------
        list[str]
            The IDs of the stored documents.
        """
        ...

    @abstractmethod
    def search(
        self,
        query: str,
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search for the most relevant documents.

        Returns
        -------
        list[dict]
            Each result dict includes keys: ``id``, ``text``, ``metadata``,
            ``distance`` (or ``score``).
        """
        ...

    @abstractmethod
    def delete(self, ids: list[str]) -> None:
        """Remove documents by ID."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Return the number of documents in the store."""
        ...

    @abstractmethod
    def list_documents(self) -> list[dict[str, Any]]:
        """Return unique uploaded documents (grouped by file_id).

        Returns
        -------
        list[dict]
            Each dict has ``file_id``, ``filename``, ``chunks_count``.
        """
        ...


# ---------------------------------------------------------------------------
# ChromaDB implementation
# ---------------------------------------------------------------------------

class ChromaVectorStore(VectorStore):
    """ChromaDB-backed vector store.

    Parameters
    ----------
    collection_name : str
        Name of the ChromaDB collection.
    persist_directory : str
        Directory where ChromaDB persists its data.
    embedding_provider : EmbeddingProvider
        Provider used to embed documents and queries.
    distance_metric : str
        ChromaDB distance metric: ``"cosine"``, ``"l2"``, or ``"ip"``.
        Default ``"cosine"``.
    """

    def __init__(
        self,
        collection_name: str,
        persist_directory: str,
        embedding_provider: EmbeddingProvider,
        distance_metric: str = "cosine",
    ) -> None:
        self.collection_name = collection_name
        self.embedding_provider = embedding_provider

        self._client = chromadb.PersistentClient(path=persist_directory)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=_ChromaEmbeddingAdapter(embedding_provider),
            metadata={"hnsw:space": distance_metric},
        )

    # -- VectorStore interface ----------------------------------------------

    def add(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ) -> list[str]:
        if not texts:
            return []

        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts]

        if metadatas is None:
            metadatas = [{}] * len(texts)

        if len(texts) != len(metadatas) or len(texts) != len(ids):
            raise ValueError(
                f"Length mismatch: texts={len(texts)}, "
                f"metadatas={len(metadatas)}, ids={len(ids)}"
            )

        logger.info("Adding %d documents to collection '%s'", len(texts), self.collection_name)
        self._collection.add(
            documents=texts,
            metadatas=metadatas,  # type: ignore[arg-type]  # chromadb Metadata type too strict
            ids=ids,
        )
        return ids

    def search(
        self,
        query: str,
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not query.strip():
            return []

        kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": top_k,
        }
        if where is not None:
            kwargs["where"] = where

        raw = self._collection.query(**kwargs)

        # Chroma returns nested lists (one per query); we have exactly one query.
        ids_list = raw.get("ids") or [[]]  # type: ignore[assignment]
        documents_list = raw.get("documents") or [[]]  # type: ignore[assignment]
        metadatas_list = raw.get("metadatas") or [[]]  # type: ignore[assignment]
        distances_list = raw.get("distances") or [[]]  # type: ignore[assignment]

        ids = ids_list[0] if ids_list else []
        documents = documents_list[0] if documents_list else []
        metadatas = metadatas_list[0] if metadatas_list else []
        distances = distances_list[0] if distances_list else []

        results: list[dict[str, Any]] = []
        for i in range(len(ids)):
            results.append({
                "id": ids[i],
                "text": documents[i] if i < len(documents) else "",
                "metadata": metadatas[i] if i < len(metadatas) else {},
                "distance": distances[i] if i < len(distances) else None,
            })
        return results

    def delete(self, ids: list[str]) -> None:
        if not ids:
            return
        logger.info("Deleting %d documents from collection '%s'", len(ids), self.collection_name)
        self._collection.delete(ids=ids)

    def count(self) -> int:
        return self._collection.count()

    # -- convenience --------------------------------------------------------

    def get(self, ids: list[str]) -> dict[str, Any]:
        """Retrieve documents by ID (raw Chroma response)."""
        return self._collection.get(ids=ids)  # type: ignore[return-value,no-any-return]

    def list_documents(self) -> list[dict[str, Any]]:
        """Return unique uploaded documents grouped by file_id.

        Queries all chunks in the collection and groups them by ``file_id``
        to produce one entry per uploaded document.
        """
        try:
            all_data = self._collection.get()
        except Exception:
            logger.exception("Failed to list documents from ChromaDB")
            return []

        metadatas = all_data.get("metadatas") or []
        if not metadatas:
            return []

        # Group chunks by file_id, counting chunks per document
        doc_map: dict[str, dict[str, Any]] = {}
        for meta in metadatas:
            file_id = meta.get("file_id")
            filename = meta.get("filename", "unknown")
            if not file_id:
                continue
            if file_id not in doc_map:
                doc_map[file_id] = {
                    "file_id": file_id,
                    "filename": filename,
                    "chunks_count": 0,
                }
            doc_map[file_id]["chunks_count"] += 1

        return sorted(doc_map.values(), key=lambda d: d["filename"])

    def reset(self) -> None:
        """Delete the collection entirely and recreate it."""
        logger.info("Resetting collection '%s'", self.collection_name)
        self._client.delete_collection(self.collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=_ChromaEmbeddingAdapter(self.embedding_provider),
        )

    def __repr__(self) -> str:
        return (
            f"ChromaVectorStore(collection={self.collection_name!r}, "
            f"count={self.count()})"
        )
