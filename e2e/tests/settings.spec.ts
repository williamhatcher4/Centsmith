import { expect, test } from '@playwright/test'
import { login } from './helpers'

// Hides the Spending page via Settings, then verifies that the nav no longer
// surfaces Spending and that a manual navigation redirects somewhere else.
// Cleans up at the end so other specs see the default page list.
test('hide and reveal the Spending page via Settings', async ({ page }) => {
  await login(page)
  await page.goto('/settings')

  // Ensure baseline: Spending is visible at the start of this test.
  await page.request.put('/api/v1/settings', {
    data: {
      personal_categories: [
        'Groceries', 'Dining', 'Transportation', 'Home', 'Health',
        'Subscriptions', 'Shopping', 'Travel', 'Entertainment',
        'Personal Care', 'Gifts', 'Other', 'Transfer', 'Income', 'Reimbursement',
      ],
      hidden_pages: [],
    },
  })
  await page.reload()
  const desktopNav = page.getByRole('navigation', { name: 'Primary' })
  await expect(desktopNav.getByRole('link', { name: 'Spending' })).toBeVisible()

  // Toggle Spending off, then Save pages.
  await page.getByRole('checkbox', { name: 'Show Spending' }).uncheck()
  await page.getByRole('button', { name: /save pages/i }).click()
  await expect(page.getByText(/page visibility updated/i)).toBeVisible({ timeout: 5_000 })

  // Spending should be gone from the nav.
  await expect(desktopNav.getByRole('link', { name: 'Spending' })).toHaveCount(0)

  // Navigating directly to /spending should redirect away.
  await page.goto('/spending')
  await page.waitForURL((url) => !url.pathname.startsWith('/spending'), { timeout: 5_000 })
  expect(page.url()).not.toContain('/spending')

  // Restore default state so other specs are unaffected.
  await page.request.put('/api/v1/settings', {
    data: {
      personal_categories: [
        'Groceries', 'Dining', 'Transportation', 'Home', 'Health',
        'Subscriptions', 'Shopping', 'Travel', 'Entertainment',
        'Personal Care', 'Gifts', 'Other', 'Transfer', 'Income', 'Reimbursement',
      ],
      hidden_pages: [],
    },
  })
})
