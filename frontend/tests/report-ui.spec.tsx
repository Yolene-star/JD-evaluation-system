import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { ReportView } from '../src/components/ReportView'
import type { AssessmentReport } from '../src/types/report'

const report: AssessmentReport = { id: 'r1', assessmentSessionId: 's1', reportVersion: 1, evidencePackageId: 'ep1', modelVersionId: 'm1', rubricSetId: 'rb1', scoringRuleVersion: 'stage3-v1', completion: 'PARTIAL', evaluatedWeight: .5, unevaluatedWeight: .5, matchScore: 72, matchScoreType: 'PARTIAL', status: 'READY', narrativeStatus: 'PENDING_RETRY', evaluations: [{ competencyId: 'c1', name: '系统设计', status: 'SCORED', score: 7, attainment: .7, level: '7-8', rationale: '有证据' }, { competencyId: 'c2', name: '沟通', status: 'INCOMPLETE', score: null, attainment: null, rationale: '暂不可完全评价' }] }

describe('stage three report UI contracts', () => {
  it('labels partial coverage and never renders incomplete as zero', () => {
    const html = renderToStaticMarkup(<ReportView report={report} />)
    expect(html).toContain('PARTIAL')
    expect(html).toContain('不可完全评价')
    expect(html).not.toMatch(/沟通[^<]*0/)
  })

  it('visualizes the role model, aggregate score, and user profile with accessible text', () => {
    const html = renderToStaticMarkup(<ReportView report={{ ...report, narrative: { overview: { text: '偏实践型画像' }, strengths: [{ text: '系统拆解', evidenceIds: ['e1'] }], weaknesses: [{ text: '沟通表达' }], recommendations: [{ text: '补充跨团队案例' }] } }} />)
    expect(html).toContain('岗位能力模型')
    expect(html).toContain('综合评分')
    expect(html).toContain('用户画像')
    expect(html).toContain('系统设计')
    expect(html).toContain('偏实践型画像')
    expect(html).toContain('role="img"')
    expect(html).toContain('能力模型数据表')
  })
})
