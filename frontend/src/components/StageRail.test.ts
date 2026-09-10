import { describe, expect, it } from 'vitest'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { activeStage, StageRail } from './StageRail'
import { StageWorkbench } from './StageWorkbench'
describe('stage rail state mapping', () => { it('keeps model confirmation inside stage one', () => { expect(activeStage('REVIEWING')).toBe(1); expect(activeStage('CONFIRMED')).toBe(1) }) })

it('renders every stage as the shared navigation control', () => {
  const html = renderToStaticMarkup(StageRail({ currentStage: 2, availability: { 1: true, 2: true, 3: false }, onSelect: () => undefined }))
  expect(html).toContain('<button')
  expect(html).toContain('JD 分析')
  expect(html).not.toContain('模型确认')
  expect(html).toContain('模拟面试')
  expect(html).toContain('人才画像')
  expect(html).toContain('aria-current="step"')
})

it('does not duplicate the shared stage navigation inside stage one content', () => {
  const html = renderToStaticMarkup(createElement(StageWorkbench, { projectId: 'project-1' }))
  expect(html).not.toContain('aria-label="评估阶段"')
})
