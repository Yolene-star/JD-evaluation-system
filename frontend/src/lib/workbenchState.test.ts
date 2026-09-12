import { describe, expect, it } from 'vitest'

import { shouldResetWorkbenchFeedback } from './workbenchState'


describe('workbench feedback reset', () => {
  it('keeps operation feedback during a same-project data refresh', () => {
    expect(shouldResetWorkbenchFeedback('project-1', 'project-1')).toBe(false)
    expect(shouldResetWorkbenchFeedback('project-1', 'project-2')).toBe(true)
  })
})
