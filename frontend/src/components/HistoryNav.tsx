export type HistoryProject = { id: string; name: string; status: string }

export function HistoryNav({ projects, activeId, onCreate, onSelect, onDelete, busy }: { projects: HistoryProject[]; activeId?: string; onCreate: () => void; onSelect: (id: string) => void; onDelete?: (id: string) => void; busy?: boolean }) {
  return <aside className="history-panel"><h1>岗位测评</h1><p className="muted">AI 驱动的岗位胜任力模型工作流</p><button className="primary-button" onClick={onCreate} disabled={busy}>{busy ? '创建中…' : '新建任务'}</button><nav aria-label="历史任务">
    {projects.length === 0 ? <p className="muted">历史任务将在这里显示</p> : projects.map(project => <div className={`history-entry ${project.id === activeId ? 'active' : ''}`} key={project.id}><button className="history-item" onClick={() => onSelect(project.id)}>{project.name}<small>{project.status}</small></button>{onDelete && <button className="history-delete" onClick={() => onDelete(project.id)} aria-label={`删除任务 ${project.name}`} title="删除任务">×</button>}</div>)}
  </nav></aside>
}
