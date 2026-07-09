"""
Generation Module.

Provides an abstract LLM provider interface and a concrete Ollama
implementation.  Also includes ``build_rag_prompt``, a helper that
assembles ``messages`` arrays for RAG-style chat completions.

Usage::

    from pipeline.generation import OllamaProvider, build_rag_prompt

    llm = OllamaProvider(model="qwen2.5:7b")
    messages = build_rag_prompt(
        query="What is RAG?",
        context=retrieved_context_text,
        chat_history=[{"role": "user", "content": "Hello"}],
    )
    answer = llm.generate(messages)
    for token in llm.generate_stream(messages):
        print(token, end="")
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Iterator

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default RAG system prompt
# ---------------------------------------------------------------------------

DEFAULT_RAG_SYSTEM_PROMPT = """\
You are a helpful, accurate AI assistant.  Use the provided context \
documents to answer the user's question.

Instructions:
- Base your answer ONLY on the context provided below.  If the context \
does not contain enough information, say so honestly — do not make up facts.
- Cite the specific document numbers when you reference information from them.
- Answer in the same language as the user's question.
- Keep answers concise but complete."""


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_rag_prompt(
    query: str,
    context: str,
    chat_history: list[dict[str, str]] | None = None,
    system_prompt: str | None = None,
) -> list[dict[str, str]]:
    """Build a ``messages`` list for a RAG-style chat completion.

    Parameters
    ----------
    query : str
        The current user question.
    context : str
        Formatted context text (e.g. output of
        :meth:`Retriever.format_context`).
    chat_history : list[dict] or None
        Earlier turns as ``{"role": "user"|"assistant", "content": "..."}``.
    system_prompt : str or None
        Custom system prompt; falls back to :data:`DEFAULT_RAG_SYSTEM_PROMPT`.

    Returns
    -------
    list[dict]
        Messages array ready for an OpenAI/Ollama chat-completions endpoint.
    """
    system = system_prompt or DEFAULT_RAG_SYSTEM_PROMPT

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system},
    ]

    # Inject conversation history
    if chat_history:
        messages.extend(chat_history)

    # Inject the user message with context
    user_content = f"Context:\n---\n{context}\n---\n\nQuestion: {query}"
    messages.append({"role": "user", "content": user_content})

    return messages


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    """Abstract base for LLM generation providers."""

    @abstractmethod
    def generate(self, messages: list[dict[str, str]]) -> str:
        """Synchronous completion – returns the full response text."""
        ...

    @abstractmethod
    def generate_stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        """Streaming completion – yields tokens one at a time."""
        ...


# ---------------------------------------------------------------------------
# Ollama implementation
# ---------------------------------------------------------------------------

class OllamaProvider(LLMProvider):
    """Ollama chat provider using the ``/api/chat`` endpoint.

    Parameters
    ----------
    base_url : str
        Ollama server base URL.
    model : str
        Model name, e.g. ``"qwen2.5:7b"``.
    max_retries : int
        Retry count on transient failures.
    retry_delay : float
        Base delay in seconds for exponential backoff.
    timeout : float
        Request timeout in seconds.
    temperature : float
        Sampling temperature (0–2).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:7b",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: float = 120.0,
        temperature: float = 0.7,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.temperature = temperature
        self._session = requests.Session()

    # -- public API ---------------------------------------------------------

    def generate(self, messages: list[dict[str, str]]) -> str:
        url = f"{self.base_url}/api/chat"
        payload = self._build_payload(messages, stream=False)

        for attempt in range(self.max_retries):
            try:
                resp = self._session.post(
                    url,
                    json=payload,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                content = data.get("message", {}).get("content", "")
                return content

            except (requests.RequestException, ValueError, KeyError) as exc:
                logger.warning(
                    "Ollama generate attempt %d/%d failed: %s",
                    attempt + 1,
                    self.max_retries,
                    exc,
                )
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
                else:
                    raise RuntimeError(
                        f"Ollama generate failed after {self.max_retries} attempts"
                    ) from exc

        raise RuntimeError("Unexpected: generate retry loop exhausted")

    def generate_stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        url = f"{self.base_url}/api/chat"
        payload = self._build_payload(messages, stream=True)

        last_exc: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                resp = self._session.post(
                    url,
                    json=payload,
                    timeout=self.timeout,
                    stream=True,
                )
                resp.raise_for_status()

                for line in resp.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        logger.debug("Skipping unparseable stream line: %s", line[:80])
                        continue

                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        yield token

                    # Honour the done flag
                    if chunk.get("done", False):
                        return

                return  # stream ended gracefully

            except (requests.RequestException, ValueError) as exc:
                last_exc = exc
                logger.warning(
                    "Ollama stream attempt %d/%d failed: %s",
                    attempt + 1,
                    self.max_retries,
                    exc,
                )
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
                # else: fall through to raise

        raise RuntimeError(
            f"Ollama stream failed after {self.max_retries} attempts"
        ) from last_exc

    # -- internal -----------------------------------------------------------

    def _build_payload(
        self,
        messages: list[dict[str, str]],
        stream: bool,
    ) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": self.temperature,
            },
        }

    def __repr__(self) -> str:
        return f"OllamaProvider(model={self.model!r})"
