import { describe, expect, it } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../test/server'
import { mockImportBatches } from '../test/handlers'
import { renderWithProviders } from '../test/renderWithProviders'
import { ExportsPage } from './ExportsPage'

describe('ExportsPage', () => {
  it('renders download links pointing at the backend export endpoints', () => {
    renderWithProviders(<ExportsPage />)

    const personal = screen.getByRole('link', { name: /personal csv/i })
    expect(personal).toHaveAttribute('href', '/api/v1/transactions/export/personal')

    const work = screen.getByRole('link', { name: /work csv/i })
    expect(work).toHaveAttribute('href', '/api/v1/transactions/export/work')
  })

  describe('Past imports section', () => {
    it('shows the list of past imports newest-first', async () => {
      renderWithProviders(<ExportsPage />)
      expect(await screen.findByText('may-statement.csv')).toBeInTheDocument()
      expect(screen.getByText('april-statement.csv')).toBeInTheDocument()
    })

    it('shows the empty state when no imports exist', async () => {
      server.use(http.get('/api/v1/imports', () => HttpResponse.json([])))
      renderWithProviders(<ExportsPage />)
      expect(await screen.findByText(/No imports yet/i)).toBeInTheDocument()
    })

    it('shows a confirm dialog before deleting and calls the API on confirm', async () => {
      let deletedId: string | null = null
      server.use(
        http.delete('/api/v1/imports/:id', ({ params }) => {
          deletedId = String(params.id)
          return HttpResponse.json({ removed_rows: 12, classified_rows: 3, categorized_rows: 1 })
        }),
      )
      const user = userEvent.setup()
      renderWithProviders(<ExportsPage />)
      await screen.findByText('may-statement.csv')

      await user.click(screen.getByRole('button', { name: /undo import may-statement\.csv/i }))
      const dialog = await screen.findByRole('dialog')
      expect(dialog).toHaveTextContent(/Undo this import\?/i)
      expect(dialog).toHaveTextContent(/may-statement\.csv/)

      await user.click(within(dialog).getByRole('button', { name: /undo import/i }))

      await waitFor(() => expect(deletedId).toBe('batch-1'))
    })

    it('does not call the API when the user cancels the confirm dialog', async () => {
      let called = false
      server.use(
        http.delete('/api/v1/imports/:id', () => {
          called = true
          return HttpResponse.json({ removed_rows: 0, classified_rows: 0, categorized_rows: 0 })
        }),
      )
      const user = userEvent.setup()
      renderWithProviders(<ExportsPage />)
      await screen.findByText('may-statement.csv')

      await user.click(screen.getByRole('button', { name: /undo import may-statement\.csv/i }))
      await screen.findByRole('dialog')
      await user.click(screen.getByRole('button', { name: /cancel/i }))

      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
      expect(called).toBe(false)
    })

    it('displays the row count for each batch', async () => {
      renderWithProviders(<ExportsPage />)
      await screen.findByText('may-statement.csv')
      // mockImportBatches[0].row_count = 12, mockImportBatches[1].row_count = 8
      expect(screen.getByText(String(mockImportBatches[0].row_count))).toBeInTheDocument()
      expect(screen.getByText(String(mockImportBatches[1].row_count))).toBeInTheDocument()
    })
  })
})
