export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceDoc[];
  retrieval?: RetrievalInfo;
  timestamp: number;
}

export interface SourceDoc {
  content: string;
  metadata: Record<string, any>;
  score: number;
}

export interface RetrievalResult {
  content: string;
  metadata: Record<string, any>;
  score: number;
}

export interface RetrievalInfo {
  count: number;
  latencyMs: number;
  results: RetrievalResult[];
}

export interface ChatRequest {
  query: string;
  history?: { role: string; content: string }[];
}

export interface ChatResponse {
  answer: string;
  sources: SourceDoc[];
}

export interface UploadResponse {
  file_id: string;
  filename: string;
  chunks_count: number;
  status: string;
}

export interface DocumentInfo {
  file_id: string;
  filename: string;
  chunks_count: number;
  status: string;
  uploaded_at?: string;
}
