import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../test/server'
import { renderWithProviders } from '../test/renderWithProviders'
import { ImportModal } from './ImportModal'

function buildCsvFile(): File {
  const csv = '2026-05-01,Coffee,4.25,\n'
  return new File([csv], 'statement.csv', { type: 'text/csv' })
}

const PREVIEW_PAYLOAD = {
  rows: [
    {
      row_number: 1,
      date: '2026-05-01',
      description: 'Coffee',
      amount_cents: 425,
      transaction_type: 'debit',
      is_duplicate: false,
    },
  ],
  total: 1,
  duplicates: 0,
  ignored_credits: 0,
  to_import: 1,
  statement_format: 'Account Activity CSV',
  skipped_errors: 0,
  amount_sign_adjustable: false,
  charges_positive: false,
  skipped_rows: [],
  mapping_required: false,
  available_columns: [],
  sample_rows: [],
  detected_columns: {},
}

describe('ImportModal Phase 2 undo flow', () => {
  it('lists every accepted import extension in the drop-zone copy', () => {
    renderWithProviders(<ImportModal onClose={vi.fn()} mode="card" />)

    expect(screen.getByText(/CSV \/ XLS \/ XLSX \/ OFX \/ QFX/i)).toBeInTheDocument()
  })

  it('advertises OFX/QFX MIME types so the file picker does not grey them out', () => {
    renderWithProviders(<ImportModal onClose={vi.fn()} mode="card" />)

    const input = document.querySelector('input[type="file"]')
    const accept = input?.getAttribute('accept') ?? ''
    expect(accept).toContain('.ofx')
    expect(accept).toContain('.qfx')
    expect(accept).toContain('application/x-ofx')
    expect(accept).toContain('application/vnd.intu.qfx')
  })

  it('shows an Undo toast after a successful import that includes a batch_id', async () => {
    server.use(
      http.post('/api/v1/transactions/import/preview', () => HttpResponse.json(PREVIEW_PAYLOAD)),
      http.post('/api/v1/transactions/import/confirm', () =>
        HttpResponse.json({
          imported: 1,
          skipped: 0,
          ignored_credits: 0,
          skipped_errors: 0,
          batch_id: 'new-batch-id',
        }),
      ),
    )

    const user = userEvent.setup()
    renderWithProviders(<ImportModal onClose={vi.fn()} mode="card" />)

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    expect(fileInput).toBeTruthy()
    await user.upload(fileInput, buildCsvFile())

    await screen.findByText(/To import/i)
    await user.click(screen.getByRole('button', { name: /Import 1/i }))

    await screen.findByText(/1 transactions imported/i)
    expect(await screen.findByRole('button', { name: /undo/i })).toBeInTheDocument()
  })

  it('calls DELETE /imports/:id when the Undo button is clicked', async () => {
    let deletedId: string | null = null
    server.use(
      http.post('/api/v1/transactions/import/preview', () => HttpResponse.json(PREVIEW_PAYLOAD)),
      http.post('/api/v1/transactions/import/confirm', () =>
        HttpResponse.json({
          imported: 1,
          skipped: 0,
          ignored_credits: 0,
          skipped_errors: 0,
          batch_id: 'undo-me',
        }),
      ),
      http.delete('/api/v1/imports/:id', ({ params }) => {
        deletedId = String(params.id)
        return HttpResponse.json({ removed_rows: 1, classified_rows: 0, categorized_rows: 0 })
      }),
    )

    const user = userEvent.setup()
    renderWithProviders(<ImportModal onClose={vi.fn()} mode="card" />)

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(fileInput, buildCsvFile())
    await screen.findByText(/To import/i)
    await user.click(screen.getByRole('button', { name: /Import 1/i }))

    const undoButton = await screen.findByRole('button', { name: /undo/i })
    await user.click(undoButton)

    await waitFor(() => expect(deletedId).toBe('undo-me'))
  })

  it('shows ignored credit rows in the preview with a "credit ignored" badge', async () => {
    server.use(
      http.post('/api/v1/transactions/import/preview', () =>
        HttpResponse.json({
          ...PREVIEW_PAYLOAD,
          rows: [
            { row_number: 1, date: '2026-05-01', description: 'Coffee', amount_cents: 425, transaction_type: 'debit', is_duplicate: false, is_ignored_credit: false },
            { row_number: 2, date: '2026-05-02', description: 'PAYMENT - THANK YOU', amount_cents: 10000, transaction_type: 'credit', is_duplicate: false, is_ignored_credit: true },
          ],
          total: 2,
          ignored_credits: 1,
          to_import: 1,
        }),
      ),
    )

    const user = userEvent.setup()
    renderWithProviders(<ImportModal onClose={vi.fn()} mode="card" />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(fileInput, buildCsvFile())

    await screen.findByText(/To import/i)
    expect(screen.getByText('PAYMENT - THANK YOU')).toBeInTheDocument()
    expect(screen.getByText(/credit ignored/i)).toBeInTheDocument()
  })

  it('does not show an Undo toast when the import imported zero rows', async () => {
    server.use(
      http.post('/api/v1/transactions/import/preview', () => HttpResponse.json(PREVIEW_PAYLOAD)),
      http.post('/api/v1/transactions/import/confirm', () =>
        HttpResponse.json({
          imported: 0,
          skipped: 1,
          ignored_credits: 0,
          skipped_errors: 0,
          batch_id: null,
        }),
      ),
    )

    const user = userEvent.setup()
    renderWithProviders(<ImportModal onClose={vi.fn()} mode="card" />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(fileInput, buildCsvFile())
    await screen.findByText(/To import/i)
    await user.click(screen.getByRole('button', { name: /Import 1/i }))

    await screen.findByText(/0 transactions imported/i)
    expect(screen.queryByRole('button', { name: /undo/i })).not.toBeInTheDocument()
  })
})

describe('ImportModal charges-positive sign toggle', () => {
  const adjustablePayload = {
    ...PREVIEW_PAYLOAD,
    amount_sign_adjustable: true,
    charges_positive: true,
  }

  it('hides the sign toggle when the file is not adjustable', async () => {
    server.use(
      http.post('/api/v1/transactions/import/preview', () => HttpResponse.json(PREVIEW_PAYLOAD)),
    )
    const user = userEvent.setup()
    renderWithProviders(<ImportModal onClose={vi.fn()} mode="card" />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(fileInput, buildCsvFile())
    await screen.findByText(/To import/i)
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })

  // Reading request.formData() is flaky for multipart bodies under jsdom, so we
  // assert against the raw multipart body text instead.
  function readChargesPositive(body: string): string | null {
    const match = body.match(/name="charges_positive"[\r\n]+([^\r\n]+)/)
    return match ? match[1].trim() : null
  }

  it('shows the toggle and re-previews with the chosen sign when flipped', async () => {
    let lastChargesPositive: string | null = 'unset'
    server.use(
      http.post('/api/v1/transactions/import/preview', async ({ request }) => {
        const cp = readChargesPositive(await request.text())
        lastChargesPositive = cp
        const chargesPositive = cp === null ? true : cp === 'true'
        return HttpResponse.json({
          ...adjustablePayload,
          charges_positive: chargesPositive,
          rows: [{ ...PREVIEW_PAYLOAD.rows[0], transaction_type: chargesPositive ? 'debit' : 'credit' }],
        })
      }),
    )

    const user = userEvent.setup()
    renderWithProviders(<ImportModal onClose={vi.fn()} mode="card" />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(fileInput, buildCsvFile())
    await screen.findByText(/To import/i)

    const checkbox = screen.getByRole('checkbox') as HTMLInputElement
    expect(checkbox.checked).toBe(true)

    await user.click(checkbox)
    await waitFor(() => expect(lastChargesPositive).toBe('false'))
  })

  it('sends the chosen sign convention to confirm', async () => {
    let confirmChargesPositive: string | null = 'unset'
    server.use(
      http.post('/api/v1/transactions/import/preview', () => HttpResponse.json(adjustablePayload)),
      http.post('/api/v1/transactions/import/confirm', async ({ request }) => {
        confirmChargesPositive = readChargesPositive(await request.text())
        return HttpResponse.json({
          imported: 1,
          skipped: 0,
          ignored_credits: 0,
          skipped_errors: 0,
          batch_id: 'batch-1',
        })
      }),
    )

    const user = userEvent.setup()
    renderWithProviders(<ImportModal onClose={vi.fn()} mode="card" />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(fileInput, buildCsvFile())
    await screen.findByText(/To import/i)
    // The auto-detected convention must be reflected before confirming.
    expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(true)
    await user.click(screen.getByRole('button', { name: /Import 1/i }))

    await waitFor(() => expect(confirmChargesPositive).toBe('true'))
  })
})

describe('ImportModal column mapping fallback', () => {
  const mappingRequiredPayload = {
    ...PREVIEW_PAYLOAD,
    rows: [],
    total: 0,
    to_import: 0,
    statement_format: 'Generic CSV',
    mapping_required: true,
    available_columns: ['Col A', 'Col B', 'Col C'],
    sample_rows: [['2026-05-01', 'Coffee', '-4.25']],
    detected_columns: { date: null, description: null, amount: null, debit: null, credit: null },
  }

  function readColumnMapping(body: string): string | null {
    const match = body.match(/name="column_mapping"[\r\n]+([^\r\n]+)/)
    return match ? match[1].trim() : null
  }

  it('shows the mapping step when auto-detection fails, then previews with the chosen mapping', async () => {
    let sentMapping: string | null = null
    server.use(
      http.post('/api/v1/transactions/import/preview', async ({ request }) => {
        const mapping = readColumnMapping(await request.text())
        if (!mapping) return HttpResponse.json(mappingRequiredPayload)
        sentMapping = mapping
        return HttpResponse.json({ ...PREVIEW_PAYLOAD, statement_format: 'Generic CSV' })
      }),
    )

    const user = userEvent.setup()
    renderWithProviders(<ImportModal onClose={vi.fn()} mode="card" />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(fileInput, buildCsvFile())

    // Mapping step appears with the file's columns to assign.
    await screen.findByText(/Map your columns/i)
    expect(screen.getByLabelText('Date column')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Preview with this mapping/i }))

    await screen.findByText(/To import/i)
    await waitFor(() => expect(sentMapping).toBeTruthy())
    expect(JSON.parse(sentMapping!)).toHaveProperty('date_column')
  })

  it('renders per-row skip reasons in the preview', async () => {
    server.use(
      http.post('/api/v1/transactions/import/preview', () =>
        HttpResponse.json({
          ...PREVIEW_PAYLOAD,
          skipped_errors: 1,
          skipped_rows: [
            { row_number: 7, raw_date: 'not-a-date', raw_amount: '9.99', raw_description: 'Bad row', reason_code: 'unparseable_date', message: 'Could not read the date in this row.' },
          ],
        }),
      ),
    )
    const user = userEvent.setup()
    renderWithProviders(<ImportModal onClose={vi.fn()} mode="card" />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(fileInput, buildCsvFile())
    await screen.findByText(/To import/i)

    expect(screen.getByText(/1 row skipped/i)).toBeInTheDocument()
    expect(screen.getByText(/Could not read the date in this row/i)).toBeInTheDocument()
  })
})
