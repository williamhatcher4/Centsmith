import path from 'node:path'
import { expect, test } from '@playwright/test'
import { login } from './helpers'

const fixture = path.resolve(__dirname, '..', 'fixtures', 'sample-statement.csv')

test('classifies an inbox row as personal and categorizes it', async ({ page }) => {
  await login(page)

  // Seed: import the sample statement first
  await page.goto('/transactions')
  await page.getByRole('button', { name: /^import$/i }).click()
  await page.setInputFiles('input[type="file"]', fixture)
  await page.getByRole('button', { name: /Import \d+/i }).click()
  await page.getByRole('button', { name: /done/i }).click()

  // Classify the first row as Personal
  await page.goto('/inbox')
  await expect(page.getByText('Coffee shop').first()).toBeVisible()
  await page.getByRole('button', { name: /personal/i }).first().click()

  // Categorize it from the Personal Inbox
  await page.goto('/personal-inbox')
  await expect(page.getByText('Coffee shop').first()).toBeVisible()
  await page.getByLabel(/Category for Coffee shop/i).selectOption('Dining')
  await expect(page.getByText('Coffee shop')).not.toBeVisible({ timeout: 5_000 })
})
