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
