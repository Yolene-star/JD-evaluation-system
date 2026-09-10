const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) throw new ApiError(response.status, await response.text())
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function createRequestController(): AbortController { return new AbortController() }

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const form = new FormData()
  form.append('file', file)
  const response = await fetch(`${API_BASE}${path}`, { method: 'POST', body: form })
  if (!response.ok) throw new ApiError(response.status, await response.text())
  return response.json() as Promise<T>
}

export type HealthResponse = { status: 'ok' }

export const assessmentApi = {
  create: (projectId: string, modelVersionId?: string) => apiFetch(`/api/projects/${projectId}/assessments`, { method: 'POST', body: JSON.stringify(modelVersionId ? { model_version_id: modelVersionId } : {}) }),
  snapshot: <T>(sessionId: string) => apiFetch<unknown>(`/api/assessments/${sessionId}`).then(raw => mapAssessmentSnapshot(raw) as T),
  start: <T>(sessionId: string) => apiFetch<T>(`/api/assessments/${sessionId}/start`, { method: 'POST' }),
  submit: <T>(sessionId: string, content: string, idempotencyKey: string) => apiFetch<T>(`/api/assessments/${sessionId}/turns`, { method: 'POST', body: JSON.stringify({ content, idempotency_key: idempotencyKey }) }),
  pause: <T>(sessionId: string) => apiFetch<T>(`/api/assessments/${sessionId}/pause`, { method: 'POST' }),
  resume: <T>(sessionId: string) => apiFetch<T>(`/api/assessments/${sessionId}/resume`, { method: 'POST' }),
  finish: <T>(sessionId: string, reason = 'user_requested') => apiFetch<T>(`/api/assessments/${sessionId}/finish`, { method: 'POST', body: JSON.stringify({ reason, confirm: true }) }),
  retry: <T>(sessionId: string, idempotencyKey: string) => apiFetch<T>(`/api/assessments/${sessionId}/retry`, { method: 'POST', body: JSON.stringify({ idempotency_key: idempotencyKey }) }),
}

function mapAssessmentSnapshot(raw: any): any {
  if (!raw || typeof raw !== 'object') return raw
  const mapQuestion = (q: any) => q && ({ ...q, turnType: q.turnType ?? q.turn_type, coveredCompetencyIds: q.coveredCompetencyIds ?? q.covered_competency_ids ?? [], followUpTargetCompetencyId: q.followUpTargetCompetencyId ?? q.follow_up_target_competency_id })
  const status = raw.agentStatus ?? raw.agent_status
  const agentStatus = status ? { phase: status.phase, confirmedCompetencyIds: status.confirmedCompetencyIds ?? status.confirmed_competency_ids ?? [], activeCompetencyId: status.activeCompetencyId ?? status.active_competency_id, pendingEvidence: status.pendingEvidence ?? status.pending_evidence ?? [], reason: status.reason } : undefined
  return { ...raw, sessionId: raw.sessionId ?? raw.session_id, modelVersionId: raw.modelVersionId ?? raw.model_version_id, currentQuestion: mapQuestion(raw.currentQuestion ?? raw.current_question), competencies: (raw.competencies ?? []).map((c: any) => ({ ...c, competencyId: c.competencyId ?? c.competency_id, followUpCount: c.followUpCount ?? c.follow_up_count, evidenceSufficiency: c.evidenceSufficiency ?? c.evidence_sufficiency })), turns: (raw.turns ?? []).map((t: any) => ({ ...t, coveredCompetencyIds: t.coveredCompetencyIds ?? t.covered_competency_ids, turnType: t.turnType ?? t.turn_type })), agentStatus }
}
