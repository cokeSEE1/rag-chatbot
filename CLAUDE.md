# RAG Chatbot — 全栈项目

本地 RAG 智能问答机器人，前端 React + TypeScript，后端 FastAPI + ChromaDB + Ollama。

## Workspace

| 项目 | 路径 | 用途 |
|------|------|------|
| 根目录 | `/Users/lanzhang/Desktop/rag-chatbot` | 项目总览 |
| backend | `/Users/lanzhang/Desktop/rag-chatbot/backend` | FastAPI 后端 |
| frontend | `/Users/lanzhang/Desktop/rag-chatbot/frontend` | React 前端 |

## 快速启动

```bash
# 1. 确保 Ollama 已运行且模型已拉取
ollama list | grep bge-m3
ollama list | grep deepseek-r1

# 2. 后端
cd ~/Desktop/rag-chatbot/backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 3. 前端（新终端）
cd ~/Desktop/rag-chatbot/frontend
npm run dev
```

## 技术栈

| 层 | 技术 |
|---|---|
| 前端框架 | React 18 + TypeScript 5.6 + Vite 6 |
| 前端样式 | 纯 CSS + CSS 变量主题，无第三方 UI 库 |
| 后端框架 | FastAPI + Uvicorn |
| 向量数据库 | ChromaDB (PersistentClient) |
| Embedding | Ollama + bge-m3 (1024维) |
| LLM | Ollama + deepseek-r1:7b |
| 包管理 | pip (后端) / npm (前端) |

## 架构

```
┌─────────────────┐     ┌──────────────────────────────────────┐
│  React Frontend │────▶│        Python FastAPI Backend         │
│  (:5173)        │◀────│        (:8000)                       │
│                 │     │                                      │
│  • 聊天界面      │     │  POST /api/upload                    │
│  • 文档上传      │     │  Upload → Clean → Embed → Store      │
│  • 来源展示      │     │                                      │
│                 │     │  POST /api/chat                      │
│                 │     │  Retrieve → Build Prompt → Generate   │
└─────────────────┘     └──────────────────────────────────────┘
```

## 子模块 CLAUDE.md

- [backend/CLAUDE.md](backend/CLAUDE.md) — 后端架构、Pipeline 模式、代码风格
- [frontend/CLAUDE.md](frontend/CLAUDE.md) — 前端组件树、数据流、CSS 约定

## GitHub

https://github.com/cokeSEE1/rag-chatbot
