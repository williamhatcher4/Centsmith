import path from 'node:path'
import { expect, test, type Page } from '@playwright/test'
import { login } from './helpers'

// Statements/cards reconciliation end-to-end (plan item P4.5): create a card,
// import a fixture with the card selected, sum a statement window, reconcile a
// typed bank figure against net, then clean up (undo import + delete card) so
// the shared centsmith-e2e.db is left exactly as found.
//
// Descriptions are globally unique across e2e fixtures ("Stmt Probe …") per the
// shared-DB source_hash rule in AI-Context Current State → Known Issues. The
// window uses the custom date range (fixture dates are fixed; the generated
// billing cycles are relative to the real clock).
const fixture = path.resolve(__dirname, '..', 'fixtures', 'statement-cycle.csv')

const CARD_NAME = 'E2E Statement Card'

// StatCard root carries the `group` class; scope by its label to read a value.
function stat(page: Page, label: string) {
  return page.locator('div.group').filter({ has: page.getByText(label, { exact: true }) }).first()
}

test('card statement window sums and reconciles, then cleans up', async ({ page }) => {
  await login(page)

  // --- Create a card with a statement closing day -------------------------
  await page.goto('/statements')
  await page.getByRole('button', { name: /add card/i }).first().click()
  await page.getByLabel('Card name').fill(CARD_NAME)
  await page.getByLabel('Last 4 (optional)').fill('4242')
  await page.getByLabel('Statement closing day').fill('21')
  await page.getByRole('button', { name: /^save$/i }).click()
  await expect(page.getByText('Card added')).toBeVisible()
  // The name renders in both the card list and the statement-view subtitle.
  await expect(page.getByText(CARD_NAME).first()).toBeVisible()
  // The closing day produced automatic billing cycles.
  await expect(page.getByLabel('Billing cycle')).toBeVisible()

  // --- Import the fixture linked to the card ------------------------------
  await page.goto('/transactions')
  await page.getByRole('button', { name: /^import$/i }).click()
  // The card selector lives on the upload step — pick it before the file.
  await page.getByLabel('Assign to card (optional)').selectOption({ label: `${CARD_NAME} ····4242` })
  await page.setInputFiles('input[type="file"]', fixture)
  await expect(page.getByText(/import preview/i)).toBeVisible()
  const importButton = page.getByRole('button', { name: /Import 3/i })
  await expect(importButton).toBeEnabled()
  await importButton.click()
  await expect(page.getByText(/transactions imported/i)).toBeVisible()
  await page.getByRole('button', { name: /done/i }).click()

  // --- Pick the statement window and assert the sums ----------------------
  await page.goto('/statements')
  await expect(page.getByText(CARD_NAME).first()).toBeVisible()
  await page.getByLabel('Billing cycle').selectOption('custom')
  await page.getByLabel('Start date').fill('2026-08-01')
  await page.getByLabel('End date').fill('2026-08-31')

  // Charges 40.00 + 25.50, payments 30.00, net = charges − payments.
  await expect(stat(page, 'Charges')).toContainText('$65.50')
  await expect(stat(page, 'Charges')).toContainText('2 charges')
  await expect(stat(page, 'Payments / credits')).toContainText('$30.00')
  await expect(stat(page, 'Payments / credits')).toContainText('1 item')
  await expect(stat(page, 'Net this statement')).toContainText('$35.50')

  // All three fixture rows appear in the window drill-down.
  await expect(page.getByText('Stmt Probe Charge One')).toBeVisible()
  await expect(page.getByText('Stmt Probe Charge Two')).toBeVisible()
  await expect(page.getByText('Stmt Probe Payment')).toBeVisible()

  // --- Reconcile: matching figure → match badge; off figure → delta -------
  await page.getByLabel('Bank statement figure').fill('35.50')
  await expect(page.getByText(/Matches net \(\$35\.50\)/)).toBeVisible()
  await page.getByLabel('Bank statement figure').fill('40.00')
  await expect(page.getByText(/Off by \$4\.50 \(bank higher\)/)).toBeVisible()

  // --- Cleanup: undo the import so the shared DB keeps no fixture rows ----
  await page.goto('/exports')
  const undoRow = page.locator('tr').filter({ hasText: 'statement-cycle.csv' })
  await expect(undoRow).toBeVisible()
  await undoRow.getByRole('button', { name: /undo import statement-cycle\.csv/i }).click()
  await page.getByRole('button', { name: 'Undo import', exact: true }).click()
  await expect(page.getByText(/removed 3 transactions/i)).toBeVisible({ timeout: 5_000 })

  // --- Cleanup: delete the card -------------------------------------------
  await page.goto('/statements')
  await page.getByRole('button', { name: `Delete ${CARD_NAME}` }).click()
  await page.getByRole('button', { name: /^delete$/i }).click()
  await expect(page.getByText('Card deleted')).toBeVisible()
  await expect(page.getByText('No cards yet')).toBeVisible()

  // No residue: the fixture rows are gone from the ledger.
  await page.goto('/inbox')
  await expect(page.getByText('Stmt Probe Charge One')).toHaveCount(0)
  await expect(page.getByText('Stmt Probe Payment')).toHaveCount(0)
})
