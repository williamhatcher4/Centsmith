import path from 'node:path'
import { expect, test } from '@playwright/test'
import { login } from './helpers'

// Imports a statement with unique descriptions (so it never collides with the
// shared-DB source_hash dedup used by other specs), then undoes the import from
// the Exports → "Past imports" section and verifies every created row is gone.
const fixture = path.resolve(__dirname, '..', 'fixtures', 'undo-statement.csv')

test('undo a previous import removes every row it created', async ({ page }) => {
  await login(page)

  // Import the unique fixture.
  await page.goto('/transactions')
  await page.getByRole('button', { name: /^import$/i }).click()
  await page.setInputFiles('input[type="file"]', fixture)

  await expect(page.getByText(/import preview/i)).toBeVisible()
  const importButton = page.getByRole('button', { name: /Import 3/i })
  await expect(importButton).toBeEnabled()
  await importButton.click()
  await expect(page.getByText(/transactions imported/i)).toBeVisible()
  await page.getByRole('button', { name: /done/i }).click()

  // Rows are now in the Inbox (imported = unsorted).
  await page.goto('/inbox')
  await expect(page.getByText('Undo Probe Alpha').first()).toBeVisible()

  // Undo from Exports → Past imports.
  await page.goto('/exports')
  const undoRow = page.locator('tr').filter({ hasText: 'undo-statement.csv' })
  await expect(undoRow).toBeVisible()
  await undoRow.getByRole('button', { name: /undo import undo-statement\.csv/i }).click()

  // Confirm the destructive dialog.
  await page.getByRole('button', { name: 'Undo import', exact: true }).click()
  await expect(page.getByText(/removed 3 transactions/i)).toBeVisible({ timeout: 5_000 })

  // Past-imports row is gone, and so are the transactions.
  await expect(page.locator('tr').filter({ hasText: 'undo-statement.csv' })).toHaveCount(0)
  await page.goto('/inbox')
  await expect(page.getByText('Undo Probe Alpha')).toHaveCount(0)
  await expect(page.getByText('Undo Probe Beta')).toHaveCount(0)
  await expect(page.getByText('Undo Probe Gamma')).toHaveCount(0)
})
