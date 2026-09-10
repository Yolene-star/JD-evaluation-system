export type Conflict = { type: string; names: string[]; blocking: boolean }

export function ConflictDecision({ conflicts, onResolve, disabled }: { conflicts: Conflict[]; onResolve: (index: number, decision: 'MERGE' | 'SEPARATE' | 'RENAME_MERGE') => void; disabled?: boolean }) {
  if (!conflicts.length) return <p className="muted">当前没有待处理冲突。</p>
  return <section className="conflicts"><h3>待确认冲突（{conflicts.length}）</h3>{conflicts.map((conflict, index) => <article key={`${conflict.type}-${index}`} className="conflict-item"><p><strong>{conflict.names.join(' / ')}</strong>{conflict.blocking && <span className="status warning">阻塞确认</span>}</p><div><button onClick={() => onResolve(index, 'MERGE')} disabled={disabled}>合并</button><button onClick={() => onResolve(index, 'SEPARATE')} disabled={disabled}>保留分开</button><button onClick={() => onResolve(index, 'RENAME_MERGE')} disabled={disabled}>重命名合并</button></div></article>)}</section>
}
