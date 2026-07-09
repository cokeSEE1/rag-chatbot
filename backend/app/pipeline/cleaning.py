"""
Data Cleaning Module.

Implements a chain-of-responsibility pipeline for text cleaning with five levels:
    Level 1 - Basic: Unicode normalization, line endings, whitespace compression
    Level 2 - Structure: Remove HTML tags, Markdown link/image syntax
    Level 2.5 - DOCX metadata: Strip revision history, version headers, prototype
        disclaimers from enterprise .docx documents
    Level 3 - Quality: Length checks, whitespace ratio checks
    Level 4 - RAG-specific: Paragraph chunking, short paragraph merging

Usage:
    pipeline = CleaningPipeline()
    pipeline.add_step(BasicCleaningStep())
    pipeline.add_step(StructureCleaningStep())
    pipeline.add_step(DocxMetadataCleaningStep())
    pipeline.add_step(QualityFilterStep(min_length=10, max_whitespace_ratio=0.8))
    pipeline.add_step(RAGChunkingStep(min_chunk_length=50, merge_short=True))
    result = pipeline.clean(text)
"""

from __future__ import annotations

import logging
import re
import unicodedata
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class CleaningStep(ABC):
    """Abstract base for a single cleaning step.

    Each step implements a focused transformation that receives text and
    returns cleaned text.  Steps are stateless so the same instance can be
    reused safely across calls.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name used in stats/logging."""
        ...

    @abstractmethod
    def clean(self, text: str) -> str:
        """Apply this cleaning step and return the transformed text."""
        ...


# ---------------------------------------------------------------------------
# Level 1 — Basic normalisation
# ---------------------------------------------------------------------------

class BasicCleaningStep(CleaningStep):
    """Normalise line-endings, compress whitespace, Unicode NFKC normalise."""

    @property
    def name(self) -> str:
        return "basic"

    def clean(self, text: str) -> str:
        if not text:
            return text
        # 1. Unicode NFKC normalisation (fullwidth chars, ligatures, etc.)
        text = unicodedata.normalize("NFKC", text)
        # 2. Normalise line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # 3. Collapse multiple whitespace (preserves single newlines)
        text = re.sub(r"[^\S\n]+", " ", text)
        # 4. Collapse 3+ consecutive newlines into 2
        text = re.sub(r"\n{3,}", "\n\n", text)
        # 5. Strip leading/trailing whitespace
        return text.strip()


# ---------------------------------------------------------------------------
# Level 2 — Structure removal
# ---------------------------------------------------------------------------

class StructureCleaningStep(CleaningStep):
    """Remove HTML tags and Markdown link / image syntax.

    Leaves the visible / alt text intact so semantic content is preserved.
    """

    # Regex patterns – compiled once at class level
    _HTML_TAG_RE = re.compile(r"<[^>]*>")
    _MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")        # ![alt](url)
    _MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]+\)")          # [text](url)

    @property
    def name(self) -> str:
        return "structure"

    def clean(self, text: str) -> str:
        if not text:
            return text
        # 1. Remove HTML tags entirely
        text = self._HTML_TAG_RE.sub("", text)
        # 2. Markdown images: keep the alt text
        text = self._MD_IMAGE_RE.sub(r"\1", text)
        # 3. Markdown links: keep the link text
        text = self._MD_LINK_RE.sub(r"\1", text)
        return text


# ---------------------------------------------------------------------------
# Level 3 — Quality filter
# ---------------------------------------------------------------------------

class QualityFilterStep(CleaningStep):
    """Filter out texts that fail quality heuristics.

    Parameters
    ----------
    min_length : int
        Minimum number of characters required (default 5).
    max_whitespace_ratio : float
        Maximum fraction of characters that may be whitespace (default 0.95).
    """

    def __init__(
        self,
        min_length: int = 5,
        max_whitespace_ratio: float = 0.95,
    ) -> None:
        self.min_length = min_length
        self.max_whitespace_ratio = max_whitespace_ratio

    @property
    def name(self) -> str:
        return "quality_filter"

    def clean(self, text: str) -> str:
        if not text:
            return ""
        text = text.strip()

        # Length check
        if len(text) < self.min_length:
            logger.debug("QualityFilter: text too short (%d chars), dropping", len(text))
            return ""

        # Whitespace ratio check
        whitespace_ratio = sum(1 for c in text if c.isspace()) / max(len(text), 1)
        if whitespace_ratio > self.max_whitespace_ratio:
            logger.debug(
                "QualityFilter: whitespace ratio %.2f exceeds threshold %.2f, dropping",
                whitespace_ratio,
                self.max_whitespace_ratio,
            )
            return ""

        return text


# ---------------------------------------------------------------------------
# Level 4 — RAG-specific paragraph chunking
# ---------------------------------------------------------------------------

class RAGChunkingStep(CleaningStep):
    """Split text into paragraphs and optionally merge short neighbours.

    Parameters
    ----------
    min_chunk_length : int
        Paragraphs shorter than this will be merged with the following one
        to maintain context.  Default 80.
    merge_short : bool
        Whether to merge short paragraphs.  Default True.
    """

    def __init__(
        self,
        min_chunk_length: int = 80,
        merge_short: bool = True,
    ) -> None:
        self.min_chunk_length = min_chunk_length
        self.merge_short = merge_short

    @property
    def name(self) -> str:
        return "rag_chunking"

    def clean(self, text: str) -> str:
        if not text:
            return text

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text)]
        paragraphs = [p for p in paragraphs if p]  # drop empty

        if not self.merge_short or not paragraphs:
            return "\n\n".join(paragraphs)

        merged: list[str] = []
        buffer = ""

        for para in paragraphs:
            if len(para) < self.min_chunk_length:
                # Short paragraph – accumulate into buffer
                buffer = (buffer + " " + para).strip() if buffer else para
            else:
                if buffer:
                    # Finalise the accumulated buffer
                    merged.append(buffer)
                    buffer = ""
                merged.append(para)

        if buffer:
            # Attach remaining buffer to the last paragraph (if any)
            if merged:
                merged[-1] = merged[-1] + " " + buffer
            else:
                merged.append(buffer)

        return "\n\n".join(merged)


# ---------------------------------------------------------------------------
# Level 2.5 — DOCX metadata stripping
# ---------------------------------------------------------------------------

class DocxMetadataCleaningStep(CleaningStep):
    """Remove common Chinese document metadata patterns from extracted text.

    Targets patterns frequently found in enterprise .docx documents:
    document revision history tables, version headers, prototype disclaimers,
    and other boilerplate that wastes retrieval slots.
    """

    # Patterns that indicate a line is document metadata (not content)
    _METADATA_PATTERNS: list[re.Pattern[str]] = [
        # "需求分析说明书 第2.0版" / "需求规格说明书 第1.0版"
        re.compile(
            r"^(需求(?:分析|规格)说明书)\s*第?\d+(?:\.\d+)?版\s*\d{4}年\d+月\s*$"
        ),
        # "文档修订记录 *修订状态:C——创建,A——增加,M——修改,D——删除"
        re.compile(r"^文档修订记录\s*\*修订状态:"),
        # "*修订状态:...*" standalone
        re.compile(r"^\*修订状态:.*\*$"),
        # "(备注:此文档中的图片示例均为原型示意图...)" or "(备注:图片为原型示意图)"
        re.compile(r"^\(备注:.*原型示意图"),
        # Generic version + date header "第X.X版 YYYY年MM月"
        re.compile(r"^第\d+(?:\.\d+)?版\s*\d{4}年\d+月\s*$"),
    ]

    @property
    def name(self) -> str:
        return "docx_metadata"

    def clean(self, text: str) -> str:
        if not text:
            return ""

        lines = text.split("\n")
        kept: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                # Preserve blank lines as paragraph separators
                # but don't accumulate consecutive blank lines
                if kept and kept[-1] != "":
                    kept.append("")
                continue

            # Check against all metadata patterns
            if any(pat.search(stripped) for pat in self._METADATA_PATTERNS):
                logger.debug(
                    "DocxMetadata: stripping metadata line: %s",
                    stripped[:80],
                )
                continue

            kept.append(line)

        # Strip leading/trailing blank lines
        while kept and kept[0] == "":
            kept.pop(0)
        while kept and kept[-1] == "":
            kept.pop(-1)

        return "\n".join(kept)


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------

class CleaningPipeline:
    """Chain multiple :class:`CleaningStep` instances together.

    Usage::

        pipeline = CleaningPipeline()
        pipeline.add_step(BasicCleaningStep())
        pipeline.add_step(StructureCleaningStep())
        result = pipeline.clean(raw_text)
        # result == {"text": "...", "stats": {...}, "errors": [...]}
    """

    def __init__(self) -> None:
        self._steps: list[CleaningStep] = []

    def add_step(self, step: CleaningStep) -> None:
        """Append a cleaning step to the pipeline."""
        self._steps.append(step)

    @property
    def steps(self) -> list[CleaningStep]:
        """Return the ordered list of registered steps (read-only)."""
        return list(self._steps)

    def clean(self, text: str) -> dict[str, Any]:
        """Run every registered step sequentially.

        Returns
        -------
        dict
            ``{"text": str, "stats": dict, "errors": list[str]}``
        """
        stats: dict[str, dict[str, int]] = {}
        errors: list[str] = []
        current = text

        for step in self._steps:
            length_before = len(current) if current else 0
            try:
                current = step.clean(current)
            except Exception:
                logger.exception("Cleaning step '%s' raised an error", step.name)
                errors.append(f"Step '{step.name}' failed: retaining pre-step text")
                # Keep the text from before the failed step
                continue

            length_after = len(current) if current else 0
            stats[step.name] = {
                "length_before": length_before,
                "length_after": length_after,
                "delta": length_after - length_before,
            }

        return {
            "text": current,
            "stats": stats,
            "errors": errors,
        }
