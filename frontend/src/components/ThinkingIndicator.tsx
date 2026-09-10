export function ThinkingIndicator({ phase = '正在分析回答' }: { phase?: string }) { return <div className="thinking-indicator" role="status" aria-live="polite">{phase}…</div> }
