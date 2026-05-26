import { execFileSync } from 'node:child_process'
import { existsSync, rmSync } from 'node:fs'
import path from 'node:path'

export default async function globalSetup() {
  const repoRoot = path.resolve(__dirname, '..')
  const dbPath = path.join(repoRoot, 'centsmith-e2e.db')
  const pythonExe = path.join(repoRoot, 'backend', '.venv', 'Scripts', 'python.exe')

  for (const candidate of [dbPath, `${dbPath}-journal`, `${dbPath}-wal`, `${dbPath}-shm`]) {
    if (existsSync(candidate)) rmSync(candidate)
  }

  const dbUrl = `sqlite:///${dbPath.replace(/\\/g, '/')}`
  execFileSync(
    pythonExe,
    ['-m', 'app.scripts.seed_e2e_user'],
    {
      cwd: path.join(repoRoot, 'backend'),
      stdio: 'inherit',
      env: {
        ...process.env,
        DATABASE_URL: dbUrl,
        E2E_USERNAME: 'e2e_user',
        E2E_PASSWORD: 'e2e_password',
      },
    },
  )
}
