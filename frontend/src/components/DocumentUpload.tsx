import { useState, useRef, useCallback, type DragEvent } from 'react'
import { uploadFile } from '../api/client'
import type { UploadResponse } from '../types'

interface DocumentUploadProps {
  onUploadSuccess: (doc: UploadResponse) => void
}

const ALLOWED_TYPES = [
  'text/plain',
  'text/markdown',
  'text/x-markdown',
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
]

const ALLOWED_EXTENSIONS = ['.txt', '.md', '.pdf', '.docx']

export default function DocumentUpload({ onUploadSuccess }: DocumentUploadProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const validateFile = (file: File): string | null => {
    const ext = '.' + file.name.split('.').pop()?.toLowerCase()
    if (!ALLOWED_EXTENSIONS.includes(ext) && !ALLOWED_TYPES.includes(file.type)) {
      return `不支持的文件类型: ${file.name}。支持: ${ALLOWED_EXTENSIONS.join(', ')}`
    }
    if (file.size > 50 * 1024 * 1024) {
      return `文件过大: ${file.name}。最大支持 50MB`
    }
    return null
  }

  const handleFile = useCallback(async (file: File) => {
    const error = validateFile(file)
    if (error) {
      setUploadError(error)
      return
    }

    setUploading(true)
    setUploadError(null)

    try {
      const result = await uploadFile(file)
      onUploadSuccess(result)
    } catch (err) {
      const message = err instanceof Error ? err.message : '上传失败，请重试'
      setUploadError(message)
    } finally {
      setUploading(false)
    }
  }, [onUploadSuccess])

  const handleDrop = useCallback((e: DragEvent) => {
    e.preventDefault()
    setIsDragging(false)

    const files = e.dataTransfer.files
    if (files.length > 0) {
      handleFile(files[0])
    }
  }, [handleFile])

  const handleDragOver = useCallback((e: DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleClick = () => {
    fileInputRef.current?.click()
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) {
      handleFile(files[0])
    }
    // Reset input so the same file can be re-uploaded
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  return (
    <div className="document-upload">
      <h3 className="document-upload__title">文档上传</h3>

      <div
        className={`document-upload__zone ${isDragging ? 'document-upload__zone--dragging' : ''} ${uploading ? 'document-upload__zone--uploading' : ''}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={handleClick}
      >
        <input
          ref={fileInputRef}
          type="file"
          className="document-upload__input"
          accept={ALLOWED_EXTENSIONS.join(',')}
          onChange={handleFileChange}
          hidden
        />

        {uploading ? (
          <div className="document-upload__status">
            <span className="document-upload__spinner" />
            <p>正在上传...</p>
          </div>
        ) : (
          <div className="document-upload__prompt">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            <p>拖拽文件到此处，或点击选择</p>
            <span className="document-upload__hint">
              支持 {ALLOWED_EXTENSIONS.join(', ')} 格式，最大 50MB
            </span>
          </div>
        )}
      </div>

      {uploadError && (
        <div className="document-upload__error">{uploadError}</div>
      )}
    </div>
  )
}
