"""Tests for upload API helpers."""

import pytest
from app.api.upload import _chunk_text


class TestChunkText:
    """Tests for _chunk_text with context prefix."""

    def test_injects_context_prefix(self):
        """每个 chunk 应以文档上下文前缀开头."""
        text = "段落A\n\n段落B内容较多需要分成多个chunk\n\n" + ("段落C " * 50)
        chunks = _chunk_text(
            text,
            chunk_size=100,
            overlap=20,
            context_prefix="[文档: 易方达需求说明书]",
        )
        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.startswith("[文档: 易方达需求说明书]")

    def test_context_prefix_not_counted_in_chunk_size(self):
        """上下文前缀不计入 chunk_size，正文仍然以 chunk_size 为准."""
        prefix = "[文档: 测试文档]"
        # 每个段落长度 ~3-4 chars, 用多个 double-newline 分隔保证段落足够多
        # 最终正文远大于 chunk_size=200, 确保分成多个 chunk
        text = "\n\n".join(["段落" + str(i) for i in range(200)])
        chunks = _chunk_text(
            text,
            chunk_size=200,
            overlap=20,
            context_prefix=prefix,
        )
        assert len(chunks) > 1  # 应该被分成多个 chunk

    def test_no_prefix_when_none(self):
        """不传 context_prefix 时行为不变（向后兼容）."""
        text = "段落A\n\n段落B"
        chunks = _chunk_text(text, context_prefix=None)
        assert len(chunks) > 0
        assert chunks[0].startswith("段落A")

    def test_empty_text_returns_empty(self):
        """空文本返回空列表."""
        chunks = _chunk_text("", context_prefix="[文档: X]")
        assert chunks == []

    def test_prefix_preserves_content(self):
        """上下文前缀加在 chunk 前面但正文内容完整."""
        prefix = "[文档: 测试]"
        text = "第一段内容\n\n第二段内容"
        chunks = _chunk_text(text, chunk_size=500, overlap=10, context_prefix=prefix)
        assert len(chunks) == 1
        assert "第一段内容" in chunks[0]
        assert "第二段内容" in chunks[0]
