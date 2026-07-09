# DOCX 元数据清理 + Chunk 上下文注入 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复"易方达需求有哪些"查询失败的两个根因：(1) Chunk 不含文档名导致 embedding 无法关联查询，(2) DOCX 修订记录等元数据噪音污染 Chunk 0。

**Architecture:** 在清洗链中新增 `DocxMetadataCleaningStep` 去除中文文档元数据模式；在分块阶段注入文档标题前缀使每个 chunk 的 embedding 能关联到所属文档。

**Tech Stack:** Python 3.13, python-docx, regex, 现有 CleaningStep ABC 模式

---

## 文件变更总览

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `backend/app/pipeline/cleaning.py` | 新增 `DocxMetadataCleaningStep` |
| 修改 | `backend/app/api/dependencies.py` | 将新 step 加入默认清洗链 |
| 修改 | `backend/app/api/upload.py` | `_chunk_text()` 支持上下文前缀注入 |
| 新增 | `backend/tests/pipeline/test_cleaning.py` | 清洗步骤单元测试 |
| 新增 | `backend/tests/api/test_upload.py` | 分块上下文注入测试 |

---

### Task 1: DocxMetadataCleaningStep — 清洗步骤实现

**Files:**
- Modify: `backend/app/pipeline/cleaning.py` (在 `RAGChunkingStep` 类之后追加)
- Create: `backend/tests/pipeline/test_cleaning.py`

- [ ] **Step 1: 编写 `DocxMetadataCleaningStep` 的单元测试**

```python
# backend/tests/pipeline/test_cleaning.py
"""Tests for cleaning pipeline steps."""

import pytest
from app.pipeline.cleaning import (
    BasicCleaningStep,
    DocxMetadataCleaningStep,
    QualityFilterStep,
    RAGChunkingStep,
    StructureCleaningStep,
)


class TestDocxMetadataCleaningStep:
    """Tests for DocxMetadataCleaningStep."""

    @pytest.fixture
    def step(self):
        return DocxMetadataCleaningStep()

    def test_removes_revision_history_table(self, step):
        """修订记录表格行应被移除."""
        text = (
            "需求分析说明书 第2.0版 2026年4月\n"
            "文档修订记录 *修订状态:C——创建,A——增加,M——修改,D——删除\n"
            "(备注:此文档中的图片示例均为原型示意图)\n"
            "一、更新提醒机制\n"
            "1、需求描述\n"
        )
        result = step.clean(text)
        assert "修订记录" not in result
        assert "修订状态" not in result
        assert "一、更新提醒机制" in result
        assert "1、需求描述" in result

    def test_removes_version_header(self, step):
        """版本号 + 日期行应被移除."""
        text = (
            "需求规格说明书 第1.0版 2025年12月\n"
            "实际正文内容开始。\n"
        )
        result = step.clean(text)
        assert "需求规格说明书" not in result
        assert "第1.0版" not in result
        assert "实际正文内容开始" in result

    def test_removes_remark_about_prototypes(self, step):
        """原型示意图备注行应被移除."""
        text = (
            "(备注:此文档中的图片示例均为原型示意图,前端实现时会遵守UI设计规范)\n"
            "正文内容。\n"
        )
        result = step.clean(text)
        assert "原型示意图" not in result
        assert "正文内容" in result

    def test_preserves_normal_content(self, step):
        """正文内容不应受影响."""
        text = (
            "一、更新提醒机制\n"
            "1、需求描述 实现方案 在设置下新增更新提醒配置菜单\n"
        )
        result = step.clean(text)
        assert "一、更新提醒机制" in result
        assert "更新提醒配置菜单" in result

    def test_handles_empty_text(self, step):
        """空文本应安全处理."""
        assert step.clean("") == ""
        assert step.clean(None) == ""  # type: ignore

    def test_removes_multiple_metadata_lines(self, step):
        """多行元数据应全部移除."""
        text = (
            "需求分析说明书 第2.0版 2026年4月\n"
            "文档修订记录 *修订状态:C——创建,A——增加,M——修改,D——删除\n"
            "(备注:图片为原型示意图)\n"
            "\n"
            "一、功能介绍\n"
            "具体功能描述。\n"
        )
        result = step.clean(text)
        lines = result.strip().split("\n")
        assert lines[0] == "一、功能介绍"
        assert "具体功能描述" in result
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/pipeline/test_cleaning.py::TestDocxMetadataCleaningStep -v
```
Expected: 全部 FAIL（`DocxMetadataCleaningStep` 未定义）

- [ ] **Step 3: 实现 `DocxMetadataCleaningStep`**

在 `backend/app/pipeline/cleaning.py` 的 `RAGChunkingStep` 类之后、`CleaningPipeline` 类之前插入：

```python
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
        # "(备注:此文档中的图片示例均为原型示意图...)"
        re.compile(r"^\(备注:\s*此文档中的(?:图片|图表|截图)示例均为原型示意图"),
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && python -m pytest tests/pipeline/test_cleaning.py::TestDocxMetadataCleaningStep -v
```
Expected: 全部 PASS

- [ ] **Step 5: 将 `DocxMetadataCleaningStep` 加入默认清洗链**

修改 `backend/app/api/dependencies.py:get_cleaning_pipeline()`：

```python
# 修改后的 get_cleaning_pipeline (行 23-39)
@lru_cache()
def get_cleaning_pipeline():
    """Return a singleton CleaningPipeline with default steps."""
    from app.pipeline.cleaning import (
        BasicCleaningStep,
        CleaningPipeline,
        DocxMetadataCleaningStep,   # 新增
        QualityFilterStep,
        RAGChunkingStep,
        StructureCleaningStep,
    )

    logger.info("Initialising CleaningPipeline with default steps")
    pipeline = CleaningPipeline()
    pipeline.add_step(BasicCleaningStep())
    pipeline.add_step(StructureCleaningStep())
    pipeline.add_step(DocxMetadataCleaningStep())  # 新增：在 Structure 之后、Quality 之前
    pipeline.add_step(QualityFilterStep())
    pipeline.add_step(RAGChunkingStep())
    return pipeline
```

- [ ] **Step 6: 运行完整清洗链测试确认兼容性**

```bash
cd backend && python -m pytest tests/pipeline/ -v
```
Expected: 所有已有测试 PASS（如有），新增测试 PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/lanzhang/Desktop/rag-chatbot
git add backend/app/pipeline/cleaning.py backend/app/api/dependencies.py backend/tests/pipeline/test_cleaning.py
git commit -m "feat: add DocxMetadataCleaningStep to strip document metadata noise"
```

---

### Task 2: Chunk 上下文注入 — 每个 Chunk 携带文档标题

**Files:**
- Modify: `backend/app/api/upload.py:_chunk_text()` 和调用处
- Create: `backend/tests/api/test_upload.py`

- [ ] **Step 1: 编写 `_chunk_text` 上下文注入的单元测试**

```python
# backend/tests/api/test_upload.py
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
        # 正文远大于 chunk_size
        text = "\n\n".join(["段落" + str(i) for i in range(50)])
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/api/test_upload.py -v
```
Expected: FAIL（`_chunk_text` 不支持 `context_prefix` 参数）

- [ ] **Step 3: 修改 `_chunk_text()` 支持上下文前缀**

修改 `backend/app/api/upload.py` 的 `_chunk_text` 函数签名和逻辑：

```python
def _chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
    context_prefix: str | None = None,
) -> list[str]:
    """Split *cleaned* text into overlapping paragraph-oriented chunks.

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
            chunks.append("\n\n".join(current))
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
```

- [ ] **Step 4: 修改 upload 路由调用 `_chunk_text` 时传入 `context_prefix`**

修改 `backend/app/api/upload.py` 行 163-165：

```python
    # --- Chunk ------------------------------------------------------------------
    # Inject document filename as context prefix so every chunk's embedding
    # captures the document association — critical for retrieval quality.
    context_prefix = f"[文档: {file.filename}]"
    chunks = _chunk_text(cleaned_text, context_prefix=context_prefix)
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd backend && python -m pytest tests/api/test_upload.py -v
```
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/lanzhang/Desktop/rag-chatbot
git add backend/app/api/upload.py backend/tests/api/test_upload.py
git commit -m "feat: inject document filename as context prefix in each chunk"
```

---

### Task 3: 端到端验证

- [ ] **Step 1: 清空旧向量数据并重启后端**

```bash
rm -rf /Users/lanzhang/Desktop/rag-chatbot/backend/data/chroma/
```
后端会自动重载（uvicorn --reload）。

- [ ] **Step 2: 重新上传易方达文档**

```bash
curl -s -X POST http://localhost:8000/api/upload \
  -F "file=@/path/to/易方达新增需求方案设计2026.4.8 v2.0.docx"
```
Expected: `{"status": "success", "chunks_count": N}`

- [ ] **Step 3: 验证清洗效果**

```bash
cd backend && python3 -c "
from app.pipeline.storage import ChromaVectorStore
from app.pipeline.embedding import OllamaEmbeddingProvider

provider = OllamaEmbeddingProvider(model='bge-m3')
store = ChromaVectorStore(
    collection_name='rag_documents',
    persist_directory='./data/chroma',
    embedding_provider=provider
)
results = store.search('易方达需求有哪些', top_k=10)
yfd = [r for r in results if '易方达' in r['metadata'].get('filename', '')]
print(f'易方达 chunks in top-10: {len(yfd)}')
for r in yfd[:5]:
    idx = r['metadata'].get('chunk_index', '?')
    score = 1.0 - r.get('distance', 0)
    preview = r['text'][:120]
    print(f'  Chunk {idx}: score={score:.4f} | {preview}...')
"
```
Expected:
- 易方达 chunks 在 top-10 中 ≥ 5 个（之前只有 3 个）
- Chunk 0 不再包含"文档修订记录"、"修订状态"等元数据
- 每个 chunk 以 `[文档: 易方达新增需求方案设计...]` 开头

- [ ] **Step 4: 验证问答质量**

```bash
curl -s -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "易方达需求有哪些"}'
```
Expected:
- `answer` 列出多项易方达需求（更新提醒、上传提醒、批量下载/下线、邮箱发送、飞书分享等）
- `sources` 大部分来自易方达文档，而非无关的 AI 文章
- 不再把"BGE-M3 搭配 Ollama"或"向量数据库选型"当作易方达需求

- [ ] **Step 5: Commit**

```bash
cd /Users/lanzhang/Desktop/rag-chatbot
git add -A
git commit -m "verify: e2e validation of docx cleaning + chunk context injection"
```

---

## 自审

### 1. 需求覆盖
- [x] DOCX 元数据清理 → Task 1: `DocxMetadataCleaningStep`
- [x] Chunk 上下文注入 → Task 2: `_chunk_text` + `context_prefix`
- [x] 端到端验证 → Task 3: 清库→上传→检索验证→问答验证

### 2. Placeholder 检查
- 无 TBD/TODO/placeholder
- 所有步骤包含实际代码
- 所有命令包含预期输出

### 3. 类型一致性
- `context_prefix: str | None = None` 签名在 `_chunk_text` 定义和测试中一致
- `DocxMetadataCleaningStep.name` 返回 `"docx_metadata"`，在 stats 字典中作为 key
