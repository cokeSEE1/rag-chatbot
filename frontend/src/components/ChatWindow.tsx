import { useEffect, useRef, type ReactNode } from 'react'
import type { Message } from '../types'
import MessageBubble from './MessageBubble'
import ChatInput from './ChatInput'
import EmptyState from './EmptyState'

interface ChatWindowProps {
  messages: Message[]
  isLoading: boolean
  onSend: (message: string) => void
  headerRight?: ReactNode
}

export default function ChatWindow({ messages, isLoading, onSend, headerRight }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom when messages change or loading state changes
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  return (
    <div className="chat-window">
      <div className="chat-window__header">
        <h2>RAG 智能问答</h2>
        {headerRight && <div className="chat-window__header-right">{headerRight}</div>}
      </div>

      <div className="chat-window__messages">
        {messages.length === 0 && !isLoading ? (
          <EmptyState />
        ) : (
          messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))
        )}

        {/* Only show typing indicator while waiting for the first token.
             Once the assistant starts responding, the streaming bubble itself
             provides the "in progress" visual. */}
        {isLoading && messages[messages.length - 1]?.role !== 'assistant' && (
          <div className="message-row message-row--assistant">
            <div className="message-bubble message-bubble--assistant">
              <div className="typing-indicator">
                <span className="typing-indicator__dot" />
                <span className="typing-indicator__dot" />
                <span className="typing-indicator__dot" />
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="chat-window__input">
        <ChatInput onSend={onSend} disabled={isLoading} />
      </div>
    </div>
  )
}
