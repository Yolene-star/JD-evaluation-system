import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  // Vitest component contracts use .spec.tsx; Playwright should only collect browser tests.
  testMatch: /.*\.(spec|e2e)\.ts$/,
  use: { baseURL: 'http://127.0.0.1:5192' },
  webServer: [
    { command: 'E:\\Anaconda3\\python.exe -m uvicorn backend.app.main:app --app-dir .. --host 127.0.0.1 --port 8001', port: 8001, reuseExistingServer: true },
    { command: 'npm run dev -- --host 127.0.0.1 --port 5192 --strictPort', port: 5192, reuseExistingServer: true },
  ],
})
