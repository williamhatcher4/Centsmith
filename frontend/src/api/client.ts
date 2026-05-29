async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...options,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...options.headers },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = err.detail
    const message =
      typeof detail === 'string'
        ? detail
        : detail && typeof detail === 'object' && typeof detail.message === 'string'
          ? detail.message
          : 'Request failed'
    throw new Error(message)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) => request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  postForm: <T>(path: string, data: Record<string, string>) => request<T>(path, {
    method: 'POST',
    body: new URLSearchParams(data),
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  }),
  put: <T>(path: string, body: unknown) => request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}
