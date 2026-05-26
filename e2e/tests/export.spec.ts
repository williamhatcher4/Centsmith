import { expect, test } from '@playwright/test'
import { login } from './helpers'

test('downloads a personal CSV export from the Exports page', async ({ page }) => {
  await login(page)
  await page.goto('/exports')

  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('link', { name: /personal csv/i }).click(),
  ])

  expect(download.suggestedFilename()).toMatch(/^personal_transactions_\d{8}\.csv$/)
})
