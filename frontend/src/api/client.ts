import type { ChatRequest, ChatResponse, DocumentInfo, SourceDoc, UploadResponse } from '../types'

const API_BASE = '/api'

async function sendMessage(request: ChatRequest): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

/** Callbacks for streaming RAG chat. */
interface StreamCallbacks {
  /** A new token has arrived. */
  onToken: (token: string) => void
  /** Stream completed with accumulated answer and sources. */
  onDone: (answer: string, sources: SourceDoc[]) => void
  /** A fatal error occurred during streaming. */
  onError: (error: Error) => void
}

/**
 * Send a RAG query and consume the SSE stream.
 *
 * Tokens are yielded via `onToken` as they arrive; `onDone` fires once
 * `[DONE]` is received.  Pass an `AbortController` signal to cancel
 * mid-stream.  The Vite proxy is configured with `selfHandleResponse` to
 * prevent buffering of SSE responses.
 */
async function sendMessageStream(
  request: ChatRequest,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    signal,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Stream request failed' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('ReadableStream not supported')
  }

  const decoder = new TextDecoder()
  let buffer = ''
  let fullAnswer = ''
  let sources: SourceDoc[] = []

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed || !trimmed.startsWith('data: ')) continue

        const data = trimmed.slice(6)

        if (data === '[DONE]') {
          callbacks.onDone(fullAnswer, sources)
          return
        }

        try {
          const parsed = JSON.parse(data)
          if (parsed.token) {
            fullAnswer += parsed.token
            callbacks.onToken(parsed.token)
          } else if (parsed.sources) {
            sources = parsed.sources
          } else if (parsed.error) {
            callbacks.onError(new Error(parsed.error))
            return
          }
        } catch {
          // Skip unparseable lines
        }
      }

      // Natural pacing: reader.read() blocks until new SSE data arrives
      // over the network (~50ms between Ollama tokens).  Each read naturally
      // yields 1–2 tokens, React batches them, and the next read waits.
    }

    // Stream ended without explicit [DONE]
    callbacks.onDone(fullAnswer, sources)
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      return
    }
    callbacks.onError(err instanceof Error ? err : new Error(String(err)))
  } finally {
    try { reader.releaseLock() } catch { /* already released */ }
  }
}

async function uploadFile(file: File): Promise<UploadResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${API_BASE}/upload`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Upload failed' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

async function healthCheck(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/health`)
    return response.ok
  } catch {
    return false
  }
}

async function fetchDocuments(): Promise<DocumentInfo[]> {
  const response = await fetch(`${API_BASE}/documents`)

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Failed to fetch documents' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

export { API_BASE, fetchDocuments, sendMessage, sendMessageStream, uploadFile, healthCheck }
export type { StreamCallbacks }
