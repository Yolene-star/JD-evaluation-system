export function ParseFailure({ onRetry }: { onRetry: () => void }) { return <section><h3>解析失败</h3><p className="muted">保留原始材料，你可以重试或重新粘贴文字。</p><button onClick={onRetry}>重试</button></section> }
