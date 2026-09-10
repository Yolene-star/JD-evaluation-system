import { useState } from 'react'

export type ReportChatMessage = { id: string; role: 'user' | 'agent'; content: string; citedEvidenceIds?: string[] }

export function ReportChat({ reportId, messages, onSend, busy = false }: { reportId: string; messages: ReportChatMessage[]; onSend: (content: string) => Promise<unknown> | unknown; busy?: boolean }) {
  const [content, setContent] = useState('')
  const submit = async () => { const value = content.trim(); if (!value) return; await onSend(value); setContent('') }
  return <section className="report-chat" aria-label={`报告 ${reportId} 咨询`}><header><div><span className="eyebrow">Evidence-bound consultation</span><h3>咨询 Agent</h3><p className="panel-subtitle">询问评分依据、证据和改进措施。回答不会修改报告。</p></div></header><div className="report-chat-suggestions"><button onClick={() => onSend('为什么得到这个分数？')}>为什么得到这个分数？</button><button onClick={() => onSend('我应该如何改进？')}>给我改进措施</button></div><div className="report-chat-history" aria-live="polite">{messages.length ? messages.map(item => <article key={item.id} className={`report-chat-message ${item.role}`}><span>{item.role === 'user' ? '你' : 'Agent'}</span><p>{item.content}</p>{item.citedEvidenceIds?.length ? <small>引用证据：{item.citedEvidenceIds.join('、')}</small> : null}</article>) : <p className="muted">还没有咨询记录。你可以从上方问题开始。</p>}</div><div className="report-chat-composer"><label htmlFor="report-question">询问当前报告</label><textarea id="report-question" value={content} onChange={event => setContent(event.target.value)} placeholder="例如：系统设计能力为什么是这个分数？我该如何补充证据？" rows={3} /><button className="primary-button" disabled={busy || !content.trim()} onClick={submit}>{busy ? '分析中…' : '发送问题'}</button></div></section>
}
