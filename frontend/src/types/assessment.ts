export type AssessmentStatus = 'READY' | 'IN_PROGRESS' | 'PAUSED' | 'COMPLETED' | 'PARTIALLY_FINISHED' | 'FAILED'
export type AssessmentCompletion = 'NONE' | 'FULL' | 'PARTIAL'
export type EvidenceSufficiency = 'SUFFICIENT' | 'INSUFFICIENT' | 'UNCERTAIN'
export type AssessmentQuestion = { id: string; content: string; turnType: 'MAIN_QUESTION' | 'FOLLOW_UP'; coveredCompetencyIds: string[]; followUpTargetCompetencyId?: string }
export type CompetencyProgress = { competencyId: string; name: string; status: 'PENDING' | 'ASKING' | 'FOLLOW_UP' | 'SUFFICIENT' | 'EXHAUSTED' | 'INCOMPLETE'; followUpCount: number; evidenceSufficiency: EvidenceSufficiency }
export type AssessmentTurn = { id: string; role: 'SYSTEM' | 'USER'; type: 'MAIN_QUESTION' | 'ANSWER' | 'FOLLOW_UP'; content: string; coveredCompetencyIds?: string[] }
export type EvidenceGroup = { competencyId: string; competencyName: string; sufficiency: EvidenceSufficiency; observations: string[]; followUpReason?: string }
export type AssessmentSnapshot = { sessionId: string; projectId?: string; status: AssessmentStatus; completion: AssessmentCompletion; modelVersionId: string; currentQuestion?: AssessmentQuestion; competencies: CompetencyProgress[]; turns: AssessmentTurn[]; evidenceGroups?: EvidenceGroup[]; retryable: boolean; error?: string }
