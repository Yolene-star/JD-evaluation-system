export function shouldResetWorkbenchFeedback(previousProjectId: string | undefined, nextProjectId: string | undefined): boolean {
  return previousProjectId !== nextProjectId
}
