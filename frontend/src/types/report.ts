export type ReportCompletion = 'FULL' | 'PARTIAL'
export type ReportStatus = 'GENERATING' | 'READY' | 'FAILED'
export type NarrativeStatus = 'PENDING' | 'GENERATING' | 'READY' | 'PENDING_RETRY' | 'FAILED'
export type EvaluationStatus = 'SCORED' | 'INCOMPLETE'
export type EvidenceKind = 'POSITIVE' | 'NEGATIVE' | 'MISSING' | 'UNCERTAIN'

export type ReportEvidence = {
  id: string
  kind: EvidenceKind
  text: string
  turnId?: string
  excerpt?: string
}

export type CompetencyEvaluation = {
  competencyId: string
  name: string
  status: EvaluationStatus
  score: number | null
  attainment: number | null
  level?: string
  confidence?: number | null
  rationale?: string
  evidenceIds?: string[]
  evidence?: ReportEvidence[]
  matchedIndicatorIds?: string[]
  negativeEvidenceIds?: string[]
  missingIndicatorIds?: string[]
  weight?: number
}

export type ReportNarrativeItem = { competencyId?: string; text: string; evidenceIds?: string[] }
export type ReportNarrative = {
  overview?: { text: string; evidenceIds?: string[] }
  strengths?: ReportNarrativeItem[]
  weaknesses?: ReportNarrativeItem[]
  recommendations?: ReportNarrativeItem[]
}

export type AssessmentReport = {
  id: string
  assessmentSessionId: string
  reportVersion: number
  evidencePackageId: string
  modelVersionId: string
  rubricSetId: string
  scoringRuleVersion: string
  completion: ReportCompletion
  evaluatedWeight: number
  unevaluatedWeight: number
  matchScore: number | null
  matchScoreType: 'FULL' | 'PARTIAL' | 'NONE'
  status: ReportStatus
  narrativeStatus: NarrativeStatus
  createdAt?: string
  jobTitle?: string
  evaluations: CompetencyEvaluation[]
  narrative?: ReportNarrative
  candidateBackground?: { sourceType: 'BACKGROUND_ONLY'; notice: string; education: unknown[]; projects: unknown[]; skills: unknown[]; experiences: unknown[] } | null
  scoringPolicy?: { attainmentFormula: string; partialWeightPolicy: string; incompletePolicy: string }
}
