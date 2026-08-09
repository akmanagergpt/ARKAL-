/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// Phase 5 Package 4B delivers the first slice: the Project Registry page over
// the Command Center API. The Command Center itself is delivered as
// per-capability slices and consolidated at Phase 27.
// The Command Center API is served by the Python backend. Proxying keeps the
// browser on one origin, so the app calls `/api/...` in development, in the
// preview build and in the T10 journey exactly as it would when the two halves
// are served together. No CORS relaxation exists anywhere as a result.
const API_PROXY = {
  '/api': {
    target: process.env.ARKALI_API_TARGET ?? 'http://127.0.0.1:8000',
    changeOrigin: false,
  },
};

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  server: {
    // Loopback only. TRUST-2 generated products run under NET_EGRESS_CONTROL
    // with loopback permitted; see MASTER_SPECIFICATION Trust-Tiered Isolation.
    host: '127.0.0.1',
    strictPort: true,
    proxy: API_PROXY,
  },
  // `vite preview` serves the real production build. The T10 journey runs
  // against it rather than against the dev server, so the evidence covers the
  // artifact that would actually ship.
  preview: {
    host: '127.0.0.1',
    strictPort: true,
    proxy: API_PROXY,
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.{ts,tsx}'],
    // A component test is not a browser test. T10 browser/E2E is NOT_CONFIGURED
    // and is owned by a later package; nothing here may be reported as T10.
    restoreMocks: true,
  },
});
