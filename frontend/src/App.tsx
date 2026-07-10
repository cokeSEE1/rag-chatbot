import { useState, useCallback, useEffect } from 'react'
import { useChat } from './hooks/useChat'
import ChatWindow from './components/ChatWindow'
import DocumentUpload from './components/DocumentUpload'
import ModelSwitcher from './components/ModelSwitcher'
import { fetchDocuments } from './api/client'
import type { DocumentInfo } from './types'
import type { ModelOption } from './components/ModelSwitcher'

const MODEL_OPTIONS: ModelOption[] = [
  { name: 'deepseek-r1:7b', provider: 'ollama', label: '本地', desc: '4.7GB' },
  { name: 'qwen2.5:7b', provider: 'ollama', label: '本地', desc: '4.4GB' },
  { name: 'deepseek-v4-flash', provider: 'anthropic', label: '远程', desc: 'packyapi' },
  { name: 'claude-sonnet-5', provider: 'anthropic', label: '远程', desc: 'Anthropic' },
]

export default function App() {
  const { messages, isLoading, error, sendMessage, clearMessages, setError } = useChat()
  const [documents, setDocuments] = useState<DocumentInfo[]>([])
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [selectedModel, setSelectedModel] = useState<ModelOption>(MODEL_OPTIONS[0])

  // Load existing documents on mount
  useEffect(() => {
    fetchDocuments()
      .then(setDocuments)
      .catch(() => {
        // Silently fail — the list can be refreshed by uploading a new document
      })
  }, [])

  const handleUploadSuccess = useCallback((doc: DocumentInfo) => {
    setDocuments(prev => {
      const filtered = prev.filter(d => d.file_id !== doc.file_id)
      return [doc, ...filtered]
    })
  }, [])

  const handleSend = useCallback((query: string) => {
    sendMessage(query, selectedModel.provider, selectedModel.name)
  }, [sendMessage, selectedModel])

  return (
    <div className="app">
      {/* Mobile sidebar toggle */}
      <button
        className="sidebar-toggle"
        onClick={() => setSidebarOpen(!sidebarOpen)}
        aria-label={sidebarOpen ? '关闭侧边栏' : '打开侧边栏'}
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          {sidebarOpen ? (
            <line x1="18" y1="6" x2="6" y2="18" />
          ) : (
            <>
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </>
          )}
        </svg>
      </button>

      {/* Overlay for mobile sidebar */}
      {sidebarOpen && (
        <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Sidebar */}
      <aside className={`sidebar ${sidebarOpen ? 'sidebar--open' : ''}`}>
        <div className="sidebar__header">
          <h1 className="sidebar__logo">RAG Chat</h1>
        </div>

        <DocumentUpload onUploadSuccess={handleUploadSuccess} />

        <div className="sidebar__documents">
          <h3 className="sidebar__section-title">
            已上传文档 ({documents.length})
          </h3>
          {documents.length === 0 ? (
            <p className="sidebar__empty">暂无文档</p>
          ) : (
            <ul className="sidebar__doc-list">
              {documents.map((doc) => (
                <li key={doc.file_id} className="sidebar__doc-item">
                  <span className="sidebar__doc-icon">&#128196;</span>
                  <div className="sidebar__doc-info">
                    <span className="sidebar__doc-name">{doc.filename}</span>
                    <span className="sidebar__doc-meta">
                      {doc.chunks_count} 个片段 &middot; {doc.status}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="sidebar__footer">
          <button className="sidebar__clear-btn" onClick={clearMessages}>
            清空对话
          </button>
        </div>
      </aside>

      {/* Main chat area */}
      <main className="main">
        {error && (
          <div className="toast toast--error">
            <span>{error}</span>
            <button className="toast__close" onClick={() => setError(null)}>
              &times;
            </button>
          </div>
        )}
        <ChatWindow
          messages={messages}
          isLoading={isLoading}
          onSend={handleSend}
          headerRight={
            <ModelSwitcher
              options={MODEL_OPTIONS}
              selected={selectedModel}
              onChange={setSelectedModel}
            />
          }
        />
      </main>
    </div>
  )
}
