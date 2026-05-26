import path from 'node:path'
import { expect, test } from '@playwright/test'
import { login } from './helpers'

// Dedicated fixture so this test does not collide with import.spec.ts (which
// uses sample-statement.csv and expects exactly 4 new rows on import).
const fixture = path.resolve(__dirname, '..', 'fixtures', 'classify-statement.csv')
const TARGET = 'Specialty bookstore'

test('classifies an inbox row as personal and categorizes it', async ({ page }) => {
  await login(page)

  // Seed: import the dedicated classify statement (idempotent — handles retries)
  await page.goto('/transactions')
  await page.getByRole('button', { name: /^import$/i }).click()
  await page.setInputFiles('input[type="file"]', fixture)
  await expect(page.getByText(/import preview/i)).toBeVisible()
  const importBtn = page.getByRole('button', { name: /Import \d+/i })
  if (await importBtn.isEnabled()) {
    await importBtn.click()
    await page.getByRole('button', { name: /done/i }).click()
  } else {
    // 0 new rows — already imported on a prior attempt; close the dialog
    await page.getByRole('button', { name: /back/i }).click()
    await page.getByRole('button', { name: /cancel/i }).click()
  }

  // Classify the target row as Personal (skip if already classified on a retry)
  await page.goto('/inbox')
  const targetRow = page.locator('tbody tr').filter({ hasText: TARGET })
  if ((await targetRow.count()) > 0) {
    await targetRow.getByRole('button', { name: /personal/i }).click()
    await expect(targetRow).toHaveCount(0, { timeout: 10_000 })
  }

  // Categorize it from the Personal Inbox
  await page.goto('/personal-inbox')
  await expect(page.getByText(TARGET).first()).toBeVisible({ timeout: 10_000 })
  await page.getByLabel(new RegExp(`Category for ${TARGET}`, 'i')).selectOption('Dining')
  await expect(page.getByText(TARGET)).toHaveCount(0, { timeout: 10_000 })
})
