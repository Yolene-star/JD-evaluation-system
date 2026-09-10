import { useEffect, useState } from 'react'
import { assessmentApi } from '../lib/api'
import type { AssessmentSnapshot } from '../types/assessment'
import { AssessmentIntroCard } from './AssessmentIntroCard'
import { AssessmentCompletionCard } from './AssessmentCompletionCard'
import { AnswerComposer } from './AnswerComposer'
import { EvidenceInlineCard } from './EvidenceInlineCard'
import { QuestionBubble } from './QuestionBubble'
import { RetryNotice } from './RetryNotice'
import { ThinkingIndicator } from './ThinkingIndicator'

export function AssessmentView({ projectId, onSnapshot, onSessionId }: { projectId: string; onSnapshot?: (snapshot: AssessmentSnapshot) => void; onSessionId?: (sessionId: string) => void }) {
  const [sessionId, setSessionId] = useState<string>(); const [snapshot, setSnapshot] = useState<AssessmentSnapshot>(); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const createdFor = useState<{ id?: string }>({})[0]
  const refresh = async (id = sessionId) => { if (!id) return; const next = await assessmentApi.snapshot<AssessmentSnapshot>(id); setSnapshot(next); onSnapshot?.(next) }
  const create = async () => { setBusy(true); setError(''); try { const result = await assessmentApi.create(projectId) as { id?: string; session_id?: string }; const id = result.id ?? result.session_id; if (!id) throw new Error('未返回测评会话'); setSessionId(id); onSessionId?.(id); await refresh(id) } catch (cause) { setError(cause instanceof Error ? cause.message : '创建测评失败') } finally { setBusy(false) } }
  useEffect(() => { if (createdFor.id !== projectId) { createdFor.id = projectId; create() } }, [projectId])
  const start = async () => { if (!sessionId) return; setBusy(true); try { await assessmentApi.start(sessionId); await refresh() } finally { setBusy(false) } }
  const submit = async ({ content, idempotencyKey }: { content: string; idempotencyKey: string }) => { if (!sessionId) return false; setBusy(true); setError(''); try { const next = await assessmentApi.submit<AssessmentSnapshot>(sessionId, content, idempotencyKey); setSnapshot(next); onSnapshot?.(next); return true } catch (cause) { setError(cause instanceof Error ? cause.message : '提交失败'); return false } finally { setBusy(false) } }
  const mutate = async (action: 'pause' | 'resume' | 'finish') => { if (!sessionId) return; setBusy(true); try { await assessmentApi[action](sessionId); await refresh() } finally { setBusy(false) } }
  if (error) return <div role="alert" className="error">{error}<button onClick={create}>重试创建</button></div>
  if (!snapshot) return <ThinkingIndicator phase="正在加载测评" />
  const names = Object.fromEntries(snapshot.competencies.map(item => [item.competencyId, item.name]))
  if (snapshot.status === 'READY') return <AssessmentIntroCard totalCount={snapshot.competencies.length} onStart={start} />
  const retry = async () => { if (!sessionId) return; setBusy(true); try { await assessmentApi.retry(sessionId, crypto.randomUUID()); await refresh() } finally { setBusy(false) } }
  return <div className="assessment-view">{snapshot.currentQuestion && <QuestionBubble question={snapshot.currentQuestion} competencyNames={names} />}{snapshot.turns.filter(turn => turn.role === 'USER').map(turn => <article className="assessment-answer" key={turn.id}><span>你的回答</span><p>{turn.content}</p></article>)}{snapshot.retryable && <RetryNotice message="分析暂时失败，已保留你的回答。你可以先休息一下，准备好后再重试。" onRetry={retry} />}{snapshot.evidenceGroups && <EvidenceInlineCard groups={snapshot.evidenceGroups} />}{snapshot.completion !== 'NONE' && <AssessmentCompletionCard completion={snapshot.completion} completedCount={snapshot.competencies.filter(c => c.status === 'SUFFICIENT' || c.status === 'EXHAUSTED').length} totalCount={snapshot.competencies.length} incompleteNames={snapshot.competencies.filter(c => c.status === 'INCOMPLETE').map(c => c.name)} />}{snapshot.status === 'IN_PROGRESS' && <AnswerComposer disabled={busy} question={snapshot.currentQuestion?.content} onSubmit={submit} />}</div>
}
