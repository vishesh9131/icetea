import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Bloomberg-style terminal frontend for the Icetea backend.
// Dev server listens on 5173 (default). The backend at :8000 has CORS
// configured to allow this origin, so the chat SSE stream works end-to-end.
export default defineConfig({
  // /app/ when built into the unified Netlify dist (see scripts/build-netlify-unified.sh)
  base: process.env.VITE_BASE || '/',
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})
