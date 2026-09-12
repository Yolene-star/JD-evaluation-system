import { describe, expect, it } from 'vitest'
import { formatSystemNotice } from './systemNotice'

describe('system notice formatting', () => {
  it('shows a readable JD title without raw ids or JSON', () => {
    const content = formatSystemNotice('JD_ADDED', JSON.stringify({ jd_id: 'long-secret-id', title: '前端工程师 JD', source: 'link' }))
    expect(content).toBe('已添加 JD：前端工程师 JD')
    expect(content).not.toContain('long-secret-id')
    expect(content).not.toContain('{')
  })

  it('describes the selected link extractor in Chinese', () => {
    expect(formatSystemNotice('JD_EXTRACTOR_SELECTED', JSON.stringify({ adapter: 'boss-zhipin' }))).toBe('已识别网页提取模块：Boss 直聘')
  })

  it('describes conversational model mutations without exposing JSON', () => {
    expect(formatSystemNotice('JD_REMOVED', JSON.stringify({ jd_id: 'hidden', title: '前端 JD' }))).toBe('已将 JD 移出当前模型：前端 JD')
    expect(formatSystemNotice('COMPETENCY_WEIGHT_UPDATED', JSON.stringify({ name: '组件化开发', weight: 0.25 }))).toBe('已更新能力权重：组件化开发')
  })
})
