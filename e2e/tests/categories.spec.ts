import { expect, test } from '@playwright/test'
import { login } from './helpers'

// Exercises the custom-category lifecycle in Settings: add a category, seed a
// transaction in it, rename it (rows follow), then delete it with relabel (rows
// move to the target). Verifies the row's category via the API at each step and
// cleans up the seeded transaction so the shared e2e DB stays stable.
const ORIGINAL = 'E2E Cat Original'
const RENAMED = 'E2E Cat Renamed'
const PROBE = 'E2E Category Probe Row'

const BASELINE_CATEGORIES = [
  'Groceries', 'Dining', 'Transportation', 'Home', 'Health',
  'Subscriptions', 'Shopping', 'Travel', 'Entertainment',
  'Personal Care', 'Gifts', 'Other', 'Transfer', 'Income', 'Reimbursement',
]

async function probeCategory(page: import('@playwright/test').Page): Promise<string | null> {
  const res = await page.request.get('/api/v1/transactions?classification=personal&limit=1000')
  const rows = (await res.json()) as Array<{ description: string; personal_category: string | null }>
  return rows.find((r) => r.description === PROBE)?.personal_category ?? null
}

test('rename and relabel a custom category and the rows follow', async ({ page }) => {
  await login(page)
  await page.goto('/settings')

  // Start from a known baseline category list.
  await page.request.put('/api/v1/settings', {
    data: { personal_categories: BASELINE_CATEGORIES, hidden_pages: [] },
  })
  await page.reload()

  // Add the custom category via the UI.
  await page.getByLabel('New category name').fill(ORIGINAL)
  await page.getByRole('button', { name: /^add$/i }).click()
  await expect(page.getByText(`Added "${ORIGINAL}"`)).toBeVisible({ timeout: 5_000 })

  // Seed a personal transaction in the new category, then reload so usage loads.
  await page.request.post('/api/v1/transactions/manual', {
    data: {
      transaction_date: '2026-07-10',
      description: PROBE,
      amount_cents: 4321,
      transaction_type: 'debit',
      classification: 'personal',
      personal_category: ORIGINAL,
    },
  })
  expect(await probeCategory(page)).toBe(ORIGINAL)
  await page.reload()

  // Rename ORIGINAL -> RENAMED; the seeded row should follow.
  await page.getByRole('button', { name: `Rename ${ORIGINAL}`, exact: true }).click()
  await page.getByRole('textbox', { name: `Rename ${ORIGINAL}`, exact: true }).fill(RENAMED)
  await page.getByRole('button', { name: `Save ${ORIGINAL}`, exact: true }).click()
  await expect(page.getByText(`Renamed to "${RENAMED}"`)).toBeVisible({ timeout: 5_000 })
  await expect.poll(() => probeCategory(page)).toBe(RENAMED)

  // Delete RENAMED with relabel to Other; the seeded row should move to Other.
  await page.getByRole('button', { name: `Delete ${RENAMED}`, exact: true }).click()
  const dialog = page.getByRole('dialog').filter({ hasText: 'Delete' })
  await dialog.getByLabel('Relabel to').selectOption('Other')
  await dialog.getByRole('button', { name: /^delete$/i }).click()
  await expect(page.getByText(`Deleted "${RENAMED}"`)).toBeVisible({ timeout: 5_000 })
  await expect.poll(() => probeCategory(page)).toBe('Other')

  // Cleanup: delete the seeded row and restore baseline categories.
  const res = await page.request.get('/api/v1/transactions?classification=personal&limit=1000')
  const rows = (await res.json()) as Array<{ id: number; description: string }>
  const probe = rows.find((r) => r.description === PROBE)
  if (probe) await page.request.delete(`/api/v1/transactions/${probe.id}`)
  await page.request.put('/api/v1/settings', {
    data: { personal_categories: BASELINE_CATEGORIES, hidden_pages: [] },
  })
})
