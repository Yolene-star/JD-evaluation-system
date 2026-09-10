import { describe, expect, it } from 'vitest'
import { buildMaterialNotice } from './materialNotice'

describe('material notice', () => {
  it('describes the added material and next parsing action', () => {
    expect(buildMaterialNotice('前端工程师 JD')).toContain('已添加《前端工程师 JD》')
    expect(buildMaterialNotice('前端工程师 JD')).toContain('运行解析')
  })
})
