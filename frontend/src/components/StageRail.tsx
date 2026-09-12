export type StageStatus = 'COLLECTING' | 'ANALYZING' | 'REVIEWING' | 'CONFIRMED' | 'ARCHIVED'
export type StageNumber = 1 | 2 | 3
export function activeStage(_status?: StageStatus): 1 { return 1 }
const labels: Record<StageNumber, string> = { 1: 'JD 分析', 2: '模拟面试', 3: '人才画像' }
export type StageRailProps = { status?: StageStatus; currentStage?: StageNumber; availability?: Record<StageNumber, boolean>; onSelect?: (stage: StageNumber) => void }
export function StageRail({ status, currentStage, availability = { 1: true, 2: true, 3: false }, onSelect = () => undefined }: StageRailProps = {}) { const active = currentStage ?? activeStage(status); return <nav className="stage-rail" aria-label="评估阶段">{([1, 2, 3] as StageNumber[]).map(stage => <button type="button" key={stage} className={active === stage ? 'current' : active > stage ? 'complete' : ''} aria-current={active === stage ? 'step' : undefined} disabled={!availability[stage] && !(stage === 3 && active >= 2)} onClick={() => onSelect(stage)}>{labels[stage]}</button>)}</nav> }
