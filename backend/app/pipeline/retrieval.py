"""
Retrieval Module.

Wraps a :class:`VectorStore` and exposes higher-level retrieval methods.
The Retriever is intentionally thin — it delegates to the store — so that
it can later be extended with hybrid search, re-ranking, multi-hop
retrieval, etc.

Usage::

    retriever = Retriever(vector_store)
    results = retriever.retrieve("What is RAG?", top_k=5)
    context = retriever.format_context(results)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .storage import VectorStore

logger = logging.getLogger(__name__)


class Retriever:
    """Retrieval wrapper around a :class:`VectorStore`.

    Parameters
    ----------
    vector_store : VectorStore
        The backend store used for semantic search.
    default_top_k : int
        Default number of results to retrieve (overrideable per call).
    """

    def __init__(
        self,
        vector_store: VectorStore,
        default_top_k: int = 5,
    ) -> None:
        self._store = vector_store
        self.default_top_k = default_top_k

    # -- retrieval ----------------------------------------------------------

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve the most relevant documents for *query*.

        Parameters
        ----------
        query : str
            Natural-language query.
        top_k : int or None
            Maximum number of results (falls back to *default_top_k*).
        where : dict or None
            ChromaDB-compatible metadata filter.

        Returns
        -------
        list[dict]
            Each dict contains ``id``, ``text``, ``metadata``, ``distance``.
        """
        k = top_k if top_k is not None else self.default_top_k
        logger.debug("Retrieving top_k=%d for query: %s", k, query[:120])
        return self._store.search(query, top_k=k, where=where)

    # -- formatting ---------------------------------------------------------

    @staticmethod
    def format_context(results: list[dict[str, Any]]) -> str:
        """Format retrieved documents into a string suitable for an LLM prompt.

        Each document is labelled as ``[Document N]`` with its text content
        separated by a horizontal rule.

        Parameters
        ----------
        results : list[dict]
            The output of :meth:`retrieve`.

        Returns
        -------
        str
            Formatted context block.
        """
        if not results:
            return "（未找到相关文档）"

        blocks: list[str] = []
        for i, doc in enumerate(results, start=1):
            text = doc.get("text", "").strip()
            source = doc.get("metadata", {}).get("source", "")
            header = f"[Document {i}]"
            if source:
                header += f" (source: {source})"
            blocks.append(f"{header}\n{text}")

        return "\n\n---\n\n".join(blocks)

    # -- convenience --------------------------------------------------------

    @property
    def store(self) -> VectorStore:
        """Expose the underlying store for direct operations."""
        return self._store

    def __repr__(self) -> str:
        return f"Retriever(store={self._store!r})"
