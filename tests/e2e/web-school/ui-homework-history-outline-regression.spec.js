/**
 * Focused guard rails for the teacher-side homework submission history outline.
 *
 * A student submission is the parent object; each attempt is a child record with
 * a body, attachment, review result, and teacher actions. The history dialog
 * should keep attempt summaries scannable while letting teachers expand only
 * the attempt they need to inspect or grade.
 */
const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario } = require('./fixtures.cjs')
const { apiJson, login, obtainAccessToken } = require('./future-advanced-coverage-helpers.cjs')

const scenario = () => loadE2eScenario()

async function studentSubmit(token, homeworkId, content, extra = {}) {
  return apiJson(`/api/homeworks/${homeworkId}/submission`, {
    method: 'POST',
    token,
    body: { content, ...extra }
  })
}

async function teacherSubmissions(token, homeworkId) {
  return apiJson(`/api/homeworks/${homeworkId}/submissions?page=1&page_size=20`, { token })
}

test.describe('homework submission history outline', () => {
  test.describe.configure({ timeout: 120_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e seed; run globalSetup with E2E_DEV_SEED_TOKEN')
    }
  })

  test('teacher can collapse and expand an attempt without losing the summary row', async ({ page }) => {
    const s = scenario()
    const stamp = Date.now()
    const firstBody = `outline history first attempt ${stamp}`
    const secondBody = `outline history second attempt ${stamp}`

    const studentToken = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    await studentSubmit(studentToken, s.homework_id, firstBody)
    await studentSubmit(studentToken, s.homework_id, secondBody)

    const list = await teacherSubmissions(teacherToken, s.homework_id)
    const row = list.data.find(item => item.student_no === s.student_plain.username)
    expect(row?.submission_id).toBeTruthy()

    await page.setViewportSize({ width: 1280, height: 900 })
    await login(page, s.teacher_own.username, s.password_teacher_student)
    await page.goto(`/homework/${s.homework_id}/submissions`, { waitUntil: 'load', timeout: 60000 })
    await page.getByTestId(`homework-submission-history-${s.student_plain.username}`).click()

    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 15000 })
    const summary = page.getByTestId(`homework-history-attempt-preview-${row.latest_attempt_id}`)
    const body = page.getByTestId(`homework-history-attempt-body-${row.latest_attempt_id}`)
    const toggle = page.getByTestId(`homework-history-attempt-toggle-${row.latest_attempt_id}`)

    await expect(summary).toContainText(secondBody, { timeout: 15000 })
    await expect(body).toBeVisible({ timeout: 15000 })

    await toggle.click()
    await expect(summary).toBeVisible({ timeout: 15000 })
    await expect(body).toBeHidden({ timeout: 15000 })

    await toggle.click()
    await expect(body).toBeVisible({ timeout: 15000 })
    await expect(body).toContainText(secondBody, { timeout: 15000 })
  })
})
