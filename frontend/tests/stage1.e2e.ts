import { test, expect } from '@playwright/test'

test('frontend dev server reaches the backend health endpoint', async ({ request }) => {
  const response = await request.get('/api/health')
  expect(response.status()).toBe(200)
  expect(response.headers()['content-type']).toContain('application/json')
  await expect(response.json()).resolves.toEqual({ status: 'ok' })
})

test('stage one shell exposes project and analysis controls', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('button', { name: '新建任务' })).toBeVisible()
  await expect(page.getByRole('button', { name: '运行解析' })).toBeDisabled()
  await expect(page.getByRole('button', { name: '生成总模型' })).toBeDisabled()
})

test('audit events render as readable system notices without raw JSON', async ({ page }) => {
  await page.route('**/api/projects', route => route.fulfill({ json: [{ id: 'project-notice', name: '前端岗位', status: 'COLLECTING' }] }))
  await page.route('**/api/projects/project-notice/chat/history', route => route.fulfill({ json: { messages: [] } }))
  await page.route('**/api/projects/project-notice/events', route => route.fulfill({ json: [{ id: 'event-1', action: 'JD_UPDATED', payload: JSON.stringify({ jd_id: 'hidden-id', title: '高级前端工程师 JD' }), created_at: '2026-09-10T00:00:00' }] }))
  await page.route('**/api/projects/project-notice/analysis', route => route.fulfill({ status: 404, json: { detail: '尚未解析' } }))
  await page.route('**/api/projects/project-notice/models/latest', route => route.fulfill({ status: 404, json: { detail: '尚未聚合' } }))

  await page.goto('/')
  await page.getByRole('button', { name: '前端岗位 COLLECTING' }).click()

  await expect(page.getByText('已更新 JD：高级前端工程师 JD', { exact: true })).toBeVisible()
  await expect(page.getByText(/hidden-id|\{"jd_id"/)).toHaveCount(0)
})

test('a user can hold a multi-turn conversation and confirm a destructive command', async ({ page }) => {
  const project = { id: 'project-1', name: '前端工程师岗位', status: 'COLLECTING' }
  const chatPayloads: Array<{ message: string; confirm: boolean }> = []
  await page.route('**/api/projects', async route => {
    if (route.request().method() === 'POST') return route.fulfill({ json: project })
    return route.fulfill({ json: [] })
  })
  await page.route('**/api/projects/project-1/analysis', route => route.fulfill({ status: 404, json: { detail: '尚未解析' } }))
  await page.route('**/api/projects/project-1/models/latest', route => route.fulfill({ status: 404, json: { detail: '尚未聚合' } }))
  await page.route('**/api/projects/project-1/chat', async route => {
    const payload = route.request().postDataJSON()
    chatPayloads.push(payload)
    if (payload.message.includes('移除') && !payload.confirm) {
      return route.fulfill({ json: { reply: '请确认是否移出。', operation: { action: 'REMOVE_JD', requires_confirmation: true } } })
    }
    if (payload.confirm) return route.fulfill({ json: { reply: '已移出该 JD。', operation: { action: 'REMOVE_JD' } } })
    return route.fulfill({ json: { reply: `已收到：${payload.message}` } })
  })

  await page.goto('/')
  await page.getByRole('button', { name: '新建任务' }).click()
  const composer = page.getByRole('textbox', { name: '消息' })
  await composer.fill('先解释当前阶段')
  await page.getByRole('button', { name: '发送' }).click()
  await composer.fill('再告诉我还缺什么')
  await page.getByRole('button', { name: '发送' }).click()
  await composer.fill('请移除《前端JD》')
  await page.getByRole('button', { name: '发送' }).click()
  await page.getByRole('button', { name: '确认执行' }).click()

  await expect(page.getByText('先解释当前阶段', { exact: true })).toBeVisible()
  await expect(page.getByText('再告诉我还缺什么', { exact: true })).toBeVisible()
  await expect(page.getByText('已移出该 JD。', { exact: true })).toBeVisible()
  expect(chatPayloads.at(-1)).toEqual({ message: '请移除《前端JD》', confirm: true })
})
