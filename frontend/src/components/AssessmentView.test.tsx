import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { AssessmentSnapshot } from '../types/assessment'
import { AssessmentTimeline } from './AssessmentView'

describe('AssessmentTimeline', () => {
  it('keeps historical questions and renders the current follow-up once in chronological order', () => {
    const snapshot: AssessmentSnapshot = {
      sessionId: 'session-1',
      status: 'IN_PROGRESS',
      completion: 'NONE',
      modelVersionId: 'model-1',
      competencies: [{
        competencyId: 'python',
        name: 'Python 开发',
        status: 'FOLLOW_UP',
        followUpCount: 1,
        evidenceSufficiency: 'INSUFFICIENT',
      }],
      turns: [
        { id: 'question-1', role: 'SYSTEM', type: 'MAIN_QUESTION', content: '请介绍一个 Python 项目。', coveredCompetencyIds: ['python'] },
        { id: 'answer-1', role: 'USER', type: 'ANSWER', content: '我没有。' },
        { id: 'question-2', role: 'SYSTEM', type: 'FOLLOW_UP', content: '那请谈谈课程练习中的具体做法。', coveredCompetencyIds: ['python'] },
      ],
      currentQuestion: {
        id: 'question-2',
        content: '那请谈谈课程练习中的具体做法。',
        turnType: 'FOLLOW_UP',
        coveredCompetencyIds: ['python'],
        followUpTargetCompetencyId: 'python',
      },
      retryable: false,
    }

    const html = renderToStaticMarkup(<AssessmentTimeline snapshot={snapshot} competencyNames={{ python: 'Python 开发' }} />)

    expect(html).toContain('请介绍一个 Python 项目。')
    expect(html).toContain('我没有。')
    expect(html.match(/那请谈谈课程练习中的具体做法。/g)).toHaveLength(1)
    expect(html.indexOf('请介绍一个 Python 项目。')).toBeLessThan(html.indexOf('我没有。'))
    expect(html.indexOf('我没有。')).toBeLessThan(html.indexOf('那请谈谈课程练习中的具体做法。'))
  })
})
