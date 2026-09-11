import { useState } from 'react'
export function AnswerComposer({ disabled = false, question = '', onSubmit }: { disabled?: boolean; question?: string; onSubmit: (value: { content: string; idempotencyKey: string }) => void | boolean | Promise<void | boolean> }) {
  const [draft, setDraft] = useState('')
  const [helper, setHelper] = useState('卡住了也没关系，可以先说一个具体经历，再补充你的做法和结果。')
  const [alternateQuestion, setAlternateQuestion] = useState('')
  const submit = async () => { if (!draft.trim() || disabled) return; const accepted = await onSubmit({ content: draft, idempotencyKey: crypto.randomUUID() }); if (accepted !== false) setDraft('') }
  return <div className="assessment-composer"><label htmlFor="assessment-answer">你的回答</label><div className="assessment-helper-messages" aria-live="polite"><p className="assessment-support">{helper}</p>{alternateQuestion && <p className="assessment-rephrase">{alternateQuestion}</p>}</div><textarea id="assessment-answer" value={draft} onChange={e => setDraft(e.target.value)} disabled={disabled} placeholder="写下你的真实经历、做法和结果…" rows={5} /><div className="assessment-composer-actions"><div className="assessment-helper-actions"><button type="button" onClick={() => setHelper('提示：先说清楚背景、你负责的部分，以及最后带来的结果。')} disabled={disabled}>提示一下</button><button type="button" onClick={() => setAlternateQuestion(question ? `换个角度想想：${question} 你也可以只讲一个最具体的例子。` : '换个角度想想：先讲一个最具体的例子。')} disabled={disabled}>换个说法</button></div><button className="primary-button" onClick={submit} disabled={disabled || !draft.trim()}>{disabled ? '处理中…' : '提交回答'}</button></div></div>
}
