import { defineConfig, devices } from '@playwright/test'
import path from 'node:path'

const BACKEND_PORT = Number(process.env.CENTSMITH_E2E_BACKEND_PORT ?? 18012)
const FRONTEND_PORT = Number(process.env.CENTSMITH_E2E_FRONTEND_PORT ?? 15175)
const DB_PATH = path.resolve(process.cwd(), '..', 'centsmith-e2e.db')
const SESSION_SECRET = 'centsmith-e2e-secret-do-not-use-anywhere-else'

const repoRoot = path.resolve(__dirname, '..')
const backendDir = path.join(repoRoot, 'backend')
const frontendDir = path.join(repoRoot, 'frontend')
const pythonExe = path.join(backendDir, '.venv', 'Scripts', 'python.exe')

const sharedEnv: Record<string, string> = {
  DATABASE_URL: `sqlite:///${DB_PATH.replace(/\\/g, '/')}`,
  SECRET_KEY: SESSION_SECRET,
  ENVIRONMENT: 'development',
  CORS_ORIGINS: `http://127.0.0.1:${FRONTEND_PORT}`,
  ADMIN_USERNAME: 'e2e_user',
  ADMIN_PASSWORD: 'e2e_password',
}

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  globalSetup: require.resolve('./global-setup'),
  use: {
    baseURL: `http://127.0.0.1:${FRONTEND_PORT}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: [
    {
      command: `"${pythonExe}" -m uvicorn app.main:app --host 127.0.0.1 --port ${BACKEND_PORT}`,
      cwd: backendDir,
      url: `http://127.0.0.1:${BACKEND_PORT}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: sharedEnv,
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${FRONTEND_PORT}`,
      cwd: frontendDir,
      url: `http://127.0.0.1:${FRONTEND_PORT}`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: {
        VITE_API_PROXY_TARGET: `http://127.0.0.1:${BACKEND_PORT}`,
      },
    },
  ],
})
