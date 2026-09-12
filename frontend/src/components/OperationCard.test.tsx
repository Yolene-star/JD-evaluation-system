import { describe, expect, it } from 'vitest'

import { operationActionLabel } from './OperationCard'


describe('OperationCard', () => {
  it('maps an internal tool name to a friendly Chinese label', () => {
    expect(operationActionLabel('UPDATE_COMPETENCY_WEIGHT')).toBe('修改能力权重')
    expect(operationActionLabel('UNKNOWN_INTERNAL_ACTION')).toBe('更新项目数据')
  })
})
