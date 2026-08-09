/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// Phase 5 Package 4B delivers the first slice: the Project Registry page over
// the Command Center API. The Command Center itself is delivered as
// per-capability slices and consolidated at Phase 27.
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
