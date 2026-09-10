export function CompetencyDetail({ name, evidence }: { name: string; evidence?: string }) { return <section className="evidence-view"><h3>{name}</h3><p>{evidence ?? '暂无证据'}</p></section> }
