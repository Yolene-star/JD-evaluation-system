import { test, expect } from '@playwright/test'

test('stage three renders partial report without turning incomplete into zero', async ({ page }) => {
  const session = { id: 's3', status: 'PARTIALLY_FINISHED', completion: 'PARTIAL', model_version_id: 'm1', competencies: [{ competency_id: 'c1', name: '系统设计', status: 'SUFFICIENT', follow_up_count: 0, evidence_sufficiency: 'SUFFICIENT' }], turns: [], progress: { completed: 1, total: 1 }, retryable: false }
  await page.route('**/api/projects', route => route.fulfill({ json: [{ id: 'p3', name: '阶段三岗位', status: 'CONFIRMED' }] }))
  await page.route('**/api/projects/p3/chat/history', route => route.fulfill({ json: { messages: [] } }))
  await page.route('**/api/projects/p3/events', route => route.fulfill({ json: [] }))
  await page.route('**/api/projects/p3/assessments', route => route.fulfill({ json: session }))
  await page.route('**/api/assessments/s3', route => route.fulfill({ json: session }))
  await page.route('**/api/assessment-sessions/s3/reports', route => route.fulfill({ json: [{ id: 'r3', assessment_session_id: 's3', report_version: 1, evidence_package_id: 'ep3', model_version_id: 'm1', rubric_set_id: 'rb1', scoring_rule_version: 'stage3-v1', completion: 'PARTIAL', evaluated_weight: .5, unevaluated_weight: .5, match_score: 70, match_score_type: 'PARTIAL', status: 'READY', narrative_status: 'PENDING_RETRY', evaluations: [{ competency_id: 'c1', name: '系统设计', status: 'SCORED', score: 7, attainment: .7, level: '7-8', rationale: '有证据' }, { competency_id: 'c2', name: '沟通', status: 'INCOMPLETE', score: null, attainment: null, rationale: '暂不可完全评价' }] }]}))
  await page.goto('/')
  await page.getByRole('button', { name: '阶段三岗位 CONFIRMED' }).click()
  await page.getByRole('button', { name: '进入阶段二' }).click()
  await expect(page.getByRole('button', { name: '查看阶段三报告' })).toBeVisible()
  await page.getByRole('button', { name: '查看阶段三报告' }).click()
  await expect(page.getByRole('heading', { name: '能力评价与人才画像' }).last()).toBeVisible()
  await expect(page.getByText('不可完全评价', { exact: true })).toBeVisible()
  await expect(page.getByText('70%')).toBeVisible()
})
