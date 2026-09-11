import { useEffect, useRef, useState } from 'react'
import { assessmentApi, resumeApi, type ResumeContextSummary } from '../lib/api'
import type { AssessmentSnapshot } from '../types/assessment'
import { AssessmentIntroCard } from './AssessmentIntroCard'
import { AssessmentCompletionCard } from './AssessmentCompletionCard'
import { AnswerComposer } from './AnswerComposer'
import { EvidenceInlineCard } from './EvidenceInlineCard'
import { QuestionBubble } from './QuestionBubble'
import { RetryNotice } from './RetryNotice'
import { ThinkingIndicator } from './ThinkingIndicator'

export function AssessmentTimeline({ snapshot, competencyNames }: { snapshot: AssessmentSnapshot; competencyNames: Record<string, string> }) {
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }) }, [snapshot.turns.length, snapshot.currentQuestion?.id])
  const seen = new Set<string>()
  const turns = snapshot.turns.filter(turn => { if (turn.role !== 'SYSTEM') return true; const key = `${turn.role}:${turn.content}`; if (seen.has(key)) return false; seen.add(key); return true })
  const persistedQuestionIds = new Set(turns.filter(turn => turn.role === 'SYSTEM').map(turn => turn.id))
  return <div className="assessment-history">
    {turns.map(turn => turn.role === 'SYSTEM' && turn.type === 'ANSWER'
      ? <article className="assessment-agent-notice" key={turn.id}><span>Agent</span><p>{turn.content}</p></article>
      : turn.role === 'SYSTEM'
      ? <QuestionBubble key={turn.id} question={{
          id: turn.id,
          content: turn.content,
          turnType: turn.type === 'FOLLOW_UP' ? 'FOLLOW_UP' : 'MAIN_QUESTION',
          coveredCompetencyIds: turn.coveredCompetencyIds ?? [],
        }} competencyNames={competencyNames} />
      : <article className="assessment-answer" key={turn.id}><span>你的回答</span><p>{turn.content}</p></article>)}
    {snapshot.currentQuestion && !persistedQuestionIds.has(snapshot.currentQuestion.id) && <QuestionBubble question={snapshot.currentQuestion} competencyNames={competencyNames} />}
    <div ref={endRef} aria-hidden="true" />
  </div>
}

export function AssessmentView({ projectId, onSnapshot, onSessionId, snapshotOverride }: { projectId: string; onSnapshot?: (snapshot: AssessmentSnapshot) => void; onSessionId?: (sessionId: string) => void; snapshotOverride?: AssessmentSnapshot }) {
  const [sessionId, setSessionId] = useState<string>(); const [snapshot, setSnapshot] = useState<AssessmentSnapshot>(); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [assistantNotices, setAssistantNotices] = useState<string[]>([]); const createdFor = useState<{ id?: string }>({})[0]
  const [resume, setResume] = useState<ResumeContextSummary>(); const [resumeReady, setResumeReady] = useState(false); const [useResume, setUseResume] = useState(false)
  // Stage controls (pause/resume/finish) are rendered by the parent workbench.
  // Keep this view in sync with the parent's refreshed snapshot so a successful
  // resume immediately reveals the answer composer instead of leaving the old
  // PAUSED view mounted.
  useEffect(() => {
    if (!snapshotOverride) return
    setSnapshot(snapshotOverride)
    if (snapshotOverride.sessionId && snapshotOverride.sessionId !== sessionId) {
      setSessionId(snapshotOverride.sessionId)
    }
  }, [snapshotOverride, sessionId])
  const refresh = async (id = sessionId) => { if (!id) return; const next = await assessmentApi.snapshot<AssessmentSnapshot>(id); setSnapshot(next); onSnapshot?.(next) }
  const create = async (withResume = useResume) => { setBusy(true); setError(''); try { const result = await assessmentApi.create(projectId, undefined, withResume) as { id?: string; session_id?: string }; const id = result.id ?? result.session_id; if (!id) throw new Error('未返回测评会话'); setSessionId(id); onSessionId?.(id); await refresh(id) } catch (cause) { setError(cause instanceof Error ? cause.message : '创建测评失败') } finally { setBusy(false) } }
  useEffect(() => { if (createdFor.id === projectId) return; createdFor.id = projectId; setSessionId(undefined); setSnapshot(undefined); onSessionId?.(''); setResumeReady(false); resumeApi.current(projectId).then(value => { setResume(value); setUseResume(true) }).catch(() => { setResume(undefined); setUseResume(false) }).finally(() => setResumeReady(true)) }, [projectId])
  const start = async () => { if (!sessionId) return; setBusy(true); try { await assessmentApi.start(sessionId); await refresh() } finally { setBusy(false) } }
  const submit = async ({ content, idempotencyKey }: { content: string; idempotencyKey: string }) => { if (!sessionId) return false; setBusy(true); setError(''); try { const next = await assessmentApi.submit<AssessmentSnapshot>(sessionId, content, idempotencyKey); setSnapshot(next); onSnapshot?.(next); setAssistantNotices(items => [...items, /我没有|不知道|不清楚|卡住|紧张/.test(content) ? '收到，先不用紧张。你可以从一个很小的具体例子开始，我们再一步一步补充。' : '收到，我先记录这段回答，再继续核对具体做法、依据和结果。']); return true } catch (cause) { setError(cause instanceof Error ? cause.message : '提交失败'); return false } finally { setBusy(false) } }
  const mutate = async (action: 'pause' | 'resume' | 'finish') => { if (!sessionId) return; setBusy(true); try { await assessmentApi[action](sessionId); await refresh() } finally { setBusy(false) } }
  if (error) return <div role="alert" className="error">{error}<button onClick={() => void create()}>重试创建</button></div>
  if (!snapshot) {
    if (!resumeReady) return <ThinkingIndicator phase="正在加载测评设置" />
    return <section className="assessment-setup" aria-labelledby="assessment-setup-title">
      <h3 id="assessment-setup-title">开始阶段二测评</h3>
      <p>简历是可选背景，只用于个性化提问，不会直接作为评分证据。</p>
      {resume ? <p className="notice">当前简历：{resume.source_filename}（v{resume.version}）</p> : <p className="muted">尚未上传简历，你仍可以完整完成测评。</p>}
      <label>上传或替换简历（可选）<input type="file" accept=".txt,.pdf,.docx,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" disabled={busy} onChange={async event => { const file = event.target.files?.[0]; if (!file) return; setBusy(true); setError(''); try { const next = await resumeApi.upload(projectId, file); setResume(next); setUseResume(true) } catch (cause) { setError(cause instanceof Error ? cause.message : '简历解析失败') } finally { setBusy(false); event.currentTarget.value = '' } }} /></label>
      {resume && <button disabled={busy} onClick={async () => { setBusy(true); setError(''); try { await resumeApi.remove(projectId); setResume(undefined); setUseResume(false) } catch (cause) { setError(cause instanceof Error ? cause.message : '移除简历失败') } finally { setBusy(false) } }}>移除当前简历</button>}
      <label><input type="checkbox" checked={useResume && Boolean(resume)} onChange={event => setUseResume(event.target.checked)} disabled={!resume} /> 使用当前简历作为背景参考</label>
      <div className="assessment-actions"><button className="primary-button" disabled={busy} onClick={() => void create()}>开始测评</button></div>
    </section>
  }
  const names = Object.fromEntries(snapshot.competencies.map(item => [item.competencyId, item.name]))
  if (snapshot.status === 'READY') return <AssessmentIntroCard totalCount={snapshot.competencies.length} onStart={start} />
  const retry = async () => { if (!sessionId) return; setBusy(true); try { await assessmentApi.retry(sessionId, crypto.randomUUID()); await refresh() } finally { setBusy(false) } }
  return <div className="assessment-view"><AssessmentTimeline snapshot={snapshot} competencyNames={names} />{snapshot.retryable && <RetryNotice message="分析暂时失败，已保留你的回答。你可以先休息一下，准备好后再重试。" onRetry={retry} />}{snapshot.evidenceGroups && <EvidenceInlineCard groups={snapshot.evidenceGroups} />}{snapshot.completion !== 'NONE' && <AssessmentCompletionCard completion={snapshot.completion} completedCount={snapshot.competencies.filter(c => c.status === 'SUFFICIENT' || c.status === 'EXHAUSTED').length} totalCount={snapshot.competencies.length} incompleteNames={snapshot.competencies.filter(c => c.status === 'INCOMPLETE').map(c => c.name)} />}{snapshot.status === 'IN_PROGRESS' && <AnswerComposer disabled={busy} question={snapshot.currentQuestion?.content} agentMessage={assistantNotices.at(-1) ?? ''} onSubmit={submit} />}</div>
}
