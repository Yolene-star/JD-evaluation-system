import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ReportChat } from './ReportChat'

describe('ReportChat', () => {
  it('renders a bottom anchor for keeping the latest message in view', () => {
    const html = renderToStaticMarkup(<ReportChat reportId="r1" messages={[{ id: 'm1', role: 'agent', content: '回答' }]} onSend={() => undefined} />)
    expect(html).toContain('aria-hidden="true"')
  })
})
