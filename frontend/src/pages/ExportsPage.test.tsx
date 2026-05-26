import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
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
})
