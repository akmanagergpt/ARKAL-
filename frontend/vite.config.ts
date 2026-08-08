import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// Phase 1 bootstrap: workspace configuration only.
// No application entry, route or component exists yet. The Command Center is
// delivered as per-capability slices from Phase 5 and consolidated at Phase 27.
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
});
