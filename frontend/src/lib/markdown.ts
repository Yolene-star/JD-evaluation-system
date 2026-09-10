export type MarkdownBlock = { type: 'heading' | 'paragraph' | 'ordered-list' | 'unordered-list'; level?: number; text?: string; items?: string[] }

export function parseMarkdown(source: string): MarkdownBlock[] {
  const lines = source.replace(/\r/g, '').split('\n'); const blocks: MarkdownBlock[] = []; let index = 0
  while (index < lines.length) {
    const line = lines[index].trim(); if (!line) { index++; continue }
    const heading = line.match(/^(#{1,6})\s+(.+)$/); if (heading) { blocks.push({ type: 'heading', level: heading[1].length, text: heading[2] }); index++; continue }
    const ordered = line.match(/^\d+[.)]\s+(.+)$/); if (ordered) { const items: string[] = []; while (index < lines.length) { const item = lines[index].trim().match(/^\d+[.)]\s+(.+)$/); if (!item) break; items.push(item[1]); index++ } blocks.push({ type: 'ordered-list', items }); continue }
    const unordered = line.match(/^[-*+]\s+(.+)$/); if (unordered) { const items: string[] = []; while (index < lines.length) { const item = lines[index].trim().match(/^[-*+]\s+(.+)$/); if (!item) break; items.push(item[1]); index++ } blocks.push({ type: 'unordered-list', items }); continue }
    const paragraphs = [line]; index++; while (index < lines.length && lines[index].trim() && !/^(#{1,6})\s+/.test(lines[index].trim()) && !/^\d+[.)]\s+/.test(lines[index].trim()) && !/^[-*+]\s+/.test(lines[index].trim())) { paragraphs.push(lines[index].trim()); index++ } blocks.push({ type: 'paragraph', text: paragraphs.join('\n') })
  }
  return blocks
}
