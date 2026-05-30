import type { ReactElement, ReactNode } from 'react'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider, ToastProvider, ConfirmDialogProvider } from '../components/ui'

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  })
}

export function renderWithProviders(ui: ReactElement, { route = '/' }: { route?: string } = {}) {
  const queryClient = makeQueryClient()
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ToastProvider>
          <ConfirmDialogProvider>
            <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
          </ConfirmDialogProvider>
        </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>
  )
  return { queryClient, ...render(ui, { wrapper }) }
}
