"""
Embedding Provider Module.

Strategy-pattern abstraction over embedding models so the rest of the
pipeline never needs to know which service is generating vectors.

Default provider: Ollama + BGE-M3 (1024-dimensional).

Usage::

    provider = OllamaEmbeddingProvider(base_url="http://localhost:11434", model="bge-m3")
    vectors = provider.embed(["hello world", "another text"])
    query_vec = provider.embed_query("search query")
    print(provider.dimension)  # 1024
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any

import requests

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class EmbeddingProvider(ABC):
    """Abstract base for embedding providers."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of documents.

        Parameters
        ----------
        texts : list[str]
            One or more text strings to embed.

        Returns
        -------
        list[list[float]]
            A list of embedding vectors, one per input text.
        """
        ...

    @abstractmethod
    def embed_query(self, query: str) -> list[float]:
        """Embed a single query string.

        Some providers use different prompts / prefixes for queries vs
        documents; this method encapsulates that difference.
        """
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the dimensionality of the embedding vectors."""
        ...


# ---------------------------------------------------------------------------
# Ollama implementation
# ---------------------------------------------------------------------------

class OllamaEmbeddingProvider(EmbeddingProvider):
    """Ollama embedding provider using the ``/api/embeddings`` endpoint.

    Parameters
    ----------
    base_url : str
        Ollama server base URL, e.g. ``"http://localhost:11434"``.
    model : str
        Model name known to Ollama, e.g. ``"bge-m3"``.
    dimension : int
        Expected embedding dimensionality (used for validation).
    max_retries : int
        Number of retries on transient failures.
    retry_delay : float
        Base delay in seconds between retries (exponential backoff).
    timeout : float
        Request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "bge-m3",
        dimension: int = 1024,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._dimension = dimension
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self._session = requests.Session()

    # -- properties ---------------------------------------------------------

    @property
    def dimension(self) -> int:
        return self._dimension

    # -- public API ---------------------------------------------------------

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._embed_batch(texts)

    def embed_query(self, query: str) -> list[float]:
        results = self._embed_batch([query])
        return results[0]

    # -- internal -----------------------------------------------------------

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for idx, text in enumerate(texts):
            vector = self._embed_one(text, attempt=0)
            # Validate dimension
            if len(vector) != self._dimension:
                logger.warning(
                    "Embedding dimension mismatch for text %d: expected %d, got %d",
                    idx,
                    self._dimension,
                    len(vector),
                )
            vectors.append(vector)
        return vectors

    def _embed_one(self, text: str, attempt: int) -> list[float]:
        _ = attempt  # reserved for retry-aware logging
        url = f"{self.base_url}/api/embeddings"
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": text,
        }

        for retry in range(self.max_retries):
            try:
                resp = self._session.post(
                    url,
                    json=payload,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                embedding = data.get("embedding")
                if embedding is None:
                    raise ValueError(f"No 'embedding' field in response: {data}")
                return embedding

            except (requests.RequestException, ValueError) as exc:
                logger.warning(
                    "Ollama embedding attempt %d/%d failed: %s",
                    retry + 1,
                    self.max_retries,
                    exc,
                )
                if retry < self.max_retries - 1:
                    sleep_time = self.retry_delay * (2 ** retry)
                    time.sleep(sleep_time)
                else:
                    raise RuntimeError(
                        f"Ollama embedding failed after {self.max_retries} attempts"
                    ) from exc

        # Should be unreachable – satisfy the type-checker
        raise RuntimeError("Unexpected: embedding retry loop exhausted")

    def __repr__(self) -> str:
        return f"OllamaEmbeddingProvider(model={self.model!r}, dim={self._dimension})"
