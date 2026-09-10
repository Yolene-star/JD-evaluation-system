import type { AssessmentReport } from '../types/report'

export function ReportWorkbench({ report }: { report: AssessmentReport }) {
  const scored = report.evaluations.filter(item => item.score !== null).length
  return <div className="report-workbench"><section><span className="eyebrow">Stage 3 · Report</span><h3>阶段三报告工作台</h3><p>报告版本：v{report.reportVersion}</p><p>证据包：{report.completion}</p></section><section><strong>报告覆盖</strong><p>{scored} / {report.evaluations.length} 项能力已评价</p><progress value={report.evaluatedWeight} max={1} /></section><section><strong>评分规则</strong><p>{report.scoringRuleVersion}</p><small>未评价能力不计为 0 分</small></section><section><strong>咨询范围</strong><p>可询问评分依据、证据引用和改进措施。</p><small>Agent 无权修改分数、模型或历史报告。</small></section></div>
}
