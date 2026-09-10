export type PendingOperation = {
  action: string
  requires_confirmation?: boolean
  message: string
}

export type ChatPayload = {
  message: string
  confirm: boolean
}

export function createPendingOperation(
  operation: { action: string; requires_confirmation?: boolean } | undefined,
  message: string,
): PendingOperation | undefined {
  if (!operation) return undefined
  return { ...operation, message }
}

export function buildChatPayload(message: string, confirm = false, pendingOperation?: PendingOperation): ChatPayload | undefined {
  const sourceMessage = confirm ? pendingOperation?.message : message
  const trimmed = sourceMessage?.trim()
  if (!trimmed) return undefined
  return { message: trimmed, confirm }
}
