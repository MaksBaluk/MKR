import { defineConfig, devices } from '@playwright/test';

// Ruling: runs against the Docker stack (nginx on 8080). Start it first: cd app && docker compose up -d
export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  use: { baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8080', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
