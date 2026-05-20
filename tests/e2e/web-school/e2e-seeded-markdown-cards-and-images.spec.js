const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario } = require('./fixtures.cjs')
const { apiJson, login, obtainAccessToken } = require('./future-advanced-coverage-helpers.cjs')

function scenario() {
  return loadE2eScenario()
}

async function screenshot(page, testInfo, name) {
  const output = testInfo.outputPath(`${name}.png`)
  await page.screenshot({ path: output, fullPage: true })
  await testInfo.attach(name, { path: output, contentType: 'image/png' })
  return output
}

test.describe('seeded markdown cards and images', () => {
  test.describe.configure({ timeout: 180_000 })

  test.beforeEach(async ({}, testInfo) => {
    const data = await resetE2eScenario()
    if (!data) {
      testInfo.skip(true, 'Missing E2E scenario; globalSetup must seed scenario.json')
    }
  })

  test('learning note rendering matches the seeded cards-and-image layout', async ({ page }, testInfo) => {
    const s = scenario()
    const owner = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const note = await apiJson('/api/learning-notes', {
      method: 'POST',
      token: owner,
      body: {
        title: `seeded-cards-${Date.now()}`,
        description: 'cards and image demo',
        subject_id: s.course_required_id,
        visibility: 'private',
        copy_from_subject_id: null,
        copy_chapters: false,
        copy_materials: false
      }
    })
    await apiJson(`/api/learning-notes/${note.id}/resources`, {
      method: 'POST',
      token: owner,
      body: {
        title: 'cards and image demo',
        content: [
          ':::example 示例用法',
          '1. 价格、配额、返回示例适合放进卡片。',
          '2. 普通正文继续使用标准 Markdown。',
          ':::',
          '',
          ':::pricing 价格说明',
          '- 输入：**$5 / M Tokens**',
          '- 输出：**$30 / M Tokens**',
          ':::',
          '',
          ':::note 插图示例',
          '![课程卡片与插图示意图](/markdown-demo-card-image.svg)',
          ':::',
          '',
          ':::tip 当前结论',
          '- 先完成最小可复现流程，再补充更复杂的图表。',
          ':::',
          '',
          ':::warning 待确认',
          '- 如果图太复杂，先用箱线图说明差异会更稳妥。',
          ':::'
        ].join('\n'),
        content_format: 'markdown',
        attachment_name: null,
        attachment_url: null,
        chapter_id: null
      }
    })

    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.goto('/learning-notes', { waitUntil: 'domcontentloaded', timeout: 60000 })

    const noteCard = page.locator('.note-card').filter({ hasText: 'seeded-cards-' }).first()
    await expect(noteCard).toBeVisible({ timeout: 20000 })
    await noteCard.click()

    const firstResource = page.locator('.outline-row__main').first()
    await expect(firstResource).toBeVisible({ timeout: 15000 })
    await firstResource.click()

    const body = page.locator('.note-article__body')
    await expect(body.locator('.md-card--example')).toBeVisible({ timeout: 15000 })
    await expect(body.locator('.md-card--pricing')).toBeVisible({ timeout: 15000 })
    await expect(body.locator('.md-card--note')).toBeVisible({ timeout: 15000 })
    await expect(body.locator('.md-card--tip')).toBeVisible({ timeout: 15000 })
    await expect(body.locator('.md-card--warning')).toBeVisible({ timeout: 15000 })
    await expect(body.locator('img').first()).toBeVisible({ timeout: 15000 })

    await screenshot(page, testInfo, 'seeded-learning-note-cards-image')
  })
})
