import type { Page } from '@playwright/test'

export async function login(page: Page, username = 'e2e_user', password = 'e2e_password') {
  await page.goto('/login')
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForURL(/\/$/)
}
