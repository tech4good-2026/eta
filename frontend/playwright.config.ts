import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir: './e2e', testMatch: '*.e2e.ts', workers: 1, retries: 0,
  use: { baseURL: 'http://127.0.0.1:4178', trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
  webServer: [
    { command: 'uv run --project ../backend --frozen uvicorn app.main:app --app-dir ../backend --host 127.0.0.1 --port 18083',
      url: 'http://127.0.0.1:18083/health', reuseExistingServer: false,
      env: { ROUTE_PROVIDER: 'mock', CORS_ORIGINS: '["http://127.0.0.1:4178"]' } },
    { command: 'npm run dev -- --port 4178 --host 127.0.0.1', url: 'http://127.0.0.1:4178',
      reuseExistingServer: false, env: { VITE_API_BASE_URL: 'http://127.0.0.1:18083/api/v1' } },
  ],
});
