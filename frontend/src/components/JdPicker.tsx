import { useEffect, useState } from 'react'

export type JdOption = { id: string; title: string; participates_in_model?: boolean }

export function JdPicker({ items, selectedId, onSelect, onRename }: { items: JdOption[]; selectedId?: string; onSelect: (id: string | undefined) => void; onRename?: (id: string, title: string) => Promise<void> }) {
  const selected = items.find(item => item.id === selectedId)
  const [editing, setEditing] = useState(false); const [draft, setDraft] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('')
  useEffect(() => { setEditing(false); setError('') }, [selectedId])
  const startEdit = () => { if (!selected) return; setDraft(selected.title); setError(''); setEditing(true) }
  const save = async () => { const title = draft.trim(); if (!selected || !title) { setError('岗位名称不能为空'); return } setBusy(true); setError(''); try { await onRename?.(selected.id, title); setEditing(false) } catch (cause) { setError(cause instanceof Error ? cause.message : '岗位名称保存失败') } finally { setBusy(false) } }
  return <div className="jd-picker"><label htmlFor="jd-select">选择 JD</label><select id="jd-select" value={selectedId ?? ''} onChange={event => onSelect(event.target.value || undefined)}><option value="">全部 JD</option>{items.map(item => <option key={item.id} value={item.id}>{item.title}{item.participates_in_model === false ? '（已移出）' : ''}</option>)}</select>{editing ? <div className="jd-rename"><label htmlFor="jd-title">岗位名称</label><input id="jd-title" value={draft} onChange={event => { setDraft(event.target.value); if (error) setError('') }} onKeyDown={event => { if (event.key === 'Enter') void save() }} disabled={busy} autoFocus /><button className="primary-button" onClick={save} disabled={busy || !draft.trim()}>{busy ? '保存中…' : '保存'}</button><button onClick={() => { setEditing(false); setError('') }} disabled={busy}>取消</button></div> : <button className="jd-rename-trigger" onClick={startEdit} disabled={!selected || !onRename} title={selected ? '修改岗位名称' : '请先选择一份 JD'}>编辑岗位名称</button>}{error && <p role="alert" className="error">{error}</p>}</div>
}
