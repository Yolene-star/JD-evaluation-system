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

  it('maps backend agent status fields into the assessment snapshot', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      session_id: 'session-1',
      model_version_id: 'model-1',
      competencies: [],
      turns: [],
      agent_status: {
        phase: 'FOLLOWING_UP',
        confirmed_competency_ids: ['c-1'],
        active_competency_id: 'c-2',
        pending_evidence: ['缺少结果'],
        reason: '需要追问',
      },
    }), { status: 200 })))

    const snapshot = await assessmentApi.snapshot<any>('session-1')

    expect(snapshot.agentStatus).toEqual({
      phase: 'FOLLOWING_UP',
      confirmedCompetencyIds: ['c-1'],
      activeCompetencyId: 'c-2',
      pendingEvidence: ['缺少结果'],
      reason: '需要追问',
    })
    vi.unstubAllGlobals()
  })
})
