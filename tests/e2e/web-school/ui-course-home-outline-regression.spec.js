/**
 * Focused guard rails for the course-home material outline preview.
 *
 * The full materials page owns the editable chapter tree. The course home page
 * now renders a compact read-only outline so students can understand the course
 * material structure without leaving the dashboard-style overview. These tests
 * verify that the preview keeps the same explicit + / - expansion model.
 */
const { expect, test } = require('@playwright/test')
const { enterSeededRequiredCourse, loadE2eScenario, resetE2eScenario } = require('./fixtures.cjs')
const { apiPostJson, login, obtainAccessToken } = require('./future-advanced-coverage-helpers.cjs')

const scenario = () => loadE2eScenario()

async function createChapter(token, subjectId, title, parentId = null) {
  return apiPostJson(`/api/material-chapters?subject_id=${subjectId}`, token, {
    title,
    parent_id: parentId
  })
}

test.describe('course-home material outline preview', () => {
  test.describe.configure({ timeout: 120_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e seed; run globalSetup with E2E_DEV_SEED_TOKEN')
    }
  })

  test('student can collapse and expand course-home material chapter preview', async ({ page }) => {
    const s = scenario()
    const token = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const suffix = `${s.suffix}_${Date.now()}`
    const parentTitle = `E2E home outline parent ${suffix}`
    const childTitle = `E2E home outline child ${suffix}`
    const parent = await createChapter(token, s.course_required_id, parentTitle)
    await createChapter(token, s.course_required_id, childTitle, parent.id)

    await page.setViewportSize({ width: 1280, height: 900 })
    await login(page, s.student_plain.username, s.student_plain.password || s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)
    const treeRespPromise = page.waitForResponse(
      r =>
        r.request().method() === 'GET' &&
        r.url().includes('/api/material-chapters/tree') &&
        r.url().includes(`subject_id=${s.course_required_id}`),
      { timeout: 60000 }
    )
    await page.goto('/course-home', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await treeRespPromise

    const outline = page.getByTestId('course-home-material-outline')
    await expect(outline).toBeVisible({ timeout: 60000 })
    await expect(outline.getByText(parentTitle, { exact: true })).toBeVisible({ timeout: 60000 })
    await expect
      .poll(async () => outline.getByText(childTitle, { exact: true }).isVisible())
      .toBeTruthy()

    await page.getByTestId(`course-home-material-toggle-${parent.id}`).scrollIntoViewIfNeeded()
    await page.getByTestId(`course-home-material-toggle-${parent.id}`).click()
    await expect(outline.getByText(parentTitle, { exact: true })).toBeVisible({ timeout: 30000 })
    await expect(outline.getByText(childTitle, { exact: true })).toBeHidden({ timeout: 30000 })

    await page.getByTestId(`course-home-material-toggle-${parent.id}`).scrollIntoViewIfNeeded()
    await page.getByTestId(`course-home-material-toggle-${parent.id}`).click()
    await expect
      .poll(async () => outline.getByText(childTitle, { exact: true }).isVisible(), { timeout: 45000 })
      .toBeTruthy()
  })
})
