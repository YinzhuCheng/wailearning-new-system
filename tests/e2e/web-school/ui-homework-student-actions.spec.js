const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario, enterSeededRequiredCourse } = require('./fixtures.cjs')
const { apiGetJson, currentSelectedCourseId, login, obtainAccessToken } = require('./future-advanced-coverage-helpers.cjs')

const scenario = () => loadE2eScenario()

test.describe('UI: homework student actions (requires globalSetup seed)', () => {
  test.describe.configure({ timeout: 120_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e/.cache/scenario.json; set E2E_DEV_SEED_TOKEN and run globalSetup')
    }
  })

  test('student: merged homework action opens submit page; dropdown opens detail', async ({ page }) => {
    const s = scenario()
    await login(page, s.student_plain.username, s.student_plain.password)

    await page.goto('/courses')
    await enterSeededRequiredCourse(page, s.suffix)
    await expect.poll(() => currentSelectedCourseId(page), { timeout: 15000 }).toBe(s.course_required_id)

    const token = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const apiRows = await apiGetJson(
      `/api/homeworks?subject_id=${s.course_required_id}&class_id=${s.class_id_1}&page=1&page_size=100`,
      token
    )
    expect((apiRows.data || []).some(row => Number(row.id) === Number(s.homework_id))).toBe(true)

    await page.goto('/homework')

    const row = page.getByRole('row', { name: new RegExp(`E2E_UI.*${s.suffix}`) }).first()
    await expect(row).toBeVisible({ timeout: 20000 })

    await Promise.all([
      page.waitForURL(new RegExp(`/homework/${s.homework_id}/submit$`), { timeout: 60000 }),
      row.getByTestId('homework-student-submit').click()
    ])

    await page.goBack()
    await expect(row).toBeVisible({ timeout: 15000 })
    await row.getByTestId('homework-student-detail').click()
    await expect(page.locator('.el-dialog').filter({ hasText: /E2E_UI/ })).toBeVisible({ timeout: 10000 })
    await page.keyboard.press('Escape')
  })

  test('student: my courses page has no duplicate current-course banner', async ({ page }) => {
    const s = scenario()
    await login(page, s.student_plain.username, s.student_plain.password)
    await page.goto('/courses')
    await expect(page.locator('text=/^\\u5f53\\u524d\\u8bfe\\u7a0b\\uff1a/')).toHaveCount(0)
  })
})
