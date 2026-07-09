import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        selfHandleResponse: true,
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes, req, res) => {
            // selfHandleResponse: true bypasses http-proxy's internal response
            // processing (web_o passes + proxyRes.pipe) entirely. This is
            // necessary for SSE streaming because http-proxy's writeHeaders
            // pass only calls res.setHeader() without res.writeHead(). Node.js
            // defers the actual header write until the first res.write(), which
            // batches headers with the first data chunk. For SSE, this causes
            // the entire response body to buffer before the first byte reaches
            // the client.
            //
            // By calling res.writeHead() ourselves and piping manually, headers
            // are flushed immediately and body chunks stream unbuffered.
            const headers: Record<string, string> = {}
            for (const [key, value] of Object.entries(proxyRes.headers)) {
              if (value !== undefined) headers[key] = value as string
            }
            // Force chunked transfer — prevents any content-length based buffering
            delete headers['content-length']
            res.writeHead(proxyRes.statusCode || 200, headers)
            proxyRes.pipe(res)
          })
        },
      },
    },
  },
})
