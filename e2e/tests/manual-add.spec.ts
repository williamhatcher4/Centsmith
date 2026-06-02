import { expect, test } from '@playwright/test'
import { login } from './helpers'

// Adds a transaction by hand via the ?action=add modal and confirms it shows up
// in the Transactions list. Cleans the row up afterward so the shared e2e DB
// stays stable for other specs.
const PROBE = 'Manual Add Probe Zeta'

test('add a transaction manually and see it in the list', async ({ page }) => {
  await login(page)

  // ?action=add opens the Add transaction modal on load.
  await page.goto('/transactions?action=add')
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('Add transaction')).toBeVisible()

  await dialog.getByLabel('Description').fill(PROBE)
  await dialog.getByLabel('Amount ($)').fill('12.34')
  await dialog.getByRole('button', { name: /^save$/i }).click()

  await expect(page.getByText(/transaction added/i)).toBeVisible({ timeout: 5_000 })

  // The new debit row appears in the default (debits) Transactions list.
  const row = page.locator('tbody tr').filter({ hasText: PROBE })
  await expect(row).toBeVisible()
  await expect(row).toContainText('12.34')

  // Cleanup: delete the probe row via the API so other specs are unaffected.
  const list = await page.request.get('/api/v1/transactions?limit=1000')
  const rows = (await list.json()) as Array<{ id: number; description: string }>
  const probe = rows.find((r) => r.description === PROBE)
  if (probe) await page.request.delete(`/api/v1/transactions/${probe.id}`)
})
