import { describe, expect, it } from 'vitest'
import { parseMarkdown } from './markdown'

describe('markdown parser', () => {
  it('keeps headings, emphasis and ordered lists as structured blocks', () => {
    expect(parseMarkdown('## 结论\n\n请 **确认**：\n1. 添加 JD\n2. 运行解析')).toEqual([
      { type: 'heading', level: 2, text: '结论' },
      { type: 'paragraph', text: '请 **确认**：' },
      { type: 'ordered-list', items: ['添加 JD', '运行解析'] },
    ])
  })
})
