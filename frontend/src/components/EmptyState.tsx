export default function EmptyState() {
  return (
    <div className="empty-state">
      <div className="empty-state__icon">
        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          <line x1="9" y1="10" x2="15" y2="10" />
          <line x1="12" y1="7" x2="12" y2="13" />
        </svg>
      </div>
      <h2 className="empty-state__title">欢迎使用 RAG 智能问答</h2>
      <p className="empty-state__desc">
        上传文档后，即可基于文档内容进行智能问答。
        <br />
        支持 .txt、.md、.pdf、.docx 格式文件。
      </p>
    </div>
  )
}
