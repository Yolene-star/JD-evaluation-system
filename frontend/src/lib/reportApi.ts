import { apiFetch } from './api'
import type { AssessmentReport } from '../types/report'

export function mapReport(raw: any): AssessmentReport {
  return { ...raw, assessmentSessionId: raw.assessmentSessionId ?? raw.assessment_session_id, reportVersion: raw.reportVersion ?? raw.report_version, evidencePackageId: raw.evidencePackageId ?? raw.evidence_package_id, modelVersionId: raw.modelVersionId ?? raw.model_version_id, rubricSetId: raw.rubricSetId ?? raw.rubric_set_id, scoringRuleVersion: raw.scoringRuleVersion ?? raw.scoring_rule_version, evaluatedWeight: raw.evaluatedWeight ?? raw.evaluated_weight, unevaluatedWeight: raw.unevaluatedWeight ?? raw.unevaluated_weight, matchScore: raw.matchScore ?? raw.match_score, matchScoreType: raw.matchScoreType ?? raw.match_score_type, narrativeStatus: raw.narrativeStatus ?? raw.narrative_status, candidateBackground: raw.candidateBackground ?? raw.candidate_background ?? null, evaluations: (raw.evaluations ?? []).map((item: any) => ({ ...item, competencyId: item.competencyId ?? item.competency_id, evidenceIds: item.evidenceIds ?? item.evidence_ids, evidence: (item.evidence ?? []).map((evidence: any) => ({ ...evidence, turnId: evidence.turnId ?? evidence.turn_id })), matchedIndicatorIds: item.matchedIndicatorIds ?? item.matched_indicator_ids, negativeEvidenceIds: item.negativeEvidenceIds ?? item.negative_evidence_ids, missingIndicatorIds: item.missingIndicatorIds ?? item.missing_indicator_ids })) }
}

export const reportApi = {
  list: (sessionId: string) => apiFetch<any[]>(`/api/assessment-sessions/${sessionId}/reports`).then(rows => rows.map(mapReport)),
  get: (reportId: string) => apiFetch<any>(`/api/reports/${reportId}`).then(mapReport),
  generate: (sessionId: string, input: { evidence_package_id?: string; rubric_set_id?: string; idempotency_key: string }) => apiFetch<any>(`/api/assessment-sessions/${sessionId}/reports`, { method: 'POST', body: JSON.stringify(input) }).then(mapReport),
  retryNarrative: (reportId: string) => apiFetch<any>(`/api/reports/${reportId}/narrative/retry`, { method: 'POST' }).then(mapReport),
  policy: (reportId: string) => apiFetch<AssessmentReport['scoringPolicy']>(`/api/reports/${reportId}/scoring-policy`),
  chatHistory: (reportId: string) => apiFetch<any[]>(`/api/reports/${reportId}/chat/messages`).then(rows => rows.map(item => ({ ...item, reportId: item.report_id, citedEvidenceIds: item.cited_evidence_ids ?? [], citedEvidence: item.cited_evidence ?? [] }))),
  ask: (reportId: string, content: string) => apiFetch<any>(`/api/reports/${reportId}/chat/messages`, { method: 'POST', body: JSON.stringify({ content }) }),
}
