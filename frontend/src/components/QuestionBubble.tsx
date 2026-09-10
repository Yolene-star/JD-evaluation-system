import type { AssessmentQuestion } from '../types/assessment'
export function QuestionBubble({ question, competencyNames }: { question: AssessmentQuestion; competencyNames: Record<string, string> }) {
  const names = question.coveredCompetencyIds.map(id => competencyNames[id] ?? id)
  const composite = names.length > 1
  return <article className="assessment-question message-bubble agent"><span>{composite ? `综合题 · 覆盖 ${names.length} 项能力` : names[0] ?? '当前问题'}</span><p>{question.content}</p>{composite && <div className="assessment-tags">{names.map(name => <span key={name}>{name}</span>)}</div>}</article>
}
