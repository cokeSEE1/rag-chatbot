# Frontend Streaming Output Design

**Date**: 2026-07-09 | **Status**: approved

## Overview

Backend `POST /api/chat/stream` (SSE) is already implemented. Frontend currently uses `POST /api/chat` (non-streaming). This design adds streaming consumption with RAF-based batching to limit react-markdown re-parses to ~16/s instead of 1/token.

## Files Changed

| File | Change |
|------|--------|
| `src/api/client.ts` | Add `sendMessageStream()` using `fetch` + `ReadableStream` |
| `src/hooks/useChat.ts` | Add streaming path with `bufferRef` + `requestAnimationFrame` batching |
| `src/types/index.ts` | Add `StreamChatCallbacks` type (optional, could inline) |

## Data Flow

```
sendMessageStream(query, history, onToken, onDone, onError)
  → fetch POST /api/chat/stream
    → ReadableStream reader
      → parse SSE lines: data: {"token":"..."} | {"sources":[...]} | [DONE]
        → onToken(token) → hook accumulates in bufferRef
        → RAF flushes buffer to state (~16 fps max)
        → onDone(sources, fullText) → finalize message, update historyRef
        → onError(err) → setError
```

## RAF Batching

```
bufferRef: accumulated text since last flush
rafId: pending RAF handle (null if none)

onToken:
  bufferRef += token
  if !rafId: rafId = rAF(() => { update last assistant msg; rafId = null })
```

## Error Handling

- Network error → onError → setError + remove partial message
- SSE error event → onError
- AbortController → user can cancel mid-stream

## Edge Cases

- Stale response: abort previous stream when new message sent before old finishes
- Empty response: show "暂无相关答案"
- Disconnect: error toast + partial content preserved
