from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SourceDoc(BaseModel):
    """A single source document retrieved for a query."""

    content: str = Field(..., description="Document chunk content")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata (filename, page, etc.)"
    )
    score: float = Field(..., description="Relevance / similarity score")


class ChatRequest(BaseModel):
    """Incoming chat request from the frontend."""

    query: str = Field(..., min_length=1, description="User question")
    history: list[dict[str, str]] | None = Field(
        default=None, description="Previous conversation turns"
    )


class ChatResponse(BaseModel):
    """Non-streaming chat response."""

    answer: str = Field(..., description="LLM-generated answer")
    sources: list[SourceDoc] = Field(
        default_factory=list, description="Source documents referenced"
    )


class UploadResponse(BaseModel):
    """Response after a document has been ingested."""

    file_id: str = Field(..., description="Unique identifier for the uploaded file")
    filename: str = Field(..., description="Original filename")
    chunks_count: int = Field(..., description="Number of text chunks created")
    status: str = Field(default="success", description="Processing status")
