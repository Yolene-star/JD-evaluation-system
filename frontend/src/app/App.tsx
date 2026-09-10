import { useCallback, useEffect, useRef, useState } from 'react'
import { ConversationTimeline, type ConversationMessage } from '../components/ConversationTimeline'
import { HistoryNav } from '../components/HistoryNav'
import { MaterialDialog } from '../components/MaterialDialog'
import { StageWorkbench } from '../components/StageWorkbench'
import { OperationCard } from '../components/OperationCard'
import { apiFetch, assessmentApi } from '../lib/api'
import { buildMaterialNotice } from '../lib/materialNotice'
import { buildChatPayload, createPendingOperation, type PendingOperation } from '../lib/chat'
import { formatSystemNotice } from '../lib/systemNotice'
import { AssessmentView } from '../components/AssessmentView'
import { AssessmentWorkbench } from '../components/AssessmentWorkbench'
import type { AssessmentSnapshot } from '../types/assessment'
import { ReportView } from '../components/ReportView'
import { reportApi } from '../lib/reportApi'
import type { AssessmentReport } from '../types/report'
import { ReportWorkbench } from '../components/ReportWorkbench'
import { ReportChat, type ReportChatMessage } from '../components/ReportChat'
import { StageRail, type StageNumber } from '../components/StageRail'

function formatLlmError(error?: string): string {
  if (error?.includes('10013') || error?.toLowerCase().includes('permission')) {
    return '本机网络策略阻止了 DeepSeek 连接（WinError 10013）。请配置 HTTPS_PROXY，或切换到允许访问 api.deepseek.com 的网络；当前回复已使用演示兜底。'
  }
  return `DeepSeek 连接失败：${error ?? '请检查网络或 API 配置。'}`
}

export default function App() {
  const [showMaterials, setShowMaterials] = useState(false)
  const [showWorkbench, setShowWorkbench] = useState(false)
  const [showAssessment, setShowAssessment] = useState(false)
  const [showReport, setShowReport] = useState(false)
  const [currentStage, setCurrentStage] = useState<StageNumber>(1)
  const [reportSessionId, setReportSessionId] = useState<string>()
  const [report, setReport] = useState<AssessmentReport>()
  const [reportLoading, setReportLoading] = useState(false)
  const [reportError, setReportError] = useState('')
  const [reportTab, setReportTab] = useState<'report' | 'chat'>('report')
  const [reportMessages, setReportMessages] = useState<ReportChatMessage[]>([])
  const [reportChatBusy, setReportChatBusy] = useState(false)
  const [assessmentSnapshot, setAssessmentSnapshot] = useState<AssessmentSnapshot>()
  const workbenchToggleRef = useRef<HTMLButtonElement>(null)
  useEffect(() => { const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape' && showWorkbench) { setShowWorkbench(false); workbenchToggleRef.current?.focus() } }; window.addEventListener('keydown', onKeyDown); return () => window.removeEventListener('keydown', onKeyDown) }, [showWorkbench])
  const [projects, setProjects] = useState<{ id: string; name: string; status: string }[]>([])
  const [activeId, setActiveId] = useState<string>()
  const [message, setMessage] = useState('')
  const [reply, setReply] = useState('')
  const [appError, setAppError] = useState('')
  const [appBusy, setAppBusy] = useState(false)
  const [operationBusy, setOperationBusy] = useState(false)
  const [workbenchRefreshKey, setWorkbenchRefreshKey] = useState(0)
  const mutateAssessment = async (action: 'pause' | 'resume' | 'finish') => {
    if (!reportSessionId) return
    if (action === 'finish' && !window.confirm('确定结束当前测评吗？未完成能力会标记为待补充。')) return
    try {
      await assessmentApi[action](reportSessionId)
      const next = await assessmentApi.snapshot<AssessmentSnapshot>(reportSessionId)
      setAssessmentSnapshot(next)
    } catch (cause) {
      setAppError(cause instanceof Error ? cause.message : '测评状态更新失败')
    }
  }
  const [pendingOperation, setPendingOperation] = useState<PendingOperation>()
  const [messages, setMessages] = useState<ConversationMessage[]>([])
  const [chatSource, setChatSource] = useState<'llm' | 'demo-fallback' | 'llm-error'>('demo-fallback')
  useEffect(() => { apiFetch<typeof projects>('/api/projects').then(setProjects).catch(() => undefined) }, [])
  const loadConversation = useCallback(async (projectId: string, isCurrent: () => boolean = () => true) => {
    const [history, events] = await Promise.all([
      apiFetch<{ messages: Array<{ id: string; role: string; content: string }> }>(`/api/projects/${projectId}/chat/history`),
      apiFetch<Array<{ id: string; action: string; payload: string; created_at: string }>>(`/api/projects/${projectId}/events`),
    ])
    const chat = history.messages.map(item => ({ id: item.id, role: item.role === 'agent' ? 'agent' as const : item.role === 'system' ? 'system' as const : 'user' as const, content: item.content }))
    const notices = events.slice().reverse().map(event => ({ id: `system-${event.id}`, role: 'system' as const, content: formatSystemNotice(event.action, event.payload) }))
    if (isCurrent()) setMessages([...chat, ...notices])
  }, [])
  useEffect(() => {
    if (!activeId) { setMessages([]); return }
    let cancelled = false
    loadConversation(activeId, () => !cancelled).catch(() => { if (!cancelled) setMessages([]) })
    return () => { cancelled = true }
  }, [activeId, loadConversation])
  useEffect(() => {
    if (!activeId) return
    const refreshOnReturn = () => {
      loadConversation(activeId).catch(() => undefined)
      setWorkbenchRefreshKey(key => key + 1)
    }
    window.addEventListener('focus', refreshOnReturn)
    document.addEventListener('visibilitychange', refreshOnReturn)
    return () => { window.removeEventListener('focus', refreshOnReturn); document.removeEventListener('visibilitychange', refreshOnReturn) }
  }, [activeId, loadConversation])
  useEffect(() => { const handler = async (event: Event) => { const name = (event as CustomEvent<string>).detail; setMessages(current => [...current, { id: `material-${Date.now()}`, role: 'system', content: buildMaterialNotice(name) }]); if (!activeId) return; try { await apiFetch(`/api/projects/${activeId}/analysis/run`, { method: 'POST' }); await apiFetch(`/api/projects/${activeId}/aggregate`, { method: 'POST' }); setMessages(current => [...current, { id: `analysis-${Date.now()}`, role: 'system', content: `《${name}》已完成解析和总模型汇总，工作台数据已刷新。` }]); await refreshProjects(); setWorkbenchRefreshKey(key => key + 1) } catch (cause) { setMessages(current => [...current, { id: `analysis-error-${Date.now()}`, role: 'system', content: `《${name}》已保存，但自动解析失败：${cause instanceof Error ? cause.message : '请点击工作台中的“运行解析”重试。'}` }]) } }; window.addEventListener('material-added', handler); return () => window.removeEventListener('material-added', handler) }, [activeId])
  const refreshProjects = async () => setProjects(await apiFetch<typeof projects>('/api/projects'))
  const createProject = async () => { setAppBusy(true); setAppError(''); try { const project = await apiFetch<{ id: string; name: string; status: string }>('/api/projects', { method: 'POST', body: JSON.stringify({ name: '未命名岗位任务' }) }); setProjects(current => [project, ...current]); setActiveId(project.id); setReply(''); setPendingOperation(undefined) } catch (cause) { setAppError(cause instanceof Error ? cause.message : '新建任务失败，请重试。') } finally { setAppBusy(false) } }
  const deleteProject = async (id: string) => { setAppBusy(true); setAppError(''); try { await apiFetch(`/api/projects/${id}`, { method: 'DELETE' }); setProjects(current => current.filter(project => project.id !== id)); if (activeId === id) { setActiveId(undefined); setMessages([]); setReply(''); setPendingOperation(undefined) } } catch (cause) { setAppError(cause instanceof Error ? cause.message : '删除任务失败，请重试。') } finally { setAppBusy(false) } }
  const selectProject = (id: string) => { setActiveId(id); setCurrentStage(1); setReply(''); setPendingOperation(undefined); setAppError(''); setShowAssessment(false); setShowReport(false); setAssessmentSnapshot(undefined); setReport(undefined); setReportSessionId(undefined) }
  const loadReport = async () => {
    if (!reportSessionId) return
    setReportLoading(true)
    setReportError('')
    try {
      const rows = await reportApi.list(reportSessionId)
      if (rows[0]) { setReport(rows[0]); setReportMessages(await reportApi.chatHistory(rows[0].id)); return }
      const created = await reportApi.generate(reportSessionId, { idempotency_key: `report-${reportSessionId}` })
      setReport(created)
      setReportMessages([])
    } catch (cause) {
      setReportError(cause instanceof Error ? cause.message : '报告生成失败，请稍后重试。')
    } finally {
      setReportLoading(false)
    }
  }
  const askReport = async (content: string) => { if (!report) return; setReportChatBusy(true); try { await reportApi.ask(report.id, content); setReportMessages(await reportApi.chatHistory(report.id)) } catch (cause) { setReportError(cause instanceof Error ? cause.message : '咨询失败，请重试。') } finally { setReportChatBusy(false) } }
  const selectStage = (stage: StageNumber) => {
    setCurrentStage(stage)
    if (stage === 1) { setShowAssessment(false); setShowReport(false); return }
    setShowAssessment(true)
    if (stage === 2) { setShowReport(false); return }
    setShowReport(true)
    setReportTab('report')
    void loadReport()
  }
  const send = async (confirm = false) => { const payload = buildChatPayload(message, confirm, pendingOperation); if (!activeId || !payload) return false; setOperationBusy(true); setAppError(''); try { if (!confirm) setMessages(current => [...current, { id: `user-${Date.now()}`, role: 'user', content: payload.message }]); const result = await apiFetch<{ reply: string; source?: 'llm' | 'demo-fallback' | 'llm-error'; error?: string; operation?: { action: string; requires_confirmation?: boolean }; system_notices?: string[] }>(`/api/projects/${activeId}/chat`, { method: 'POST', body: JSON.stringify(payload) }); setChatSource(result.source ?? 'demo-fallback'); if (result.source === 'llm-error') setAppError(formatLlmError(result.error)); setReply(result.reply); setMessages(current => [...current, ...(result.system_notices ?? []).map((content, index) => ({ id: `system-${Date.now()}-${index}`, role: 'system' as const, content })), { id: `agent-${Date.now()}`, role: 'agent', content: result.reply }]); setPendingOperation(createPendingOperation(result.operation, payload.message)); if (!confirm) setMessage(''); await refreshProjects(); setWorkbenchRefreshKey(key => key + 1); return true } catch (cause) { setAppError(cause instanceof Error ? cause.message : '对话操作失败，请检查当前项目状态后重试。'); return false } finally { setOperationBusy(false) } }
  const confirmOperation = async () => { if (await send(true)) setPendingOperation(undefined) }
  const materialsDisabledReason = activeId ? undefined : '请先新建或选择一个任务'
  const sendDisabledReason = !activeId ? '请先新建或选择一个任务' : !message.trim() ? '请输入消息后发送' : undefined
  return <main className={`app-shell shell-stage-${currentStage}`}><HistoryNav projects={projects} activeId={activeId} onCreate={createProject} onSelect={selectProject} onDelete={deleteProject} busy={appBusy} />
    <section className="conversation-panel"><header><div><span className="eyebrow">{showReport ? 'Stage 3 · 能力评价' : showAssessment ? 'Stage 2 · 自适应测评' : 'Stage 1 · JD 分析'}</span><h2>{showReport ? '能力评价与人才画像' : showAssessment ? '文字测评' : '与 Agent 对话'}</h2><p className="panel-subtitle">{showReport ? '基于版本化证据生成可追溯的辅助性报告。' : showAssessment ? '围绕已确认模型逐项回答，生成可追溯证据。' : '通过对话核对材料、理解依据并推进模型确认。'}</p></div><div className="header-actions">{showAssessment && <button ref={workbenchToggleRef} onClick={() => setShowWorkbench(true)}>工作台</button>}{showAssessment && assessmentSnapshot?.completion !== 'NONE' && <button onClick={() => { setShowReport(true); setReportTab('report'); void loadReport() }} disabled={!reportSessionId || reportLoading}>查看阶段三报告</button>}{showReport && <><button aria-pressed={reportTab === 'report'} onClick={() => setReportTab('report')}>报告</button><button aria-pressed={reportTab === 'chat'} onClick={() => setReportTab('chat')}>咨询 Agent</button><button onClick={() => { setShowReport(false); setReportError('') }}>返回阶段二</button></>}{!showReport && <button onClick={() => { setShowReport(false); setShowAssessment(value => !value) }} disabled={!activeId}>{showAssessment ? '返回阶段一' : '进入阶段二'}</button>}<span className="status">{activeId ? (chatSource === 'llm' ? 'LLM 已连接' : chatSource === 'llm-error' ? 'LLM 连接失败' : '演示模式') : '准备开始'}</span></div></header>{showReport ? report ? reportTab === 'chat' ? <ReportChat reportId={report.id} messages={reportMessages} onSend={askReport} busy={reportChatBusy} /> : <ReportView report={report} onRetryNarrative={() => reportApi.retryNarrative(report.id).then(setReport)} /> : <section className="report-loading" role={reportError ? 'alert' : undefined}><h3>{reportLoading ? '正在生成阶段三报告…' : '阶段三报告暂时不可用'}</h3>{reportError && <p>{reportError}</p>}{!reportLoading && <button onClick={() => void loadReport()}>重试生成报告</button>}</section> : showAssessment && activeId ? <AssessmentView projectId={activeId} onSnapshot={setAssessmentSnapshot} onSessionId={setReportSessionId} /> : <><ConversationTimeline messages={messages} />{appError && <p role="alert" className="error">{appError}</p>}{pendingOperation?.requires_confirmation && <OperationCard action={pendingOperation.action} result="该操作会修改项目数据；确认后会写入审计事件。" onConfirm={confirmOperation} busy={operationBusy} />}<div className="composer"><input aria-label="消息" value={message} onChange={event => setMessage(event.target.value)} placeholder="例如：哪些能力来自 JD-1？为什么要合并这两项？" /><button onClick={() => setShowMaterials(true)} disabled={!activeId} title={materialsDisabledReason}>{activeId ? '添加材料' : '先选任务'}</button><button onClick={() => send()} disabled={Boolean(sendDisabledReason) || operationBusy} title={sendDisabledReason}>{operationBusy ? '处理中…' : '发送'}</button><button ref={workbenchToggleRef} className="mobile-workbench-toggle" onClick={() => setShowWorkbench(true)} disabled={!activeId} title={materialsDisabledReason}>工作台</button></div></>}</section>
    <aside className={showWorkbench ? 'workbench-panel mobile-open' : 'workbench-panel'}><header><div><span className="eyebrow">Workbench</span><h2>{showReport ? '阶段三' : showAssessment ? '阶段二' : '阶段一'}</h2></div><button className="mobile-close" onClick={() => setShowWorkbench(false)} aria-label="关闭工作台">×</button></header><StageRail currentStage={currentStage} availability={{ 1: Boolean(activeId), 2: Boolean(activeId), 3: Boolean(reportSessionId && assessmentSnapshot?.completion !== 'NONE') }} onSelect={selectStage} />{showReport && report ? <ReportWorkbench report={report} /> : showAssessment && assessmentSnapshot ? <AssessmentWorkbench snapshot={assessmentSnapshot} onPause={() => mutateAssessment('pause')} onResume={() => mutateAssessment('resume')} onFinish={() => mutateAssessment('finish')} /> : <StageWorkbench projectId={activeId} refreshKey={workbenchRefreshKey} />}</aside>{showMaterials && activeId && <MaterialDialog projectId={activeId} onClose={() => setShowMaterials(false)} onAdded={async () => { await refreshProjects(); setWorkbenchRefreshKey(key => key + 1) }} />}
  </main>
}
