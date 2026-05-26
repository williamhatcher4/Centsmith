import path from 'node:path'
import { expect, test } from '@playwright/test'
import { login } from './helpers'

const fixture = path.resolve(__dirname, '..', 'fixtures', 'sample-statement.csv')

test('imports a sample statement and shows the new rows in the Inbox', async ({ page }) => {
  await login(page)

  await page.goto('/transactions')
  await page.getByRole('button', { name: /^import$/i }).click()
  await page.setInputFiles('input[type="file"]', fixture)

  await expect(page.getByText(/import preview/i)).toBeVisible()
  await expect(page.getByText('Account Activity CSV')).toBeVisible()
  // 5 rows total, 1 payment credit ignored, 4 to import (3 debits + 1 refund credit)
  const importButton = page.getByRole('button', { name: /Import 4/i })
  await expect(importButton).toBeEnabled()
  await importButton.click()

  await expect(page.getByText(/transactions imported/i)).toBeVisible()
  await page.getByRole('button', { name: /done/i }).click()

  await page.goto('/inbox')
  await expect(page.getByText('Coffee shop').first()).toBeVisible()
  await expect(page.getByText('Grocery store').first()).toBeVisible()
})
