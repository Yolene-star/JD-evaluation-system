export function OperationCard({ action, result, onConfirm, busy }: { action: string; result: string; onConfirm?: () => void; busy?: boolean }) {
  return <article className="operation-card" aria-label="系统操作"><strong>{action}</strong><span>{result}</span>{onConfirm && <button className="primary-button" onClick={onConfirm} disabled={busy}>{busy ? '执行中…' : '确认执行'}</button>}</article>
}
