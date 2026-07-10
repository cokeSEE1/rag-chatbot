import { useState, useCallback, useRef } from 'react'
import type { Message } from '../types'
import { sendMessageStream } from '../api/client'

const MAX_HISTORY = 40 // 20 Q&A turns

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const historyRef = useRef<{ role: string; content: string }[]>([])
  const abortRef = useRef<AbortController | null>(null)

  const sendMessage = useCallback(async (query: string, provider?: string, model?: string) => {
    if (!query.trim()) return

    // Abort any in-flight stream before starting a new one
    abortRef.current?.abort()

    const controller = new AbortController()
    abortRef.current = controller

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: query.trim(),
      timestamp: Date.now(),
    }

    // Only add the user message — the assistant bubble is created lazily
    // when the first token arrives so the user sees a typing indicator
    // during the thinking phase, not an empty bubble.
    setMessages(prev => [...prev, userMessage])
    setIsLoading(true)
    setError(null)

    const assistantId = crypto.randomUUID()
    let bubbleCreated = false

    try {
      await sendMessageStream(
        { query: query.trim(), history: historyRef.current, provider, model },
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
            if (!bubbleCreated) {
              // First token — create the assistant bubble
              setMessages(prev => [
                ...prev,
                {
                  id: assistantId,
                  role: 'assistant' as const,
                  content: _token,
                  timestamp: Date.now(),
                },
              ])
              bubbleCreated = true
            } else {
              setMessages(prev =>
                prev.map(m =>
                  m.id === assistantId
                    ? { ...m, content: m.content + _token }
                    : m,
                ),
              )
            }
          },
          onDone(answer, sources) {
            setMessages(prev =>
              prev.map(m =>
                m.id === assistantId ? { ...m, content: answer, sources } : m,
              ),
            )

            historyRef.current.push(
              { role: 'user', content: query.trim() },
              { role: 'assistant', content: answer },
            )
            if (historyRef.current.length > MAX_HISTORY) {
              historyRef.current = historyRef.current.slice(-MAX_HISTORY)
            }

            setIsLoading(false)
          },
          onError(err) {
            setMessages(prev => prev.filter(m => m.id !== assistantId))
            setError(err.message)
            setIsLoading(false)
          },
        },
        controller.signal,
      )
    } catch (err) {
      if (bubbleCreated) {
        setMessages(prev => prev.filter(m => m.id !== assistantId))
      }
      const message = err instanceof Error ? err.message : '发送消息失败，请重试'
      setError(message)
      setIsLoading(false)
    }
  }, [])

  const clearMessages = useCallback(() => {
    abortRef.current?.abort()
    setMessages([])
    historyRef.current = []
    setError(null)
  }, [])

  return { messages, isLoading, error, sendMessage, clearMessages, setError }
}
