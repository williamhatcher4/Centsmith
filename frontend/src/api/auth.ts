import { api } from './client'
import type { User } from '../types'

export const authApi = {
  login: (username: string, password: string) => api.postForm<{ user: User }>('/api/v1/auth/login', { username, password }),
  logout: () => api.post<{ message: string }>('/api/v1/auth/logout', {}),
  me: () => api.get<User>('/api/v1/auth/me'),
}
