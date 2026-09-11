# Resume privacy and retention policy

- `DELETE /api/projects/{project_id}/resume-context` means **cancel current resume**: it marks the current project version as not current and keeps historical versions/snapshots for audit and reproducibility.
- Uploading a replacement creates a new version; existing AssessmentSession ResumeSnapshots never rebind.
- The API returns sanitized resume summaries and hashes, never `normalized_text` or original file bytes.
- Resume snapshots are `BACKGROUND_ONLY`; they must not become `EvidenceObservation`, competency state, score, or rubric input.
- Permanent deletion is intentionally separate from cancellation and is not exposed by the ordinary DELETE endpoint. It requires an explicit retention workflow that defines its impact on historical audit records.
- Logs should store parser/model version, latency, status and error codes, not resume contents or full user answers.
