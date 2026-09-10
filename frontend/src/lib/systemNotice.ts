type Payload = Record<string, unknown>

function parsePayload(raw: string): Payload {
  try { return JSON.parse(raw) as Payload } catch { return {} }
}

export function formatSystemNotice(action: string, rawPayload: string): string {
  const payload = parsePayload(rawPayload)
  const title = String(payload.title ?? payload.name ?? '')
  const adapter = ({ 'boss-zhipin': 'Boss 直聘', mokahr: 'Mokahr ATS', universal: '通用网页' } as Record<string, string>)[String(payload.adapter ?? '')] ?? '通用网页'
  const labels: Record<string, string> = {
    JD_ADDED: title ? `已添加 JD：${title}` : '已添加 JD',
    JD_UPDATED: title ? `已更新 JD：${title}` : '已更新 JD 信息',
    JD_EXTRACTOR_SELECTED: `已识别网页提取模块：${adapter}`,
    JD_READD: '已将 JD 重新加入当前模型',
    ANALYSIS_COMPLETED: 'JD 解析完成，模型数据已刷新',
    MODEL_AGGREGATED: '总模型已生成',
    MODEL_CONFIRMED: '模型已确认并冻结',
    COMPETENCY_CREATED: title ? `已新增能力：${title}` : '已新增能力项',
    COMPETENCY_UPDATED: title ? `已更新能力：${title}` : '已更新能力项',
    COMPETENCY_DELETED: title ? `已删除能力：${title}` : '已删除能力项',
    CONFLICT_RESOLVED: '能力冲突已处理',
  }
  return labels[action] ?? '项目数据已更新'
}
