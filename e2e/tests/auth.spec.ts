import { expect, test } from '@playwright/test'

test.describe('Authentication', () => {
  test('logs in with valid credentials and lands on the dashboard', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel('Username').fill('e2e_user')
    await page.getByLabel('Password').fill('e2e_password')
    await page.getByRole('button', { name: /sign in/i }).click()

    await expect(page).toHaveURL(/\/$/)
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
  })

  test('rejects invalid credentials with a visible error', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel('Username').fill('e2e_user')
    await page.getByLabel('Password').fill('wrong_password')
    await page.getByRole('button', { name: /sign in/i }).click()

    await expect(page.getByRole('alert')).toContainText(/incorrect/i)
  })
})
