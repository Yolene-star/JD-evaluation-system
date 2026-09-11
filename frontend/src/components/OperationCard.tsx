const ACTION_LABELS: Record<string, string> = {
  DELETE_PROJECT: '归档项目',
  REMOVE_JD: '移出 JD',
  DELETE_COMPETENCY: '删除能力项',
  UPDATE_COMPETENCY_WEIGHT: '修改能力权重',
  CONFIRM_MODEL: '确认并冻结模型',
}

export function operationActionLabel(action: string): string {
  return ACTION_LABELS[action] ?? '更新项目数据'
}

export function OperationCard({ action, result, onConfirm, busy }: { action: string; result: string; onConfirm?: () => void; busy?: boolean }) {
  return <article className="operation-card" aria-label="系统操作"><strong>{operationActionLabel(action)}</strong><span>{result}</span>{onConfirm && <button className="primary-button" onClick={onConfirm} disabled={busy}>{busy ? '执行中…' : '确认执行'}</button>}</article>
}
