# 检索过程可视化 — 设计方案

**日期**: 2026-07-09  
**状态**: 已确认  
**原型**: `.superpowers/brainstorm/77128-1783599812/content/full-app.html`

## 目标

在 RAG 问答时让用户看到检索过程：召回数量、召回内容、检索耗时，并在前端实时展示。

## 交互时序（方案 C：并行展示）

```
用户提问
  → 后端收到请求
  → SSE event: retrieval_start（"正在检索..."）
  → 后端完成检索
  → SSE event: retrieval_done（召回 N 个片段 + 内容 + 耗时）
  → 前端展示检索卡片（片段列表 + 耗时徽标）
  → SSE event: token × N（流式输出回答）
  → 前端同步渲染回答
  → SSE event: sources（最终来源列表）
  → SSE event: [DONE]
  → 前端：检索卡片折叠为摘要，来源可展开
```

## 接口变更

### SSE 事件流（新增事件）

当前事件流：
```
data: {"token": "..."}       // N 次
data: {"sources": [...]}     // 1 次
data: [DONE]
```

新事件流：
```
data: {"type":"retrieval_start"}                        // 1 次（新增）
data: {"type":"retrieval_done","count":5,"latency_ms":320,"results":[...]}  // 1 次（新增）
data: {"token":"..."}                                   // N 次（不变）
data: {"sources":[...]}                                  // 1 次（不变）
data: [DONE]
```

### retrieval_done 数据结构

```json
{
  "type": "retrieval_done",
  "count": 5,
  "latency_ms": 320,
  "results": [
    {
      "content": "RAG 是一种将信息检索与文本生成相结合的 AI 架构...",
      "metadata": {"filename": "RAG技术白皮书.md", "source": "..."},
      "score": 0.91
    }
  ]
}
```

## 后端改动

### `app/models/schemas.py` — 新增 `RetrievalResult`

```python
class RetrievalResult(BaseModel):
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float
```

### `app/api/chat.py` — 修改 `chat_stream`

在检索步骤后、生成步骤前，新增两个 yield：

```python
# 1. 发送检索开始事件
yield f"data: {json.dumps({'type': 'retrieval_start'})}\n\n"

# 2. 检索
retrieved_docs = retriever.retrieve(request.query)

# 3. 发送检索完成事件
results_data = [
    {
        "content": doc.get("text", ""),
        "metadata": doc.get("metadata", {}),
        "score": 1.0 - doc.get("distance", 1.0),
    }
    for doc in retrieved_docs
]
yield f"data: {json.dumps({'type': 'retrieval_done', 'count': len(retrieved_docs), 'latency_ms': ..., 'results': results_data})}\n\n"

# 4. 后续 token 流不变
```

### 检索耗时计算

在 `chat_stream` 中用 `time.perf_counter()` 记录检索前后时间差。

## 前端改动

### `src/types/index.ts` — 新增类型

```typescript
interface RetrievalResult {
  content: string;
  metadata: Record<string, any>;
  score: number;
}

// Message 类型扩展
interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceDoc[];
  retrieval?: {              // 新增
    count: number;
    latencyMs: number;
    results: RetrievalResult[];
  };
  timestamp: number;
}
```

### `src/api/client.ts` — 新增 SSE 事件处理

在 `sendMessageStream` 中处理新增的 `retrieval_start` 和 `retrieval_done` 事件：

```typescript
interface StreamCallbacks {
  onRetrievalStart?: () => void;                          // 新增
  onRetrievalDone?: (data: RetrievalDoneData) => void;    // 新增
  onToken: (token: string) => void;
  onDone: (answer: string, sources: SourceDoc[]) => void;
  onError: (error: Error) => void;
}
```

### `src/hooks/useChat.ts` — 处理检索回调

- `onRetrievalStart`: 创建 assistant bubble（如果还没有）并附带 `retrieval: { phase: 'searching' }`
- `onRetrievalDone`: 更新 bubble 的 `retrieval` 字段为完整数据
- 其余不变

### 新增组件：`RetrievalCard.tsx`

展示检索结果卡片，两种状态：

1. **Searching 状态**: 蓝点脉冲动画 + "正在检索知识库..."
2. **Done 状态**: 检索完成 + 片段数 + 耗时 + 片段列表（截断 2 行）

放在 `MessageBubble` 内部，assistant bubble 的上方。

### `src/components/MessageBubble.tsx` — 集成检索卡片

```tsx
{message.retrieval && (
  <RetrievalCard retrieval={message.retrieval} />
)}
{/* 现有 bubble 和 sources 不变 */}
```

### `src/components/RetrievalCard.tsx` — 检索卡片

- 卡片容器：`border: 1px solid #ebebeb; border-radius: 12px; background: #fafafa`
- 头部：搜索 SVG 图标 + "检索完成" + 右侧 `N 个片段 · X.Xs` 徽标
- 列表：每行 `[序号]` 标签 + 文本（最多 2 行截断）
- 回答完成后可折叠（与现有 SourceCitation 互补，检索卡片是概览，SourceCitation 是详情）

### 样式更新

- 新增 CSS 变量（matching 原型色调）：`--color-surface`, `--color-border-light`, `--color-text-tertiary`
- 新增 `.retrieval-card` 全套 BEM 样式
- 新增 `.generating-indicator` 样式（替代旧的 typing-indicator）

## 不做的事情

- 不修改非流式 `/api/chat` 端点（保持兼容，只改 SSE 流）
- 不删除现有 `SourceCitation` 组件（检索卡片 + 来源引用互补）
- 不改变 `Retriever` 或 Pipeline 核心逻辑

## 风险

| 风险 | 缓解 |
|------|------|
| 检索结果过多导致卡片过高 | 列表 max-height 180px + overflow-y scroll |
| SSE 事件乱序 | 后端保证 `retrieval_done` 在第一个 token 之前发送 |
| 旧版前端收到新事件 | 新事件 type 字段，旧前端忽略未知 type（安全降级） |
