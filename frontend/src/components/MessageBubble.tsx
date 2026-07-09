import ReactMarkdown from 'react-markdown'
import type { Message } from '../types'
import SourceCitation from './SourceCitation'

interface MessageBubbleProps {
  message: Message
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'

  return (
    <div className={`message-row ${isUser ? 'message-row--user' : 'message-row--assistant'}`}>
      <div className={`message-bubble ${isUser ? 'message-bubble--user' : 'message-bubble--assistant'}`}>
        {isUser ? (
          <p className="message-text">{message.content}</p>
        ) : (
          <div className="markdown-body">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        )}
      </div>
      {message.sources && message.sources.length > 0 && (
        <div className="message-sources">
          {message.sources.map((source, index) => (
            <SourceCitation key={index} source={source} index={index} />
          ))}
        </div>
      )}
    </div>
  )
}
