import { defineConfig, devices } from '@playwright/test';

// E2E nutzt eigene Ports, damit laufende Dev-Server (8000/5173) nie mitbenutzt oder gestört werden.
const BACKEND_PORT = Number(process.env.E2E_BACKEND_PORT ?? 8100);
const FRONTEND_PORT = Number(process.env.E2E_FRONTEND_PORT ?? 5273);
const BASE_URL = `http://127.0.0.1:${FRONTEND_PORT}`;

export default defineConfig({
  // platform-fix G-07: Challenge-E2E (challenge/e2e) läuft im selben Lauf mit.
  testDir: '../..',
  testMatch: ['tests/e2e/specs/**/*.spec.ts', 'challenge/e2e/**/*.spec.ts'],
  outputDir: './test-results',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
  use: {
    baseURL: BASE_URL,
    locale: 'de-DE',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      // E2E_CHANNEL=msedge erlaubt lokal den installierten Edge statt des Playwright-Chromium.
      use: { ...devices['Desktop Chrome'], channel: process.env.E2E_CHANNEL },
    },
  ],
  webServer: [
    {
      command: 'node tests/e2e/support/start-backend.mjs',
      cwd: '../..',
      url: `http://127.0.0.1:${BACKEND_PORT}/api/v1/health`,
      // platform-fix H-12: feste Ankerzeit, damit Seed und Challenge-E2E deterministisch sind.
      env: { E2E_BACKEND_PORT: String(BACKEND_PORT), APP_FROZEN_NOW: '2026-10-17T09:00:00+02:00' },
      reuseExistingServer: false,
      timeout: 60_000,
      stdout: 'pipe',
      stderr: 'pipe',
    },
    {
      command: 'npm run dev -w platform/frontend',
      cwd: '../..',
      url: BASE_URL,
      env: {
        VITE_PORT: String(FRONTEND_PORT),
        VITE_API_TARGET: `http://127.0.0.1:${BACKEND_PORT}`,
      },
      reuseExistingServer: false,
      timeout: 60_000,
      stdout: 'pipe',
      stderr: 'pipe',
    },
  ],
});
