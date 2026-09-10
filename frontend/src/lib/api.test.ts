import { describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch, assessmentApi } from './api'

describe('api client', () => {
  it('exposes HTTP status on failed requests', () => {
    const error = new ApiError(409, 'conflict')
    expect(error.status).toBe(409)
    expect(error.message).toBe('conflict')
  })

  it('passes an abort signal to fetch', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const controller = new AbortController()
    await apiFetch('/api/test', { signal: controller.signal })
    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal)
    vi.unstubAllGlobals()
  })

  it('accepts empty 204 responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
    await expect(apiFetch('/api/projects/demo', { method: 'DELETE' })).resolves.toBeUndefined()
    vi.unstubAllGlobals()
  })

  it('does not inject a browser LLM key; backend owns provider configuration', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await apiFetch('/api/test')
    expect(fetchMock.mock.calls[0][1].headers['X-LLM-API-Key']).toBeUndefined()
    vi.unstubAllGlobals()
  })

  it('confirms assessment finish requests for the guarded backend transition', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'PARTIALLY_FINISHED' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await assessmentApi.finish('session-1')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ reason: 'user_requested', confirm: true })
    vi.unstubAllGlobals()
  })
})
