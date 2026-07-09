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
