# RAG Chatbot Frontend

A RAG (Retrieval-Augmented Generation) chatbot frontend built with React, TypeScript, and Vite. Users upload documents, then ask questions that are answered based on document content.

## Project Purpose

This is the frontend for a RAG chatbot system. It provides:
- Document upload (drag-and-drop or click-to-select) in a collapsible sidebar
- Conversational Q&A interface with the chat window
- Source citations showing which documents contributed to each answer
- Markdown rendering of assistant responses

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | React 18.3 |
| Language | TypeScript 5.6 (strict mode) |
| Build tool | Vite 6 |
| Markdown rendering | react-markdown 9 |
| Styling | Plain CSS with CSS variables |
| Backend proxy | Vite dev proxy: `/api` -> `http://localhost:8000` |

**No third-party UI libraries, no CSS-in-JS, no Tailwind.**

## How to Run

```bash
cd frontend
npm install
npm run dev          # starts on http://localhost:5173
```

The Vite dev server proxies all `/api/*` requests to `http://localhost:8000` so the backend must be running on port 8000.

Build:
```bash
npm run build        # runs tsc -b then vite build
```

## Architecture

### Component Tree

```
main.tsx
  StrictMode
    App                          ← owns sidebar toggle state + documents list
      aside.sidebar              ← collapsible (mobile: full overlay)
        sidebar__header          ← logo "RAG Chat"
        DocumentUpload           ← drag/drop file upload component
        sidebar__documents       ← uploaded documents list
        sidebar__footer          ← "清空对话" (clear chat) button
      main.main                  ← main chat area
        toast (error banner)     ← positioned absolutely, shown when error
        ChatWindow               ← chat container
          chat-window__header    ← "RAG 智能问答" title
          chat-window__messages  ← scrollable message list
            EmptyState           ← shown when no messages
            MessageBubble[]      ← one per message
              SourceCitation[]   ← one per source document (assistant only)
            Typing indicator     ← shown while loading
          chat-window__input     ← bottom input area
            ChatInput            ← textarea + send button
```

### Data Flow

```
User types message
  -> ChatInput.onSend(query)
    -> ChatWindow.onSend(query)
      -> App.sendMessage(query)    ← from useChat hook
        -> useChat.sendMessage()
          -> api/client.sendMessage({ query, history })
            -> POST /api/chat      ← proxied to backend :8000
          <- ChatResponse { answer, sources }
        -> historyRef updated (max 40 entries / 20 turns)
        -> new assistant Message added to messages[]
      -> ChatWindow re-renders
        -> MessageBubble renders react-markdown
        -> SourceCitation[] renders expandable citations

User uploads file
  -> DocumentUpload drops/clicks file
    -> api/client.uploadFile(file)
      -> POST /api/upload (FormData)
    <- UploadResponse { file_id, filename, chunks_count, status }
    -> App.handleUploadSuccess adds to documents[]
    -> Sidebar re-renders document list
```

### State Management (useChat Hook)

The custom hook `useChat()` in `src/hooks/useChat.ts` manages all chat state:

| State | Type | Purpose |
|---|---|---|
| `messages` | `Message[]` | All chat messages (user + assistant) |
| `isLoading` | `boolean` | True while waiting for backend response |
| `error` | `string \| null` | Error message to display in toast |
| `sendMessage(query)` | function | Sends a message, updates messages + history |
| `clearMessages()` | function | Resets messages and conversation history |
| `setError(err)` | function | Sets or clears error state |

Key implementation details:
- `historyRef` (useRef) tracks conversation turns sent to the backend, not rendered
- History is capped at 40 entries (20 Q&A turns) to avoid context overflow
- User and assistant messages get `crypto.randomUUID()` as IDs
- `isLoading` gates the ChatInput (disabled while waiting) and shows typing indicator

## Key Files

### Entry Point

| File | Role |
|---|---|
| `index.html` | HTML entry, lang="zh-CN", mounts `#root` |
| `src/main.tsx` | React entry, renders `<App />` inside `<StrictMode>` |
| `src/App.tsx` | Root component: sidebar layout, toast errors, wire up useChat |
| `src/vite-env.d.ts` | Vite client type reference |

### Types

| File | Role |
|---|---|
| `src/types/index.ts` | All TypeScript interfaces: `Message`, `SourceDoc`, `ChatRequest`, `ChatResponse`, `UploadResponse`, `DocumentInfo` |

- `Message` — `id`, `role` ('user'\|'assistant'), `content`, optional `sources` (SourceDoc[]), `timestamp`
- `SourceDoc` — `content` (text excerpt), `metadata` (Record<string, any>), `score` (0-1 relevance)
- `ChatRequest` — `query` (string), optional `history` (role+content pairs)
- `ChatResponse` — `answer` (string), `sources` (SourceDoc[])
- `UploadResponse` — `file_id`, `filename`, `chunks_count`, `status`
- `DocumentInfo` — extends UploadResponse with optional `uploaded_at`

### API Client

| File | Role |
|---|---|
| `src/api/client.ts` | HTTP client for backend communication |

Three exported functions:
- `sendMessage(request: ChatRequest): Promise<ChatResponse>` — POST `/api/chat`, JSON body
- `uploadFile(file: File): Promise<UploadResponse>` — POST `/api/upload`, FormData (multipart)
- `healthCheck(): Promise<boolean>` — GET `/api/health`, returns true/false (not currently used in UI)

Error handling: reads `error.detail` from JSON response body, falls back to `'Request failed'` / `'Upload failed'` / HTTP status.

### Hooks

| File | Role |
|---|---|
| `src/hooks/useChat.ts` | Custom hook: messages state, loading, error, sendMessage, clearMessages |

### Components

| File | Role |
|---|---|
| `src/components/ChatWindow.tsx` | Chat area container: header, message list, typing indicator, input; auto-scrolls to bottom on new messages |
| `src/components/ChatInput.tsx` | Textarea with auto-resize (max 5 rows), Enter to send (Shift+Enter for newline), spinner when loading |
| `src/components/MessageBubble.tsx` | Renders a single message: plain text for user, react-markdown for assistant; renders SourceCitation list below assistant bubbles |
| `src/components/SourceCitation.tsx` | Expandable citation card: shows filename, relevance score %, expand to show content + metadata key-value pairs |
| `src/components/DocumentUpload.tsx` | Drag-and-drop file upload zone: validates file type (.txt/.md/.pdf/.docx) and size (50MB max), shows spinner during upload |
| `src/components/EmptyState.tsx` | Welcome screen with icon, title, and description; shown when no messages exist |

### Styles

| File | Role |
|---|---|
| `src/App.css` | All application styles in a single CSS file (~816 lines) |

### Config

| File | Role |
|---|---|
| `vite.config.ts` | Vite config: React plugin, port 5173, `/api` proxy to localhost:8000 |
| `tsconfig.json` | Project references to tsconfig.app.json + tsconfig.node.json |
| `tsconfig.app.json` | App TS config: strict, ES2020, react-jsx, noUnusedLocals, noUnusedParameters |
| `tsconfig.node.json` | Node TS config (for vite.config.ts): strict, ES2022 |

## Component Conventions

### Props Interfaces

Every component that accepts props defines an interface directly above the component:

```tsx
interface ComponentNameProps {
  propName: type
  optionalProp?: type
}

export default function ComponentName({ propName, optionalProp = defaultValue }: ComponentNameProps) {
```

No `React.FC` typing — components are regular functions with typed props destructuring.

### File Structure

- One component per file
- Default export only
- No barrel exports (no `index.ts` re-exporting from component directories)
- SVG icons are inlined as JSX (no icon library or SVG files)
- Components live in `src/components/` (flat, no subdirectories)

### Naming

- Component files: PascalCase (e.g., `ChatInput.tsx`, `MessageBubble.tsx`)
- Hook files: camelCase with `use` prefix (e.g., `useChat.ts`)
- Type files: camelCase (e.g., `index.ts` inside `types/`)
- API files: camelCase (e.g., `client.ts` inside `api/`)
- CSS class names: BEM-like, lowercase with hyphens (e.g., `.chat-window__messages`, `.message-bubble--user`)

### State Patterns

- `useState` for local component state (input text, drag state, expanded citations)
- `useRef` for DOM refs (textarea, scroll anchor, file input) and mutable values that shouldn't trigger re-renders (historyRef)
- `useCallback` for event handlers and functions passed as props
- `useEffect` for side effects: auto-resize textarea, auto-scroll, refocus after sending

## Styling Conventions

### CSS Variable System

All colors, shadows, radii, and fonts are defined as CSS variables in `:root`:

```css
/* Colors */
--color-primary: #2563eb          /* Blue 600 */
--color-primary-hover: #1d4ed8    /* Blue 700 */
--color-primary-light: #dbeafe    /* Blue 100 */
--color-bg: #ffffff
--color-bg-secondary: #f8fafc     /* Slate 50 */
--color-bg-tertiary: #f1f5f9      /* Slate 100 */
--color-sidebar: #f8fafc
--color-border: #e2e8f0           /* Slate 200 */
--color-text: #1e293b             /* Slate 800 */
--color-text-secondary: #64748b   /* Slate 500 */
--color-text-muted: #94a3b8       /* Slate 400 */
--color-user-bubble: #2563eb
--color-user-text: #ffffff
--color-assistant-bubble: #f1f5f9
--color-assistant-text: #1e293b
--color-error: #ef4444
--color-error-bg: #fef2f2
--color-success: #22c55e
--color-success-bg: #f0fdf4

/* Shadows */
--shadow-sm: 0 1px 2px rgba(0,0,0,0.05)
--shadow-md: 0 4px 6px -1px rgba(0,0,0,0.1)
--shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.1)

/* Radii */
--radius-sm: 6px
--radius-md: 10px
--radius-lg: 16px

/* Layout */
--sidebar-width: 320px

/* Typography */
--font-sans: system font stack
--font-mono: SF Mono, Fira Code, etc.
```

### BEM-like Class Naming

- **Block**: component name, lowercase with hyphens (`.chat-window`, `.message-bubble`, `.empty-state`)
- **Element**: block + `__` + element name (`.sidebar__header`, `.chat-input__textarea`, `.citation__score`)
- **Modifier**: block/element + `--` + modifier name (`.message-row--user`, `.toast--error`, `.document-upload__zone--dragging`)
- **State variant**: modifier pattern (`.sidebar--open`, `.citation__arrow--open`)

### Responsive Breakpoints

Single breakpoint at `768px`:
- Sidebar becomes a fixed-position overlay with slide-in animation
- Sidebar toggle button becomes visible
- Overlay backdrop appears behind sidebar
- Message bubbles expand to 95% width
- Chat padding reduced

### Animations

Defined as `@keyframes`:
- `fadeIn` — messages slide up and fade in (0.2s)
- `slideDown` — toast slides down from top (0.3s)
- `typingBounce` — three dots animate with staggered delays (1.4s)
- `spin` — loading spinner (0.6s linear infinite)

## API Contract (Backend Expected)

### POST /api/chat
```
Request:  { query: string, history?: { role: string, content: string }[] }
Response: { answer: string, sources: { content: string, metadata: Record<string,any>, score: number }[] }
```

### POST /api/upload
```
Request:  FormData with "file" field
Response: { file_id: string, filename: string, chunks_count: number, status: string }
```

### GET /api/health
```
Response: any 2xx status
```

## Dependencies

| Dependency | Version | Purpose |
|---|---|---|
| react | ^18.3.1 | UI framework |
| react-dom | ^18.3.1 | DOM rendering |
| react-markdown | ^9.0.1 | Render markdown in assistant messages |
| typescript | ~5.6.2 | Type checking (dev) |
| vite | ^6.0.0 | Build tool and dev server (dev) |
| @vitejs/plugin-react | ^4.3.4 | Vite React plugin (dev) |
| @types/react | ^18.3.12 | React type definitions (dev) |
| @types/react-dom | ^18.3.1 | ReactDOM type definitions (dev) |
