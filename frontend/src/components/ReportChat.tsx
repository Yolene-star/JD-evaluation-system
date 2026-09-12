import { useEffect, useRef, useState } from 'react'
import { parseMarkdown } from '../lib/markdown'

function InlineMarkdown({ text }: { text: string }) { return <>{text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, index) => part.startsWith('**') && part.endsWith('**') ? <strong key={index}>{part.slice(2, -2)}</strong> : part.startsWith('`') && part.endsWith('`') ? <code key={index}>{part.slice(1, -1)}</code> : <span key={index}>{part}</span>)}</> }
function MarkdownMessage({ content }: { content: string }) { return <>{parseMarkdown(content).map((block, index) => block.type === 'heading' ? <h4 key={index}><InlineMarkdown text={block.text ?? ''} /></h4> : block.type === 'ordered-list' ? <ol key={index}>{block.items?.map(item => <li key={item}><InlineMarkdown text={item} /></li>)}</ol> : block.type === 'unordered-list' ? <ul key={index}>{block.items?.map(item => <li key={item}><InlineMarkdown text={item} /></li>)}</ul> : <p key={index}><InlineMarkdown text={block.text ?? ''} /></p>)}</> }
function EvidenceReferences({ evidence }: { evidence?: string[]; ids?: string[] }) {
  const items = evidence?.filter(Boolean) ?? []
  if (!items.length) return null
  return <details className="report-chat-evidence"><summary>面试依据（{items.length} 条）</summary><ol>{items.map((item, index) => <li key={`${index}-${item}`}> <strong>证据 {index + 1}</strong><blockquote>{item}</blockquote></li>)}</ol></details>
}

export type ReportChatMessage = { id: string; role: 'user' | 'agent'; content: string; citedEvidenceIds?: string[]; citedEvidence?: string[] }

export function ReportChat({ reportId, messages, onSend, busy = false }: { reportId: string; messages: ReportChatMessage[]; onSend: (content: string) => Promise<unknown> | unknown; busy?: boolean }) {
  const [content, setContent] = useState('')
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }) }, [messages.length, busy])
  const submit = async () => { const value = content.trim(); if (!value) return; await onSend(value); setContent('') }
  return <section className="report-chat" aria-label={`报告 ${reportId} 咨询`}><header><div><span className="eyebrow">Evidence-bound consultation</span><h3>咨询 Agent</h3><p className="panel-subtitle">询问评分依据、证据和改进措施。回答不会修改报告。</p></div></header><div className="report-chat-suggestions"><button onClick={() => onSend('为什么得到这个分数？')}>为什么得到这个分数？</button><button onClick={() => onSend('我应该如何改进？')}>给我改进措施</button></div><div className="report-chat-history" aria-live="polite">{messages.length ? messages.map(item => <article key={item.id} className={`report-chat-message ${item.role}`}><span>{item.role === 'user' ? '你' : 'Agent'}</span>{item.role === 'agent' ? <MarkdownMessage content={item.content} /> : <p>{item.content}</p>}{item.role === 'agent' && <EvidenceReferences evidence={item.citedEvidence} ids={item.citedEvidenceIds} />}</article>) : <p className="muted">还没有咨询记录。你可以从上方问题开始。</p>}<div ref={endRef} aria-hidden="true" /></div><div className="report-chat-composer"><label htmlFor="report-question">询问当前报告</label><textarea id="report-question" value={content} onChange={event => setContent(event.target.value)} placeholder="例如：系统设计能力为什么是这个分数？我该如何补充证据？" rows={3} /><button className="primary-button" disabled={busy || !content.trim()} onClick={submit}>{busy ? '分析中…' : '发送问题'}</button></div></section>
}
