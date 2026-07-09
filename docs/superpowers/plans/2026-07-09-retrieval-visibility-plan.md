# 检索过程可视化 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 RAG 问答流式输出时，前端实时展示检索过程（召回数量、内容、耗时）

**Architecture:** 后端 SSE 流在 token 之前新增 `retrieval_start` 和 `retrieval_done` 事件；前端 `sendMessageStream` 解析新事件并通过回调传递给 `useChat` hook，hook 更新 Message 的 `retrieval` 字段，新增 `RetrievalCard` 组件渲染检索卡片

**Tech Stack:** FastAPI + Python 3.13 / React 18 + TypeScript 5.6 + Vite 6 / 纯 CSS

**Spec:** `docs/superpowers/specs/2026-07-09-retrieval-visibility-design.md`

---

## 文件分工

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/app/models/schemas.py` | 修改 | 新增 `RetrievalResult` Pydantic 模型 |
| `backend/app/api/chat.py` | 修改 | SSE 流新增 `retrieval_start`/`retrieval_done` 事件 + 耗时 |
| `frontend/src/types/index.ts` | 修改 | 新增 `RetrievalResult` 类型，`Message` 扩展 `retrieval` 字段 |
| `frontend/src/api/client.ts` | 修改 | `StreamCallbacks` 新增检索回调，SSE 解析新增 `retrieval_*` 事件 |
| `frontend/src/hooks/useChat.ts` | 修改 | 处理检索回调，更新 message 的 `retrieval` 状态 |
| `frontend/src/components/RetrievalCard.tsx` | **新建** | 检索结果卡片组件（searching / done 两种状态） |
| `frontend/src/components/MessageBubble.tsx` | 修改 | 集成 `RetrievalCard`，在 assistant bubble 上方渲染 |
| `frontend/src/App.css` | 修改 | 新增检索卡片 + generating 指示器全套样式 |

---

### Task 1: 后端 — 新增 RetrievalResult 模型

**Files:**
- Modify: `backend/app/models/schemas.py`

- [ ] **Step 1: 添加 RetrievalResult 模型**

在 `SourceDoc` 定义之后（第 16 行之后），添加：

```python
class RetrievalResult(BaseModel):
    """A single result returned by the retrieval step."""

    content: str = Field(..., description="Retrieved chunk text")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata (filename, etc.)"
    )
    score: float = Field(..., description="Relevance / similarity score (0-1)")
```

- [ ] **Step 2: 验证后端可以正常导入**

```bash
cd /Users/lanzhang/Desktop/rag-chatbot/backend
python -c "from app.models.schemas import RetrievalResult; print('OK')"
```

期望输出: `OK`

- [ ] **Step 3: Commit**

```bash
cd /Users/lanzhang/Desktop/rag-chatbot
git add backend/app/models/schemas.py
git commit -m "feat: add RetrievalResult model for retrieval visibility"
```

---

### Task 2: 后端 — SSE 流新增检索事件

**Files:**
- Modify: `backend/app/api/chat.py`

- [ ] **Step 1: 修改 `chat_stream` 函数**

在 `chat_stream` 的 `event_generator` 内，检索步骤前后添加事件。

当前代码（`chat.py:78-89`）：
```python
            # 1. Retrieve
            retrieved_docs = retriever.retrieve(request.query)

            context_parts: list[str] = []
            for doc in retrieved_docs:
                context_parts.append(doc.get("text", ""))

            context = (
                "\n\n---\n\n".join(context_parts)
                if context_parts
                else "暂无相关参考资料。"
            )
```

替换为：
```python
            import time

            # 1. Signal retrieval start
            yield f"data: {json.dumps({'type': 'retrieval_start'})}\n\n"
            await asyncio.sleep(0)

            # 2. Retrieve
            t0 = time.perf_counter()
            retrieved_docs = retriever.retrieve(request.query)
            latency_ms = round((time.perf_counter() - t0) * 1000)

            # 3. Signal retrieval done with results
            results_data = [
                {
                    "content": doc.get("text", ""),
                    "metadata": doc.get("metadata", {}),
                    "score": 1.0 - doc.get("distance", 1.0),
                }
                for doc in retrieved_docs
            ]
            yield f"data: {json.dumps({'type': 'retrieval_done', 'count': len(retrieved_docs), 'latency_ms': latency_ms, 'results': results_data})}\n\n"
            await asyncio.sleep(0)

            # 4. Build context for the LLM
            context_parts: list[str] = []
            for doc in retrieved_docs:
                context_parts.append(doc.get("text", ""))

            context = (
                "\n\n---\n\n".join(context_parts)
                if context_parts
                else "暂无相关参考资料。"
            )
```

> 注意：`import time` 应放在文件顶部（`chat.py` 已有 `import time` 吗？检查后决定是否需要添加）。

检查 `chat.py` 顶部 imports，当前有 `import asyncio, json, logging`。需要确认 `import time` 是否存在。

- [ ] **Step 2: 检查 top-level imports**

在 `chat.py` 顶部，检查 `import time` 是否已存在。如果不存在，在第 6 行 (`import logging` 后) 添加：

```python
import time
```

- [ ] **Step 3: 测试后端 SSE 流新事件**

```bash
curl -s -N -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "什么是RAG"}' | head -20
```

期望输出前几行包含：
```
data: {"type":"retrieval_start"}
data: {"type":"retrieval_done","count":...,"latency_ms":...,"results":[...]}
```

- [ ] **Step 4: Commit**

```bash
cd /Users/lanzhang/Desktop/rag-chatbot
git add backend/app/api/chat.py
git commit -m "feat: add retrieval_start and retrieval_done SSE events"
```

---

### Task 3: 前端 — 扩展类型定义

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: 添加 RetrievalResult 接口和扩展 Message**

在 `frontend/src/types/index.ts` 中：

在 `SourceDoc` 接口之后添加：

```typescript
export interface RetrievalResult {
  content: string;
  metadata: Record<string, any>;
  score: number;
}

export interface RetrievalInfo {
  count: number;
  latencyMs: number;
  results: RetrievalResult[];
}
```

修改 `Message` 接口，添加 `retrieval` 可选字段：

```typescript
export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceDoc[];
  retrieval?: RetrievalInfo;
  timestamp: number;
}
```

- [ ] **Step 2: 类型检查**

```bash
cd /Users/lanzhang/Desktop/rag-chatbot/frontend
npx tsc --noEmit 2>&1 | head -20
```

期望：无新增类型错误（可能有既存错误，忽略）。

- [ ] **Step 3: Commit**

```bash
cd /Users/lanzhang/Desktop/rag-chatbot
git add frontend/src/types/index.ts
git commit -m "feat: add RetrievalResult, RetrievalInfo types and extend Message"
```

---

### Task 4: 前端 — SSE 客户端处理检索事件

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: 扩展 StreamCallbacks 接口**

修改 `StreamCallbacks` 接口（`client.ts:23-30`），添加两个可选回调：

```typescript
/** Callbacks for streaming RAG chat. */
interface StreamCallbacks {
  /** Retrieval phase has started. */
  onRetrievalStart?: () => void
  /** Retrieval phase completed with results. */
  onRetrievalDone?: (data: { count: number; latency_ms: number; results: import('../types').RetrievalResult[] }) => void
  /** A new token has arrived. */
  onToken: (token: string) => void
  /** Stream completed with accumulated answer and sources. */
  onDone: (answer: string, sources: SourceDoc[]) => void
  /** A fatal error occurred during streaming. */
  onError: (error: Error) => void
}
```

- [ ] **Step 2: 在 SSE 解析循环中处理新事件**

修改 `sendMessageStream` 函数中解析 JSON data 的代码块（`client.ts:87-97`），在 `if (parsed.token)` 之前添加：

```typescript
          try {
            const parsed = JSON.parse(data)
            if (parsed.type === 'retrieval_start') {
              callbacks.onRetrievalStart?.()
            } else if (parsed.type === 'retrieval_done') {
              callbacks.onRetrievalDone?.({
                count: parsed.count,
                latency_ms: parsed.latency_ms,
                results: parsed.results,
              })
            } else if (parsed.token) {
              fullAnswer += parsed.token
              callbacks.onToken(parsed.token)
            } else if (parsed.sources) {
              sources = parsed.sources
            } else if (parsed.error) {
              callbacks.onError(new Error(parsed.error))
              return
            }
          } catch {
```

- [ ] **Step 3: 类型检查**

```bash
cd /Users/lanzhang/Desktop/rag-chatbot/frontend
npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 4: Commit**

```bash
cd /Users/lanzhang/Desktop/rag-chatbot
git add frontend/src/api/client.ts
git commit -m "feat: add retrieval callbacks to SSE stream client"
```

---

### Task 5: 前端 — useChat hook 处理检索回调

**Files:**
- Modify: `frontend/src/hooks/useChat.ts`

- [ ] **Step 1: 在 sendMessage 中添加检索回调**

在 `sendMessageStream` 调用时（`useChat.ts:41` 行附近），在 `onToken` 之前插入 `onRetrievalStart` 和 `onRetrievalDone`：

```typescript
      await sendMessageStream(
        { query: query.trim(), history: historyRef.current },
        {
          onRetrievalStart() {
            // Create the assistant bubble early so the user sees retrieval card first
            if (!bubbleCreated) {
              setMessages(prev => [
                ...prev,
                {
                  id: assistantId,
                  role: 'assistant' as const,
                  content: '',
                  retrieval: { count: 0, latencyMs: 0, results: [] },
                  timestamp: Date.now(),
                },
              ])
              bubbleCreated = true
            }
          },
          onRetrievalDone(data) {
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId
                  ? {
                      ...m,
                      retrieval: {
                        count: data.count,
                        latencyMs: data.latency_ms,
                        results: data.results,
                      },
                    }
                  : m,
              ),
            )
          },
          onToken(_token) {
            // ... existing code unchanged
```

- [ ] **Step 2: 类型检查**

```bash
cd /Users/lanzhang/Desktop/rag-chatbot/frontend
npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 3: Commit**

```bash
cd /Users/lanzhang/Desktop/rag-chatbot
git add frontend/src/hooks/useChat.ts
git commit -m "feat: handle retrieval callbacks in useChat hook"
```

---

### Task 6: 前端 — 创建 RetrievalCard 组件

**Files:**
- Create: `frontend/src/components/RetrievalCard.tsx`

- [ ] **Step 1: 创建组件文件**

```tsx
import type { RetrievalInfo } from '../types'

interface RetrievalCardProps {
  retrieval: RetrievalInfo
}

export default function RetrievalCard({ retrieval }: RetrievalCardProps) {
  const isSearching = retrieval.count === 0 && retrieval.results.length === 0

  if (isSearching) {
    return (
      <div className="retrieval-card retrieval-card--searching">
        <div className="retrieval-card__head">
          <span className="retrieval-card__pulse" />
          <span className="retrieval-card__label">正在检索知识库...</span>
        </div>
      </div>
    )
  }

  const latencySec = (retrieval.latencyMs / 1000).toFixed(1)

  return (
    <div className="retrieval-card">
      <div className="retrieval-card__head">
        <svg
          className="retrieval-card__icon"
          width="15" height="15"
          viewBox="0 0 24 24"
          fill="none" stroke="currentColor"
          strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="m16.5 16.5 4 4" />
        </svg>
        <span className="retrieval-card__label">检索完成</span>
        <span className="retrieval-card__meta">
          {retrieval.count} 个片段 · {latencySec}s
        </span>
      </div>
      <div className="retrieval-card__list">
        {retrieval.results.map((result, i) => (
          <div key={i} className="retrieval-card__item">
            <span className="retrieval-card__rank">{i + 1}</span>
            <span className="retrieval-card__text">{result.content}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: 类型检查**

```bash
cd /Users/lanzhang/Desktop/rag-chatbot/frontend
npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 3: Commit**

```bash
cd /Users/lanzhang/Desktop/rag-chatbot
git add frontend/src/components/RetrievalCard.tsx
git commit -m "feat: add RetrievalCard component"
```

---

### Task 7: 前端 — MessageBubble 集成 RetrievalCard

**Files:**
- Modify: `frontend/src/components/MessageBubble.tsx`

- [ ] **Step 1: 导入 RetrievalCard 并在 assistant bubble 上方渲染**

修改 `MessageBubble.tsx`：

在顶部 import 区添加：
```tsx
import RetrievalCard from './RetrievalCard'
```

在组件返回的 JSX 中，assistant 分支内，在 `<div className="markdown-body">` 之前添加检索卡片：

当前代码（`MessageBubble.tsx:18-20`）：
```tsx
          <div className="markdown-body">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
```

改为：
```tsx
          {message.retrieval && message.retrieval.results.length > 0 && (
            <RetrievalCard retrieval={message.retrieval} />
          )}
          {message.retrieval && message.retrieval.results.length === 0 && message.retrieval.count === 0 && (
            <RetrievalCard retrieval={message.retrieval} />
          )}
          {message.content && (
            <div className="markdown-body">
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          )}
```

> 注：第一个条件渲染 done 状态的检索卡片（有结果），第二个渲染 searching 状态（count=0 且 results=[]），第三个条件渲染确保空 content 时不显示空的 markdown body。

简化写法：
```tsx
          {message.retrieval && (
            <RetrievalCard retrieval={message.retrieval} />
          )}
          {message.content && (
            <div className="markdown-body">
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          )}
```

RetrievalCard 内部自行判断 searching vs done 状态，MessageBubble 只需传入 retrieval 对象。

- [ ] **Step 2: 类型检查**

```bash
cd /Users/lanzhang/Desktop/rag-chatbot/frontend
npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 3: Commit**

```bash
cd /Users/lanzhang/Desktop/rag-chatbot
git add frontend/src/components/MessageBubble.tsx
git commit -m "feat: integrate RetrievalCard into MessageBubble"
```

---

### Task 8: 前端 — 添加样式

**Files:**
- Modify: `frontend/src/App.css`

- [ ] **Step 1: 在 App.css 末尾（`@media` 块之前）添加检索卡片样式**

```css
/* ============================================
   Retrieval Card
   ============================================ */
.retrieval-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--color-bg-secondary);
  font-size: 12px;
  animation: fadeIn 0.25s ease;
}

.retrieval-card__head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--color-border);
}

.retrieval-card__icon {
  color: var(--color-text);
  flex-shrink: 0;
}

.retrieval-card__pulse {
  width: 8px;
  height: 8px;
  background: var(--color-primary);
  border-radius: 50%;
  animation: retrievalPulse 1.2s ease-in-out infinite;
  flex-shrink: 0;
}

@keyframes retrievalPulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%      { opacity: 0.4; transform: scale(1.3); }
}

.retrieval-card__label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--color-text);
  flex: 1;
}

.retrieval-card__meta {
  font-size: 10.5px;
  font-weight: 500;
  color: var(--color-text-muted);
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  padding: 3px 9px;
  border-radius: 20px;
  white-space: nowrap;
}

.retrieval-card__list {
  padding: 4px 14px 8px;
  max-height: 180px;
  overflow-y: auto;
}

.retrieval-card__item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 7px 0;
  border-bottom: 1px solid var(--color-border);
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-secondary);
}

.retrieval-card__item:last-child {
  border-bottom: none;
}

.retrieval-card__rank {
  font-size: 10.5px;
  font-weight: 600;
  color: var(--color-text);
  background: var(--color-bg-tertiary);
  padding: 2px 7px;
  border-radius: 4px;
  flex-shrink: 0;
}

.retrieval-card__text {
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

/* Searching state */
.retrieval-card--searching {
  border-color: var(--color-primary-light);
  background: var(--color-primary-light);
}

.retrieval-card--searching .retrieval-card__head {
  border-bottom: none;
}

.retrieval-card--searching .retrieval-card__label {
  color: var(--color-primary);
}

/* ============================================
   Generating Indicator
   ============================================ */
.generating-indicator {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 20px;
  font-size: 11.5px;
  font-weight: 500;
  color: var(--color-text-muted);
  width: fit-content;
}

.generating-indicator__dots {
  display: flex;
  gap: 3px;
}

.generating-indicator__dots span {
  width: 4px;
  height: 4px;
  background: var(--color-text-muted);
  border-radius: 50%;
  animation: generatingBounce 1.4s ease-in-out infinite;
}

.generating-indicator__dots span:nth-child(2) {
  animation-delay: 0.16s;
}

.generating-indicator__dots span:nth-child(3) {
  animation-delay: 0.32s;
}

@keyframes generatingBounce {
  0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1); }
}
```

- [ ] **Step 2: 验证 CSS 无语法错误**

用浏览器 DevTools 或直接检查。

- [ ] **Step 3: Commit**

```bash
cd /Users/lanzhang/Desktop/rag-chatbot
git add frontend/src/App.css
git commit -m "feat: add retrieval card and generating indicator styles"
```

---

### Task 9: 前端 — 更新 CSS 变量（适配新风格）

**Files:**
- Modify: `frontend/src/App.css`

- [ ] **Step 1: 更新 `:root` CSS 变量**

将当前的蓝色主题变量更新为新风格的黑白灰主题。当前 `:root` 块（`App.css:3-33`）替换为：

```css
:root {
  --color-primary: #18181b;
  --color-primary-hover: #27272a;
  --color-primary-light: #f0f0f0;
  --color-bg: #ffffff;
  --color-bg-secondary: #fafafa;
  --color-bg-tertiary: #f5f5f5;
  --color-sidebar: #fafafa;
  --color-border: #ebebeb;
  --color-text: #18181b;
  --color-text-secondary: #525252;
  --color-text-muted: #999999;
  --color-user-bubble: #18181b;
  --color-user-text: #ffffff;
  --color-assistant-bubble: #f5f5f5;
  --color-assistant-text: #3d3d3d;
  --color-error: #dc2626;
  --color-error-bg: #fef2f2;
  --color-success: #22c55e;
  --color-success-bg: #f0fdf4;
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.03);
  --shadow-md: 0 2px 4px rgba(0, 0, 0, 0.04);
  --shadow-lg: 0 4px 8px rgba(0, 0, 0, 0.06);
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 14px;
  --sidebar-width: 300px;
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --font-mono: 'SF Mono', 'Fira Code', 'Fira Mono', 'Roboto Mono', monospace;
}
```

- [ ] **Step 2: 在 `index.html` 中引入 Inter 字体**

修改 `frontend/index.html`，在 `<head>` 内添加：

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
```

- [ ] **Step 3: 验证前端正常**

```bash
cd /Users/lanzhang/Desktop/rag-chatbot/frontend
npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 4: Commit**

```bash
cd /Users/lanzhang/Desktop/rag-chatbot
git add frontend/src/App.css frontend/index.html
git commit -m "style: update theme to monochrome palette with Inter font"
```

---

### Task 10: 端到端验证

- [ ] **Step 1: 确认后端健康**

```bash
curl -s http://localhost:8000/api/health
```

- [ ] **Step 2: 测试 SSE 流包含检索事件**

```bash
curl -s -N -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "什么是RAG"}' 2>&1 | head -30
```

期望看到 `retrieval_start` 和 `retrieval_done` 事件。

- [ ] **Step 3: 打开前端验证 UI**

浏览器打开 `http://localhost:5173`，发送问题，确认：
- 检索卡片在回答前出现
- 显示片段数量和耗时
- 片段列表可滚动
- 回答正常流式输出
- 来源引用正常工作

- [ ] **Step 4: 最终 Commit**

```bash
cd /Users/lanzhang/Desktop/rag-chatbot
git add -A
git commit -m "feat: complete retrieval visibility feature

- Backend: retrieval_start / retrieval_done SSE events with latency
- Frontend: RetrievalCard component with searching/done states
- Frontend: updated theme to monochrome palette with Inter font
- Frontend: Message type extended with RetrievalInfo"
```
