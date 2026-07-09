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
                content: str = data.get("message", {}).get("content", "")
                return content.lstrip()

            except (requests.RequestException, ValueError, KeyError) as exc:
                resp_body = ""
                if isinstance(exc, requests.HTTPError) and exc.response is not None:
                    resp_body = exc.response.text[:500]
                logger.warning(
                    "Ollama generate attempt %d/%d failed: %s response=%s",
                    attempt + 1,
                    self.max_retries,
                    exc,
                    resp_body,
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

                stripped_prefix = False

                for line in resp.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        logger.debug("Skipping unparseable stream line: %s", line[:80])
                        continue

                    token: str = chunk.get("message", {}).get("content", "")

                    # Strip deepseek-r1 thinking-phase leading whitespace
                    if token and not stripped_prefix:
                        token = token.lstrip()
                        if token:
                            stripped_prefix = True

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


# ---------------------------------------------------------------------------
# Anthropic (Messages API) implementation
# ---------------------------------------------------------------------------

class AnthropicProvider(LLMProvider):
    """LLM provider using the Anthropic Messages API.

    Compatible with Anthropic and third-party proxies that implement the
    same wire protocol (e.g. packyapi, openrouter).

    Parameters
    ----------
    base_url : str
        API base URL.
    api_key : str
        API key for authentication (sent as ``x-api-key`` header).
    model : str
        Model name, e.g. ``"deepseek-v4-flash"``.
    max_tokens : int
        Maximum tokens in the generated response.
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
        base_url: str = "https://api.anthropic.com",
        api_key: str = "",
        model: str = "claude-sonnet-5",
        max_tokens: int = 2048,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: float = 120.0,
        temperature: float = 0.7,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.temperature = temperature
        self._session = requests.Session()
        self._session.headers.update({
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        })

    # -- public API ---------------------------------------------------------

    def generate(self, messages: list[dict[str, str]]) -> str:
        url = f"{self.base_url}/v1/messages"

        # Anthropic Messages API requires system prompt as top-level param
        system_msg: str | None = None
        chat_messages: list[dict[str, Any]] = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                chat_messages.append({"role": m["role"], "content": m["content"]})

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": chat_messages,
            "temperature": self.temperature,
        }
        if system_msg:
            payload["system"] = system_msg

        for attempt in range(self.max_retries):
            try:
                resp = self._session.post(
                    url,
                    json=payload,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                data = resp.json()

                # Extract text blocks (skip thinking blocks)
                content_blocks: list[dict[str, Any]] = data.get("content", [])
                text_parts = [
                    b["text"]
                    for b in content_blocks
                    if b.get("type") == "text" and "text" in b
                ]
                return "".join(text_parts).lstrip()

            except (requests.RequestException, ValueError, KeyError) as exc:
                resp_body = ""
                if isinstance(exc, requests.HTTPError) and exc.response is not None:
                    resp_body = exc.response.text[:500]
                logger.warning(
                    "Anthropic generate attempt %d/%d failed: %s response=%s",
                    attempt + 1,
                    self.max_retries,
                    exc,
                    resp_body,
                )
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
                else:
                    raise RuntimeError(
                        f"Anthropic generate failed after {self.max_retries} attempts"
                    ) from exc

        raise RuntimeError("Unexpected: generate retry loop exhausted")

    def generate_stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        url = f"{self.base_url}/v1/messages"

        system_msg: str | None = None
        chat_messages: list[dict[str, Any]] = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                chat_messages.append({"role": m["role"], "content": m["content"]})

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": chat_messages,
            "temperature": self.temperature,
            "stream": True,
        }
        if system_msg:
            payload["system"] = system_msg

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

                # Force UTF-8 decoding — some proxies (e.g. packyapi) omit
                # charset from the Content-Type header, causing requests to
                # fall back to ISO-8859-1 which mangles multi-byte Unicode.
                for line_bytes in resp.iter_lines(decode_unicode=False):
                    if not line_bytes:
                        continue
                    line = line_bytes.decode("utf-8")
                    # Anthropic SSE: "data: {...}" or "event: ..."
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]  # strip "data: " prefix
                    if data_str == "[DONE]":
                        return

                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    event_type = chunk.get("type", "")
                    if event_type == "content_block_delta":
                        delta = chunk.get("delta", {})
                        if delta.get("type") == "text_delta":
                            token = delta.get("text", "")
                            if token:
                                yield token
                    elif event_type == "message_stop":
                        return

                return  # stream ended gracefully

            except (requests.RequestException, ValueError) as exc:
                last_exc = exc
                logger.warning(
                    "Anthropic stream attempt %d/%d failed: %s",
                    attempt + 1,
                    self.max_retries,
                    exc,
                )
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))

        raise RuntimeError(
            f"Anthropic stream failed after {self.max_retries} attempts"
        ) from last_exc

    def __repr__(self) -> str:
        return f"AnthropicProvider(model={self.model!r})"
