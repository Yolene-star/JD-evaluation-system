import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { AnswerComposer } from './AnswerComposer'

describe('AnswerComposer', () => {
  it('keeps helper guidance inside the composer conversation area', () => {
    const html = renderToStaticMarkup(<AnswerComposer question="请介绍一个项目" onSubmit={() => undefined} />)

    expect(html).toContain('assessment-helper-messages')
    expect(html).toContain('assessment-helper-actions')
  })
})
