import path from 'node:path'
import { expect, test, type Page } from '@playwright/test'
import { login } from './helpers'

// Import column-mapping end-to-end (plan item P5.6): the most cross-layer import
// path — unfamiliar headers -> mapping_required -> user maps columns -> preview
// -> save profile -> confirm. Has component + backend tests but no e2e until now.
//
// The fixture headers (When/What/How Much) match NO parser alias group, so
// mapping_required triggers. Descriptions are globally unique ("MapProbe …") per
// the shared-DB source_hash rule (AI-Context Current State → Known Issues).
// Cleanup undoes the batch and deletes the saved profile so the shared
// centsmith-e2e.db is left exactly as found (suite must pass twice in a row).
const fixture = path.resolve(__dirname, '..', 'fixtures', 'mapping-statement.csv')
const PROFILE_NAME = 'E2E Mapping Profile'

// Delete any leftover profile with our name (defensive: the create has a unique
// name constraint, so a residue from a failed run would otherwise block re-runs).
async function deleteProfileByName(page: Page, name: string) {
  const resp = await page.request.get('/api/v1/import-profiles')
  if (!resp.ok()) return
  const profiles = (await resp.json()) as Array<{ id: number; name: string }>
  for (const profile of profiles) {
    if (profile.name === name) {
      await page.request.delete(`/api/v1/import-profiles/${profile.id}`)
    }
  }
}

test('maps unfamiliar columns, saves a profile, imports, then cleans up', async ({ page }) => {
  await login(page)
  await deleteProfileByName(page, PROFILE_NAME)

  // --- Upload a file whose headers match no alias group -> mapping step ----
  await page.goto('/transactions')
  await page.getByRole('button', { name: /^import$/i }).click()
  await page.setInputFiles('input[type="file"]', fixture)

  await expect(page.getByText('Map your columns')).toBeVisible()
  // The mapping step renders the file's columns (headers + a sample row).
  await expect(page.getByRole('dialog').getByText('MapProbe Alpha')).toBeVisible()

  // --- Map date / description / amount, then preview ----------------------
  await page.getByLabel('Date column').selectOption({ label: 'When' })
  await page.getByLabel('Description column').selectOption({ label: 'What' })
  await page.getByLabel('Amount style').selectOption('single')
  await page.getByLabel('Amount column').selectOption({ label: 'How Much' })
  await page.getByLabel('Amount convention').selectOption('signed')
  await page.getByRole('button', { name: /preview with this mapping/i }).click()

  // --- Preview reflects the mapped rows -----------------------------------
  await expect(page.getByText(/import preview/i)).toBeVisible()
  await expect(page.getByRole('dialog').getByText('Generic CSV')).toBeVisible()
  await expect(page.getByRole('dialog').getByText('MapProbe Alpha')).toBeVisible()
  await expect(page.getByRole('dialog').getByText('MapProbe Gamma Refund')).toBeVisible()
  const importButton = page.getByRole('button', { name: /Import 3/i })
  await expect(importButton).toBeEnabled()

  // --- Save the layout as a named profile ---------------------------------
  await page.getByLabel('Save this layout as a profile').fill(PROFILE_NAME)
  await page.getByRole('button', { name: /save profile/i }).click()
  await expect(page.getByText(/import profile saved/i)).toBeVisible()

  // --- Confirm the import -------------------------------------------------
  await importButton.click()
  await expect(page.getByText(/transactions imported/i)).toBeVisible()
  await page.getByRole('button', { name: /done/i }).click()

  // --- The mapped rows landed in the ledger -------------------------------
  await page.goto('/inbox')
  await expect(page.getByText('MapProbe Alpha').first()).toBeVisible()
  await expect(page.getByText('MapProbe Beta').first()).toBeVisible()

  // --- Cleanup: undo the batch via the Past imports list ------------------
  await page.goto('/exports')
  const undoRow = page.locator('tr').filter({ hasText: 'mapping-statement.csv' })
  await expect(undoRow).toBeVisible()
  await undoRow.getByRole('button', { name: /undo import mapping-statement\.csv/i }).click()
  await page.getByRole('button', { name: 'Undo import', exact: true }).click()
  await expect(page.getByText(/removed 3 transactions/i)).toBeVisible({ timeout: 5_000 })

  // --- Cleanup: delete the saved profile ----------------------------------
  await deleteProfileByName(page, PROFILE_NAME)

  // No residue: the fixture rows are gone and the profile is deleted.
  await page.goto('/inbox')
  await expect(page.getByText('MapProbe Alpha')).toHaveCount(0)
  const profilesResp = await page.request.get('/api/v1/import-profiles')
  const remaining = (await profilesResp.json()) as Array<{ name: string }>
  expect(remaining.some((p) => p.name === PROFILE_NAME)).toBe(false)
})
