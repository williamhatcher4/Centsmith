import path from 'node:path'
import { expect, test } from '@playwright/test'
import { login } from './helpers'

const fixture = path.resolve(__dirname, '..', 'fixtures', 'sample-statement.csv')

test('classifies an inbox row as personal and categorizes it', async ({ page }) => {
  await login(page)

  // Seed: import the sample statement first (idempotent – handles retry scenario)
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

  // Classify the Coffee shop row as Personal (backend sorts date DESC so it is not row 1)
  await page.goto('/inbox')
  const coffeeShopRow = page.getByRole('row').filter({
    has: page.getByRole('cell', { name: 'Coffee shop', exact: true }),
  })
  if (await coffeeShopRow.count() > 0) {
    await coffeeShopRow.getByRole('button', { name: /personal/i }).click()
    // Wait for the mutation to complete (row leaves the unsorted inbox)
    await expect(coffeeShopRow).not.toBeVisible({ timeout: 10_000 })
  }

  // Categorize it from the Personal Inbox
  await page.goto('/personal-inbox')
  await expect(page.getByText('Coffee shop').first()).toBeVisible()
  await page.getByLabel(/Category for Coffee shop/i).selectOption('Dining')
  await expect(page.getByText('Coffee shop')).not.toBeVisible({ timeout: 5_000 })
})
