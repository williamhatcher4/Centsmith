import { create } from 'zustand'
import type { User } from '../types'

interface AppState {
  user: User | null
  authReady: boolean
  setUser: (user: User | null) => void
  setAuthReady: (authReady: boolean) => void
}

export const useAppStore = create<AppState>((set) => ({
  user: null,
  authReady: false,
  setUser: (user) => set({ user, authReady: true }),
  setAuthReady: (authReady) => set({ authReady }),
}))
