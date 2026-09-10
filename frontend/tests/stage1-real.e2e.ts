import { test, expect } from '@playwright/test'

test('real stage one flow creates materials, parses and builds a model', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: '新建任务' }).click()
  await expect(page.getByRole('button', { name: '添加材料' })).toBeEnabled()

  const addJd = async (title: string, text: string) => {
    await page.getByRole('button', { name: '添加材料' }).click()
    await page.getByRole('textbox', { name: 'JD标题' }).fill(title)
    await page.getByRole('textbox', { name: 'JD正文' }).fill(text)
    await page.getByRole('button', { name: '添加到项目' }).click()
    await expect(page.getByRole('button', { name: '添加材料' })).toBeEnabled()
  }

  await addJd('前端工程师 JD', '负责 React 组件开发与页面性能优化')
  await addJd('产品工程师 JD', '负责用户研究、需求分析与跨团队沟通')
  await page.getByRole('button', { name: '运行解析' }).click()
  await expect(page.getByText('解析完成，单份 JD 模型已刷新。')).toBeVisible()
  await page.getByRole('button', { name: '生成总模型' }).click()
  await expect(page.getByText('核心胜任力概览')).toBeVisible()
  await expect(page.getByText(/项能力/)).toBeVisible()

  await page.getByRole('button', { name: '单份 JD 模型' }).click()
  await page.getByRole('button', { name: '编辑岗位名称' }).click()
  await page.getByRole('textbox', { name: '岗位名称' }).fill('高级前端工程师 JD')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByText('岗位名称已更新为“高级前端工程师 JD”。')).toBeVisible()
  await expect(page.getByRole('combobox', { name: '选择 JD' })).toContainText('高级前端工程师 JD')
  await expect(page.getByRole('combobox', { name: '选择 JD' })).toHaveValue(/.+/)
  await expect(page.getByText(/\{"jd_id"/)).toHaveCount(0)
})
