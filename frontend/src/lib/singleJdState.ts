export function getSingleJdEmptyState(status?: string) {
  if (status === 'COMPLETED') {
    return {
      title: '解析已完成，但未识别到能力项',
      detail: '请使用 AI 重新解析或手动补充能力。',
    }
  }
  return {
    title: '尚未生成解析结果',
    detail: '运行解析后查看这份 JD 的独立模型。',
  }
}
