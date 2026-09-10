import { describe, expect, it } from 'vitest'
import { mapReport } from './reportApi'

describe('report API mapping', () => {
  it('keeps competency names and maps evidence excerpts for display', () => {
    const report = mapReport({
      assessment_session_id: 's1', report_version: 1, evidence_package_id: 'p1', model_version_id: 'm1', rubric_set_id: 'r1',
      scoring_rule_version: 'v1', evaluated_weight: 1, unevaluated_weight: 0, match_score: 80, match_score_type: 'FULL',
      evaluations: [{ competency_id: 'internal-id', name: '系统设计', evidence_ids: ['e1'], evidence: [{ id: 'e1', kind: 'POSITIVE', text: '已验证', excerpt: '回答原文', turn_id: 't1' }] }],
    })
    expect(report.evaluations[0].name).toBe('系统设计')
    expect(report.evaluations[0].evidence?.[0]).toMatchObject({ excerpt: '回答原文', turnId: 't1' })
  })
})
