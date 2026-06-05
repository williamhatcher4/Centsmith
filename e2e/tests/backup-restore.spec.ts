import { promises as fs } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { expect, test } from '@playwright/test'
import { login } from './helpers'

// Exercises the Data & diagnostics card. The backup download is non-destructive;
// the restore step is driven up to the destructive confirm and then cancelled, so
// the shared e2e database is left untouched for later specs. (The actual restore
// swap is covered by the backend round-trip test.)
test('backup download, and restore asks for confirmation', async ({ page }) => {
  await login(page)
  await page.goto('/settings')
  await expect(page.getByText('Data & diagnostics')).toBeVisible()

  // Back up the database and confirm it is a real SQLite file.
  const [backup] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: /back up data/i }).click(),
  ])
  const backupPath = path.join(os.tmpdir(), `centsmith-e2e-backup-${Date.now()}.db`)
  await backup.saveAs(backupPath)
  const header = (await fs.readFile(backupPath)).subarray(0, 15).toString('utf-8')
  expect(header).toBe('SQLite format 3')

  // Choosing a file surfaces a destructive confirm; cancel so no swap happens.
  await page.setInputFiles('input[type="file"]', backupPath)
  await expect(page.getByText(/replaces ALL current data/i)).toBeVisible()
  await page.getByRole('button', { name: /cancel/i }).click()
  await expect(page.getByText(/replaces ALL current data/i)).toHaveCount(0)

  await fs.rm(backupPath, { force: true })
})
