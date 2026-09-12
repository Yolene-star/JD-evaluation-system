import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { QuestionBubble } from '../src/components/QuestionBubble'
import { EvidenceInlineCard } from '../src/components/EvidenceInlineCard'
import { AssessmentCompletionCard } from '../src/components/AssessmentCompletionCard'
import { AssessmentWorkbench } from '../src/components/AssessmentWorkbench'
import { AnswerComposer } from '../src/components/AnswerComposer'
import type { AssessmentSnapshot } from '../src/types/assessment'

const question = { id: 'q1', content: '请介绍一次系统设计经历。', turnType: 'MAIN_QUESTION' as const, coveredCompetencyIds: ['c1'] }

describe('stage two assessment UI contracts', () => {
  it('renders a single competency question without composite label', () => {
    const html = renderToStaticMarkup(<QuestionBubble question={question} competencyNames={{ c1: '系统设计' }} />)
    expect(html).toContain('系统设计')
    expect(html).not.toContain('综合题')
  })

  it('renders composite coverage and groups evidence by competency', () => {
    const html = renderToStaticMarkup(<>
      <QuestionBubble question={{ ...question, coveredCompetencyIds: ['c1', 'c2'] }} competencyNames={{ c1: '系统设计', c2: '问题分析' }} />
      <EvidenceInlineCard groups={[{ competencyId: 'c1', competencyName: '系统设计', sufficiency: 'SUFFICIENT', observations: ['拆分服务边界'] }, { competencyId: 'c2', competencyName: '问题分析', sufficiency: 'INSUFFICIENT', observations: ['缺少约束分析'] }]} />
    </>)
    expect(html).toContain('综合题')
    expect(html).toContain('覆盖 2 项能力')
    expect(html).toContain('系统设计')
    expect(html).toContain('问题分析')
    expect(html).toContain('证据充分')
    expect(html).toContain('证据不足')
  })

  it('shows completion type without formal scoring artifacts', () => {
    const html = renderToStaticMarkup(<AssessmentCompletionCard completion="PARTIAL" completedCount={1} totalCount={2} incompleteNames={['沟通表达']} />)
    expect(html).toContain('PARTIAL')
    expect(html).toContain('沟通表达')
    expect(html).not.toMatch(/score|radar|匹配度|雷达图|正式评分/i)
  })

  it('uses server snapshot progress and does not invent score fields', () => {
    const snapshot: AssessmentSnapshot = { sessionId: 's1', status: 'IN_PROGRESS', completion: 'NONE', modelVersionId: 'v1', competencies: [{ competencyId: 'c1', name: '系统设计', status: 'SUFFICIENT', followUpCount: 0, evidenceSufficiency: 'SUFFICIENT' }], turns: [], retryable: false }
    const html = renderToStaticMarkup(<AssessmentWorkbench snapshot={snapshot} />)
    expect(html).toContain('1 / 1')
    expect(html).not.toMatch(/score|radar|匹配度|雷达图|正式评分/i)
  })

  it('renders server-provided agent status with text labels', () => {
    const snapshot: AssessmentSnapshot = {
      sessionId: 's1',
      status: 'IN_PROGRESS',
      completion: 'NONE',
      modelVersionId: 'v1',
      competencies: [
        { competencyId: 'c1', name: '系统设计', status: 'SUFFICIENT', followUpCount: 0, evidenceSufficiency: 'SUFFICIENT' },
        { competencyId: 'c2', name: '问题分析', status: 'FOLLOW_UP', followUpCount: 1, evidenceSufficiency: 'INSUFFICIENT' },
      ],
      turns: [],
      retryable: false,
      agentStatus: {
        phase: 'FOLLOWING_UP',
        confirmedCompetencyIds: ['c1'],
        activeCompetencyId: 'c2',
        pendingEvidence: ['缺少工程结果'],
        reason: '当前能力仍缺少结果证据',
      },
    }

    const html = renderToStaticMarkup(<AssessmentWorkbench snapshot={snapshot} />)

    expect(html).toContain('AI 正在评估')
    expect(html).toContain('系统设计已确认')
    expect(html).toContain('正在验证问题分析')
    expect(html).toContain('等待补充：缺少工程结果')
    expect(html).toContain('当前能力仍缺少结果证据')
    expect(html).not.toMatch(/score|radar|匹配度|雷达图|正式评分/i)
  })

  it('keeps old snapshots usable without an agent status panel', () => {
    const snapshot: AssessmentSnapshot = { sessionId: 's1', status: 'IN_PROGRESS', completion: 'NONE', modelVersionId: 'v1', competencies: [], turns: [], retryable: false }
    const html = renderToStaticMarkup(<AssessmentWorkbench snapshot={snapshot} />)
    expect(html).not.toContain('AI 正在评估')
  })

  it('offers supportive answer helpers without submitting a response', () => {
    const html = renderToStaticMarkup(<AnswerComposer onSubmit={() => undefined} />)
    expect(html).toContain('提示一下')
    expect(html).toContain('换个说法')
    expect(html).not.toContain('卡住了也没关系')
  })
})
