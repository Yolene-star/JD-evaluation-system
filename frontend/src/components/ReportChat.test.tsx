import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ReportChat } from './ReportChat'

describe('ReportChat', () => {
  it('renders markdown in agent replies as readable structure', () => {
    const html = renderToStaticMarkup(<ReportChat reportId="r1" messages={[{ id: 'm1', role: 'agent', content: '## 结论\n\n- 已完成\n- 待补充\n\n**重点**' }]} onSend={() => undefined} />)
    expect(html).toContain('<h4>')
    expect(html).toContain('结论')
    expect(html).toContain('<ul>')
    expect(html).toContain('<strong>重点</strong>')
  })

  it('renders a bottom anchor for keeping the latest message in view', () => {
    const html = renderToStaticMarkup(<ReportChat reportId="r1" messages={[{ id: 'm1', role: 'agent', content: '回答' }]} onSend={() => undefined} />)
    expect(html).toContain('aria-hidden="true"')
  })
})
