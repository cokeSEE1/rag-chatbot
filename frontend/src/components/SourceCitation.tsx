import { useState } from 'react'
import type { SourceDoc } from '../types'

interface SourceCitationProps {
  source: SourceDoc
  index: number
}

export default function SourceCitation({ source, index }: SourceCitationProps) {
  const [expanded, setExpanded] = useState(false)
  const filename = source.metadata?.filename || source.metadata?.source || '未知文档'
  const scorePercent = Math.round(source.score * 100)

  return (
    <div className={`citation ${expanded ? 'citation--expanded' : ''}`}>
      <button
        className="citation__header"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        <span className="citation__index">#{index + 1}</span>
        <span className="citation__file">{filename}</span>
        <span className="citation__score" title={`相关性: ${scorePercent}%`}>
          {scorePercent}%
        </span>
        <span className={`citation__arrow ${expanded ? 'citation__arrow--open' : ''}`}>
          &#9662;
        </span>
      </button>
      {expanded && (
        <div className="citation__body">
          <div className="citation__content">{source.content}</div>
          {Object.keys(source.metadata).length > 0 && (
            <div className="citation__metadata">
              {Object.entries(source.metadata).map(([key, value]) => (
                <span key={key} className="citation__meta-item">
                  <strong>{key}:</strong> {String(value)}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
