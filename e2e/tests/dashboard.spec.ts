import { expect, test } from '@playwright/test'
import { login } from './helpers'

test('renders the dashboard stat cards after login', async ({ page }) => {
  await login(page)

  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
  await expect(page.getByText('Personal spending')).toBeVisible()
  await expect(page.getByText('Work spending')).toBeVisible()
  await expect(page.getByText('Income', { exact: true }).first()).toBeVisible()
})
