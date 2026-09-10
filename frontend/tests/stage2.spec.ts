import { test, expect } from '@playwright/test'

const baseSession = {
  id: 'session-1', session_id: 'session-1', project_id: 'project-2', model_version_id: 'model-1',
  status: 'READY', completion: 'NONE', current_competency_id: null, current_question: null,
  competencies: [{ competency_id: 'c1', name: '系统设计', status: 'PENDING', follow_up_count: 0, evidence_sufficiency: 'UNCERTAIN' }],
  turns: [], progress: { completed: 0, total: 1 }, retryable: false,
}

test('stage two preserves an answer on AI failure and allows retry', async ({ page }) => {
  await page.setViewportSize({ width: 836, height: 898 })
  let state: any = structuredClone(baseSession)
  let retry = false
  await page.route('**/api/projects', route => route.fulfill({ json: [{ id: 'project-2', name: '已确认岗位', status: 'CONFIRMED' }] }))
  await page.route('**/api/projects/project-2/chat/history', route => route.fulfill({ json: { messages: [] } }))
  await page.route('**/api/projects/project-2/events', route => route.fulfill({ json: [] }))
  await page.route('**/api/projects/project-2/analysis', route => route.fulfill({ status: 404, json: { detail: '尚未解析' } }))
  await page.route('**/api/projects/project-2/models/latest', route => route.fulfill({ status: 404, json: { detail: '尚未聚合' } }))
  await page.route('**/api/projects/project-2/assessments', async route => {
    if (route.request().method() === 'POST') return route.fulfill({ json: state })
    return route.fulfill({ json: [] })
  })
  await page.route('**/api/assessments/session-1', async route => {
    if (route.request().method() === 'GET') return route.fulfill({ json: state })
    return route.fulfill({ json: state })
  })
  await page.route('**/api/assessments/session-1/start', async route => {
    state = { ...state, status: 'IN_PROGRESS', current_competency_id: 'c1', current_question: { id: 'q1', content: '请描述一次系统设计经历。', turn_type: 'MAIN_QUESTION', covered_competency_ids: ['c1'] } }
    return route.fulfill({ json: state })
  })
  await page.route('**/api/assessments/session-1/turns', async route => {
    state = { ...state, status: 'IN_PROGRESS', retryable: true, error: 'temporary provider failure', turns: [{ id: 'a1', role: 'USER', turn_type: 'ANSWER', content: '我设计过一个高并发系统。', covered_competency_ids: ['c1'] }] }
    return route.fulfill({ json: state })
  })
  await page.route('**/api/assessments/session-1/retry', async route => {
    retry = true
    state = { ...state, retryable: false, error: undefined }
    return route.fulfill({ json: state })
  })

  await page.goto('/')
  await page.getByRole('button', { name: '已确认岗位 CONFIRMED' }).click()
  await page.getByRole('button', { name: '工作台', exact: true }).click()
  await page.getByRole('navigation', { name: '评估阶段' }).getByRole('button', { name: '模拟面试' }).click()
  await page.getByRole('complementary').filter({ hasText: 'Workbench' }).getByRole('button', { name: '关闭工作台' }).click()
  await expect(page.getByRole('button', { name: '开始测评' })).toBeVisible()
  await expect(page.getByRole('button', { name: '工作台', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '测评工作台' })).toHaveCount(1)
  await page.getByRole('button', { name: '工作台', exact: true }).click()
  await expect(page.getByRole('heading', { name: '测评工作台' })).toBeVisible()
  await page.getByRole('complementary').filter({ hasText: 'Workbench' }).getByRole('button', { name: '关闭工作台' }).click()
  await page.getByRole('button', { name: '开始测评' }).click()
  await expect(page.getByText('请描述一次系统设计经历。')).toBeVisible()
  await page.getByLabel('你的回答').fill('我设计过一个高并发系统。')
  await page.getByRole('button', { name: '提交回答' }).click()
  await expect(page.getByText('分析暂时失败，已保留你的回答。')).toBeVisible()
  await expect(page.getByText('我设计过一个高并发系统。')).toBeVisible()
  await page.getByRole('button', { name: '重试分析' }).click()
  expect(retry).toBe(true)
  await expect(page.getByText(/score|radar|profile/i)).toHaveCount(0)
})
