"""
Document upload & ingestion API.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.dependencies import (
    get_cleaning_pipeline,
    get_embedding_provider,
    get_vector_store,
)
from app.config import get_settings
from app.models.schemas import UploadResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _read_text(file_path: Path) -> str:
    """Read plain text from a file (txt, md, or already decoded)."""
    return file_path.read_text(encoding="utf-8")


def _chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
    context_prefix: str | None = None,
) -> list[str]:
    """Split *cleaned* text into overlapping paragraph-oriented chunks.

    A simple paragraph-based chunker: splits on double-newline first, then
    merges short segments until ``chunk_size`` is reached, adding ``overlap``
    characters from the previous chunk.

    Parameters
    ----------
    text : str
        Cleaned text to chunk.
    chunk_size : int
        Target maximum chunk size in characters (for body text, excluding prefix).
    overlap : int
        Number of characters to overlap between consecutive chunks.
    context_prefix : str or None
        Optional prefix prepended to every chunk (e.g. "[文档: filename]").
        The prefix is NOT counted against chunk_size so body content length is
        preserved.  This ensures the embedding captures document association.

    Returns
    -------
    list[str]
        Chunk strings ready for embedding.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) > chunk_size and current:
            # Finalise previous chunk
            chunks.append("\n\n".join(current))
            # Start new chunk with overlap
            overlap_text = "\n\n".join(current)[-overlap:] if overlap > 0 else ""
            if overlap_text:
                current = [overlap_text]
                current_len = len(overlap_text)
            else:
                current = []
                current_len = 0

        current.append(para)
        current_len += len(para)

    if current:
        chunks.append("\n\n".join(current))

    # Inject context prefix into every chunk (after chunking so prefix
    # doesn't affect chunk size calculation)
    if context_prefix:
        chunks = [f"{context_prefix}\n{chunk}" for chunk in chunks]

    return chunks


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("/documents")
async def list_documents(
    vector_store=Depends(get_vector_store),
) -> list[dict]:
    """Return all uploaded documents (grouped by file_id)."""
    return vector_store.list_documents()


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    cleaning_pipeline=Depends(get_cleaning_pipeline),
    embedding_provider=Depends(get_embedding_provider),
    vector_store=Depends(get_vector_store),
) -> UploadResponse:
    """Accept a document, clean it, chunk it, embed chunks, and store in ChromaDB.

    Supported formats: ``.txt``, ``.md``, ``.pdf``, ``.docx``.
    Maximum file size: 10 MB.
    """
    # --- Validate file -----------------------------------------------------------
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Read content (limit by MAX_FILE_SIZE)
    content_bytes = await file.read()
    if len(content_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)} MB.",
        )

    # --- Save original file to disk ----------------------------------------------
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_id = uuid.uuid4().hex
    saved_path = upload_dir / f"{file_id}{ext}"
    saved_path.write_bytes(content_bytes)

    # --- Decode text -------------------------------------------------------------
    # For .txt / .md we can read directly.
    # For .pdf / .docx the cleaning pipeline is expected to handle extraction.
    try:
        if ext in {".txt", ".md"}:
            raw_text = content_bytes.decode("utf-8")
        elif ext == ".pdf":
            # Attempt to extract text; pipeline may have a pdf reader
            raw_text = _extract_pdf_text(saved_path)
        elif ext == ".docx":
            raw_text = _extract_docx_text(saved_path)
        else:
            raw_text = content_bytes.decode("utf-8")
    except Exception as exc:
        logger.exception("Failed to decode file %s", file.filename)
        raise HTTPException(status_code=400, detail=f"Cannot read file: {exc}")

    # --- Clean -------------------------------------------------------------------
    cleaned_result = cleaning_pipeline.clean(raw_text)
    cleaned_text = cleaned_result["text"] if isinstance(cleaned_result, dict) else cleaned_result

    # --- Chunk -------------------------------------------------------------------
    # Inject document filename as context prefix so every chunk's embedding
    # captures the document association — critical for retrieval quality.
    context_prefix = f"[文档: {file.filename}]"
    chunks = _chunk_text(cleaned_text, context_prefix=context_prefix)

    if not chunks:
        raise HTTPException(
            status_code=400, detail="No processable text found in the document."
        )

    # --- Embed & store ----------------------------------------------------------
    metadatas = [
        {
            "file_id": file_id,
            "filename": file.filename,
            "chunk_index": idx,
        }
        for idx in range(len(chunks))
    ]
    vector_store.add(texts=chunks, metadatas=metadatas)

    logger.info(
        "Ingested '%s' → %d chunks (file_id=%s)",
        file.filename,
        len(chunks),
        file_id,
    )

    return UploadResponse(
        file_id=file_id,
        filename=file.filename,
        chunks_count=len(chunks),
        status="success",
    )


# ---------------------------------------------------------------------------
# Text extraction stubs (will be replaced by pipeline internals)
# ---------------------------------------------------------------------------

def _extract_pdf_text(_file_path: Path) -> str:
    """Extract text from a PDF file.

    NOTE: This is a stub. The cleaning pipeline should provide a proper
    PDF reader once it is implemented. For now, we raise so the caller
    gets a clear message.
    """
    raise NotImplementedError(
        "PDF text extraction is not yet implemented. "
        "Please add it to the cleaning pipeline."
    )


def _extract_docx_text(file_path: Path) -> str:
    """Extract text from a DOCX file using python-docx.

    Iterates over all paragraphs in the document body. Headers, footers,
    tables, and text boxes are intentionally skipped for now — they can be
    added as the pipeline matures.

    Parameters
    ----------
    file_path : Path
        Path to the .docx file.

    Returns
    -------
    str
        Extracted text with paragraphs separated by double newlines.
    """
    try:
        from docx import Document
    except ImportError:
        raise ImportError(
            "python-docx is required to process .docx files. "
            "Install it with: pip install python-docx"
        )

    doc = Document(str(file_path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    if not paragraphs:
        raise ValueError("No text found in the document.")
    return "\n\n".join(paragraphs)
