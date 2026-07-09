"""
Chat API — RAG query endpoint with optional SSE streaming.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_llm_provider, get_retriever
from app.models.schemas import ChatRequest, ChatResponse, SourceDoc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def build_rag_prompt(
    query: str,
    context: str,
    history: list[dict[str, str]] | None = None,
) -> str:
    """Construct a RAG prompt from the query, retrieved context, and history.

    Parameters
    ----------
    query : str
        Current user question.
    context : str
        Concatenated document chunks deemed relevant by the retriever.
    history : list[dict[str, str]] | None
        Previous conversation turns as ``[{"role": "user|assistant", "content": ...}]``.

    Returns
    -------
    str
        A formatted prompt string ready to be sent to the LLM.
    """
    if not history:
        history_text = ""
    else:
        lines: list[str] = []
        for turn in history:
            role = turn.get("role", "unknown")
            content = turn.get("content", "")
            lines.append(f"{role}: {content}")
        history_text = "\n".join(lines)

    prompt = f"""你是一个知识库问答助手。请根据以下参考资料回答用户的问题。

{history_text}

参考资料：
{context}

用户问题：{query}

请基于以上参考资料提供准确、有帮助的回答。如果参考资料中找不到相关信息，请如实说明。"""
    return prompt


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    retriever=Depends(get_retriever),
    llm=Depends(get_llm_provider),
) -> ChatResponse:
    """Non-streaming RAG chat endpoint."""
    try:
        # 1. Retrieve relevant documents
        retrieved_docs = retriever.retrieve(request.query)

        # 2. Build context string from retrieved docs
        context_parts: list[str] = []
        sources: list[SourceDoc] = []
        for doc in retrieved_docs:
            context_parts.append(doc.get("content", ""))
            sources.append(
                SourceDoc(
                    content=doc.get("content", ""),
                    metadata=doc.get("metadata", {}),
                    score=doc.get("score", 0.0),
                )
            )

        context = "\n\n---\n\n".join(context_parts) if context_parts else "暂无相关参考资料。"

        # 3. Build prompt and generate answer
        prompt = build_rag_prompt(request.query, context, request.history)
        answer = llm.generate(prompt)

        return ChatResponse(answer=answer, sources=sources)

    except ImportError as exc:
        logger.error("Pipeline module not available: %s", exc)
        raise HTTPException(
            status_code=501,
            detail="Pipeline modules are not yet implemented.",
        )
    except Exception as exc:
        logger.exception("Chat error")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    retriever=Depends(get_retriever),
    llm=Depends(get_llm_provider),
):
    """Streaming RAG chat endpoint using Server-Sent Events."""

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # 1. Retrieve
            retrieved_docs = retriever.retrieve(request.query)

            context_parts: list[str] = []
            for doc in retrieved_docs:
                context_parts.append(doc.get("content", ""))

            context = (
                "\n\n---\n\n".join(context_parts)
                if context_parts
                else "暂无相关参考资料。"
            )

            # 2. Build prompt
            prompt = build_rag_prompt(request.query, context, request.history)

            # 3. Stream tokens
            async for token in llm.generate_stream(prompt):
                yield f"data: {json.dumps({'token': token})}\n\n"

            # 4. Send sources as the final event
            sources_data = [
                {
                    "content": doc.get("content", ""),
                    "metadata": doc.get("metadata", {}),
                    "score": doc.get("score", 0.0),
                }
                for doc in retrieved_docs
            ]
            yield f"data: {json.dumps({'sources': sources_data})}\n\n"
            yield "data: [DONE]\n\n"

        except ImportError as exc:
            logger.error("Pipeline module not available: %s", exc)
            yield f"data: {json.dumps({'error': 'Pipeline modules are not yet implemented.'})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            logger.exception("Chat stream error")
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
