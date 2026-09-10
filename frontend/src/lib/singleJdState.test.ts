import { describe, expect, it } from 'vitest'
import { getSingleJdEmptyState } from './singleJdState'

describe('getSingleJdEmptyState', () => {
  it('explains a completed parse that produced no competencies', () => {
    expect(getSingleJdEmptyState('COMPLETED')).toEqual({
      title: '解析已完成，但未识别到能力项',
      detail: '请使用 AI 重新解析或手动补充能力。',
    })
  })

  it('keeps the pending message before parsing completes', () => {
    expect(getSingleJdEmptyState('RECEIVED')).toEqual({
      title: '尚未生成解析结果',
      detail: '运行解析后查看这份 JD 的独立模型。',
    })
  })
})
