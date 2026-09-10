import { describe, expect, it } from 'vitest'
import { buildChatPayload, createPendingOperation } from './chat'

describe('chat command confirmation', () => {
  it('confirms with the original preview message after the composer is cleared', () => {
    const pending = createPendingOperation({ action: 'REMOVE_JD', requires_confirmation: true }, '移除《产品经理 JD》')

    expect(buildChatPayload('', true, pending)).toEqual({
      message: '移除《产品经理 JD》',
      confirm: true,
    })
  })
})
