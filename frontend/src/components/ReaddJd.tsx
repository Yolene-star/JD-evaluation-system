export function ReaddJd({ disabled, onReadd }: { disabled?: boolean; onReadd: () => void }) { return <button onClick={onReadd} disabled={disabled}>重新加入当前 JD</button> }
