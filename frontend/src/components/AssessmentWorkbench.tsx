import type { AssessmentSnapshot } from '../types/assessment'

export function AssessmentWorkbench({ snapshot, onPause, onResume, onFinish, onOpenReport }: { snapshot: AssessmentSnapshot; onPause?: () => void; onResume?: () => void; onFinish?: () => void; onOpenReport?: () => void }) {
  const done = snapshot.competencies.filter(c => c.status === 'SUFFICIENT' || c.status === 'EXHAUSTED').length
  const names = new Map(snapshot.competencies.map(item => [item.competencyId, item.name]))
  const confirmed = snapshot.agentStatus?.confirmedCompetencyIds.map(id => ({ id, name: names.get(id) ?? id })) ?? []
  const activeName = snapshot.agentStatus?.activeCompetencyId ? names.get(snapshot.agentStatus.activeCompetencyId) ?? snapshot.agentStatus.activeCompetencyId : undefined

  return <div className="assessment-workbench">
    <section><span className="eyebrow">Stage 2 · Adaptive assessment</span><h3>测评工作台</h3><p>状态：{snapshot.status} · 模型版本：{snapshot.modelVersionId}</p></section>
    {snapshot.agentStatus && <section className="agent-status-panel" aria-labelledby="agent-status-title">
      <h4 id="agent-status-title">AI 正在评估</h4>
      <ul>
        {confirmed.map(item => <li key={`confirmed-${item.id}`}><span aria-hidden="true" className="agent-status-marker" />{item.name}已确认</li>)}
        {activeName && <li key={`active-${snapshot.agentStatus.activeCompetencyId}`}><span aria-hidden="true" className="agent-status-marker is-active" />正在验证{activeName}</li>}
        {snapshot.agentStatus.pendingEvidence.map(item => <li key={`pending-${item}`}><span aria-hidden="true" className="agent-status-marker is-pending" />等待补充：{item}</li>)}
      </ul>
      {snapshot.agentStatus.reason && <p>{snapshot.agentStatus.reason}</p>}
    </section>}
    <section><strong>进度</strong><p>{done} / {snapshot.competencies.length} 项能力已完成</p><progress value={done} max={snapshot.competencies.length || 1} /></section>
    <section><h4>能力项状态</h4>{snapshot.competencies.map(item => <div className="assessment-competency-row" key={item.competencyId}><span>{item.name}</span><small>{item.status} · 追问 {item.followUpCount} / 2</small></div>)}</section>
    <div className="assessment-actions">{snapshot.status === 'IN_PROGRESS' && <><button onClick={onPause}>暂停</button><button onClick={onFinish}>结束测评</button></>}{snapshot.status === 'PAUSED' && <button onClick={onResume}>继续测评</button>}{snapshot.completion !== 'NONE' && <button className="primary-button" onClick={onOpenReport}>查看人才画像</button>}</div>
  </div>
}
