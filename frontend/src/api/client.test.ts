import { describe, expect, it, vi, afterEach } from 'vitest'
import { api } from './client'

type FetchResponse = {
  ok: boolean
  status: number
  statusText?: string
  json: () => Promise<unknown>
}

function mockFetch(response: FetchResponse) {
  const fn = vi.fn().mockResolvedValue(response as unknown as Response)
  vi.stubGlobal('fetch', fn)
  return fn
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api client request', () => {
  it('returns parsed JSON on a successful response', async () => {
    mockFetch({ ok: true, status: 200, json: async () => ({ value: 42 }) })
    await expect(api.get<{ value: number }>('/x')).resolves.toEqual({ value: 42 })
  })

  it('returns undefined for a 204 No Content response', async () => {
    // json() must not be called for 204; throw if it is.
    mockFetch({ ok: true, status: 204, json: async () => { throw new Error('should not parse') } })
    await expect(api.delete('/x')).resolves.toBeUndefined()
  })

  it('throws with the string detail message on error', async () => {
    mockFetch({ ok: false, status: 400, json: async () => ({ detail: 'Plain error text' }) })
    await expect(api.get('/x')).rejects.toThrow('Plain error text')
  })

  it('unwraps a structured detail object to detail.message (regression guard)', async () => {
    mockFetch({
      ok: false,
      status: 409,
      json: async () => ({ detail: { message: 'Category in use', in_use: { Dining: 3 } } }),
    })
    await expect(api.put('/x', {})).rejects.toThrow('Category in use')
  })

  it('falls back to "Request failed" when detail is an unusable object', async () => {
    mockFetch({ ok: false, status: 500, json: async () => ({ detail: { in_use: {} } }) })
    await expect(api.post('/x', {})).rejects.toThrow('Request failed')
  })

  it('falls back to statusText when the error body is not JSON', async () => {
    mockFetch({
      ok: false,
      status: 502,
      statusText: 'Bad Gateway',
      json: async () => { throw new Error('not json') },
    })
    await expect(api.get('/x')).rejects.toThrow('Bad Gateway')
  })

  it('sends form-encoded bodies via postForm', async () => {
    const fn = mockFetch({ ok: true, status: 200, json: async () => ({ ok: true }) })
    await api.postForm('/login', { username: 'u', password: 'p' })
    const [, options] = fn.mock.calls[0]
    expect(options.method).toBe('POST')
    expect(options.body).toBeInstanceOf(URLSearchParams)
    expect(String(options.body)).toContain('username=u')
    expect(options.headers['Content-Type']).toBe('application/x-www-form-urlencoded')
  })
})
