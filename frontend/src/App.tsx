import { useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { authApi } from './api/auth'
import { useAppStore } from './store/useAppStore'
import { ThemeProvider } from './components/ui'
import { PrivateRoute } from './components/PrivateRoute'
import { AppShell } from './components/AppShell'
import { LoginPage } from './pages/LoginPage'
import { DashboardPage } from './pages/DashboardPage'
import { InboxPage } from './pages/InboxPage'
import { PersonalInboxPage } from './pages/PersonalInboxPage'
import { TransactionsPage } from './pages/TransactionsPage'
import { SpendingPage } from './pages/SpendingPage'
import { ExportsPage } from './pages/ExportsPage'

const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 30_000 } } })

function AuthLoader({ children }: { children: React.ReactNode }) {
  const setUser = useAppStore((s) => s.setUser)
  useEffect(() => {
    authApi.me().then(setUser).catch(() => {
      if (!useAppStore.getState().user) setUser(null)
    })
  }, [setUser])
  return <>{children}</>
}

export default function App() {
  return <ThemeProvider><QueryClientProvider client={qc}><BrowserRouter><AuthLoader><Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route element={<PrivateRoute><AppShell /></PrivateRoute>}>
      <Route index element={<DashboardPage />} />
      <Route path="inbox" element={<InboxPage />} />
      <Route path="personal-inbox" element={<PersonalInboxPage />} />
      <Route path="transactions" element={<TransactionsPage />} />
      <Route path="spending" element={<SpendingPage />} />
      <Route path="exports" element={<ExportsPage />} />
    </Route>
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></AuthLoader></BrowserRouter></QueryClientProvider></ThemeProvider>
}
