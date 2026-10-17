import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

const apiTarget = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000';
const port = Number(process.env.VITE_PORT ?? 5173);

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1',
    port,
    strictPort: true,
    proxy: { '/api': { target: apiTarget, changeOrigin: false } },
  },
  build: {
    // Prototyp: Hauptbündel (React, Router, Query, i18n) liegt knapp über 500 kB; Diagramme sind abgespalten.
    chunkSizeWarningLimit: 600,
  },
  preview: { host: '127.0.0.1', port, strictPort: true },
  test: {
    environment: 'jsdom',
    testTimeout: 20_000,
    // Plattformtests neben den Komponenten; Challenge-Tests liegen unter challenge/frontend.
    include: ['src/**/*.test.{ts,tsx}', '../../challenge/frontend/**/*.test.{ts,tsx}'],
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: true,
  },
});
