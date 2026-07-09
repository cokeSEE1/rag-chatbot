import { useState, useCallback, useRef } from 'react'
import type { Message } from '../types'
import { sendMessage as apiSendMessage } from '../api/client'

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const historyRef = useRef<{ role: string; content: string }[]>([])

  const sendMessage = useCallback(async (query: string) => {
    if (!query.trim()) return

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: query.trim(),
      timestamp: Date.now(),
    }

    setMessages(prev => [...prev, userMessage])
    setIsLoading(true)
    setError(null)

    try {
      const response = await apiSendMessage({
        query: query.trim(),
        history: historyRef.current,
      })

      const assistantMessage: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: response.answer,
        sources: response.sources,
        timestamp: Date.now(),
      }

      // Update conversation history for the backend
      historyRef.current.push(
        { role: 'user', content: query.trim() },
        { role: 'assistant', content: response.answer }
      )

      // Keep only the last 20 turns to avoid context overflow
      if (historyRef.current.length > 40) {
        historyRef.current = historyRef.current.slice(-40)
      }

      setMessages(prev => [...prev, assistantMessage])
    } catch (err) {
      const message = err instanceof Error ? err.message : '发送消息失败，请重试'
      setError(message)
    } finally {
      setIsLoading(false)
    }
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([])
    historyRef.current = []
    setError(null)
  }, [])

  return { messages, isLoading, error, sendMessage, clearMessages, setError }
}
