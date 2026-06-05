import { api } from './client'
import type { Card, CardPayload, StatementSummary } from '../types'

export interface StatementWindow {
  start_date: string
  end_date: string
}

export const cardsApi = {
  list: () => api.get<Card[]>('/api/v1/cards'),
  create: (payload: CardPayload) => api.post<Card>('/api/v1/cards', payload),
  update: (id: number, payload: CardPayload) => api.put<Card>(`/api/v1/cards/${id}`, payload),
  delete: (id: number) => api.delete<Card>(`/api/v1/cards/${id}`),
  statement: (cardId: number, window: StatementWindow) =>
    api.get<StatementSummary>(
      `/api/v1/cards/${cardId}/statement?start_date=${window.start_date}&end_date=${window.end_date}`,
    ),
}
