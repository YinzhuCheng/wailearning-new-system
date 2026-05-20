const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario, enterSeededRequiredCourse } = require('./fixtures.cjs')
const {
  login,
  obtainAccessToken,
  apiPostJson,
  apiPutJson,
  apiHomeworkSubmissionHistory
} = require('./future-advanced-coverage-helpers.cjs')

const scenario = () => loadE2eScenario()

async function seedAppealedSubmission() {
  const s = scenario()
  const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
  const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
  const studentReason = `E2E stale teacher appeal ${s.suffix}_${Date.now()}`

  const submission = await apiPostJson(`/api/homeworks/${s.homework_id}/submission`, studentToken, {
    content: `stale teacher appeal body ${s.suffix}_${Date.now()}`
  })
  await apiPutJson(`/api/homeworks/${s.homework_id}/submissions/${submission.id}/review`, teacherToken, {
    review_score: 81,
    review_comment: `pre stale review ${s.suffix}`
  })
  await apiPostJson(`/api/homeworks/${s.homework_id}/submissions/${submission.id}/appeal`, studentToken, {
    reason_text: studentReason
  })

  return {
    s,
    submissionId: submission.id,
    studentToken,
    studentReason
  }
}

async function openTeacherAppealDetail(page, s, submissionId, studentReason) {
  await login(page, s.teacher_own.username, s.teacher_own.password)
  await enterSeededRequiredCourse(page, s.suffix)
  await page.goto(`/homework/${s.homework_id}/submissions/${submissionId}`, {
    waitUntil: 'domcontentloaded',
    timeout: 60000
  })
  await expect(page.getByText(studentReason)).toBeVisible({ timeout: 20000 })
  await expect(page.getByRole('button', { name: '处理申诉' })).toBeVisible({ timeout: 20000 })
}

async function openAppealResolveDialog(page, responseText) {
  await page.getByRole('button', { name: '处理申诉' }).click()
  await expect(page.getByRole('dialog', { name: '处理作业申诉' })).toBeVisible({ timeout: 15000 })
  await page.getByRole('textbox').last().fill(responseText)
}

async function expectAuthoritativeAppealState(page, statusLabel, teacherResponse) {
  const reviewStudentSection = page.locator('.review-section--student')
  await expect(reviewStudentSection.getByText(statusLabel, { exact: true })).toBeVisible({ timeout: 20000 })
  await expect(reviewStudentSection.getByText(teacherResponse, { exact: true })).toBeVisible({ timeout: 20000 })
  await expect(page.getByRole('button', { name: '处理申诉' })).toHaveCount(0)
}

test.describe('E2E homework appeal stale teacher tabs', () => {
  test.describe.configure({ timeout: 240_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e seed cache; run globalSetup with E2E_DEV_SEED_TOKEN first')
    }
  })

  test('stale teacher resolve dialog refreshes to the authoritative rejected state after another tab finalizes first', async ({
    browser
  }) => {
    const { s, submissionId, studentToken, studentReason } = await seedAppealedSubmission()
    const teacherResponseA = `E2E stale reject first ${s.suffix}_${Date.now()}`
    const teacherResponseB = `E2E stale resolve second ${s.suffix}_${Date.now()}`

    const contextA = await browser.newContext()
    const contextB = await browser.newContext()
    const pageA = await contextA.newPage()
    const pageB = await contextB.newPage()
    const pageErrors = []

    pageB.on('pageerror', error => {
      pageErrors.push(String(error))
    })

    try {
      await openTeacherAppealDetail(pageA, s, submissionId, studentReason)
      await openTeacherAppealDetail(pageB, s, submissionId, studentReason)

      await pageB.getByRole('button', { name: '处理申诉' }).click()
      await expect(pageB.getByRole('dialog', { name: '处理作业申诉' })).toBeVisible({ timeout: 15000 })
      await pageB.getByRole('textbox').last().fill(teacherResponseB)

      await pageA.getByRole('button', { name: '处理申诉' }).click()
      await expect(pageA.getByRole('dialog', { name: '处理作业申诉' })).toBeVisible({ timeout: 15000 })
      await pageA.getByRole('textbox').last().fill(teacherResponseA)
      await pageA.getByRole('button', { name: '拒绝申诉' }).click()
      await expect(pageA.getByRole('dialog', { name: '处理作业申诉' })).toBeHidden({ timeout: 15000 })
      await expect(pageA.locator('.review-section--student').getByText('已拒绝', { exact: true })).toBeVisible({
        timeout: 20000
      })

      await pageB.getByRole('button', { name: '设为已处理' }).click()

      await expect(pageB.getByRole('dialog', { name: '处理作业申诉' })).toBeHidden({ timeout: 20000 })
      const reviewStudentSection = pageB.locator('.review-section--student')
      await expect(reviewStudentSection.getByText('已拒绝', { exact: true })).toBeVisible({ timeout: 20000 })
      await expect(reviewStudentSection.getByText(teacherResponseA, { exact: true })).toBeVisible({ timeout: 20000 })
      await expect(reviewStudentSection.getByText(teacherResponseB, { exact: true })).toHaveCount(0)
      await expect(pageB.getByRole('button', { name: '处理申诉' })).toHaveCount(0)

      await expect.poll(() => pageErrors.length, { timeout: 10000 }).toBe(0)

      const history = await apiHomeworkSubmissionHistory(studentToken, s.homework_id)
      expect(history.summary?.appeal_status).toBe('rejected')
      expect(history.summary?.appeal_teacher_response).toBe(teacherResponseA)
    } finally {
      await contextA.close().catch(() => {})
      await contextB.close().catch(() => {})
    }
  })

  test('stale teacher reject dialog refreshes to the authoritative resolved state after another tab finalizes first', async ({
    browser
  }) => {
    const { s, submissionId, studentToken, studentReason } = await seedAppealedSubmission()
    const teacherResponseA = `E2E stale resolve first ${s.suffix}_${Date.now()}`
    const teacherResponseB = `E2E stale reject second ${s.suffix}_${Date.now()}`

    const contextA = await browser.newContext()
    const contextB = await browser.newContext()
    const pageA = await contextA.newPage()
    const pageB = await contextB.newPage()
    const pageErrors = []

    pageB.on('pageerror', error => {
      pageErrors.push(String(error))
    })

    try {
      await openTeacherAppealDetail(pageA, s, submissionId, studentReason)
      await openTeacherAppealDetail(pageB, s, submissionId, studentReason)

      await openAppealResolveDialog(pageB, teacherResponseB)
      await openAppealResolveDialog(pageA, teacherResponseA)

      await pageA.getByRole('button', { name: '设为已处理' }).click()
      await expect(pageA.getByRole('dialog', { name: '处理作业申诉' })).toBeHidden({ timeout: 15000 })
      await expectAuthoritativeAppealState(pageA, '已处理', teacherResponseA)

      await pageB.getByRole('button', { name: '拒绝申诉' }).click()
      await expect(pageB.getByRole('dialog', { name: '处理作业申诉' })).toBeHidden({ timeout: 20000 })
      await expectAuthoritativeAppealState(pageB, '已处理', teacherResponseA)
      await expect(pageB.locator('.review-section--student').getByText(teacherResponseB, { exact: true })).toHaveCount(0)

      await expect.poll(() => pageErrors.length, { timeout: 10000 }).toBe(0)

      const history = await apiHomeworkSubmissionHistory(studentToken, s.homework_id)
      expect(history.summary?.appeal_status).toBe('resolved')
      expect(history.summary?.appeal_teacher_response).toBe(teacherResponseA)
    } finally {
      await contextA.close().catch(() => {})
      await contextB.close().catch(() => {})
    }
  })

  test('teacher review save interleaved with appeal modal resolution keeps appeal terminal state authoritative', async ({
    browser
  }) => {
    const { s, submissionId, studentToken, studentReason } = await seedAppealedSubmission()
    const appealResponse = `E2E review interleave resolve ${s.suffix}_${Date.now()}`
    const lateReviewComment = `E2E review after resolve ${s.suffix}_${Date.now()}`

    const reviewContext = await browser.newContext()
    const appealContext = await browser.newContext()
    const reviewPage = await reviewContext.newPage()
    const appealPage = await appealContext.newPage()

    try {
      await openTeacherAppealDetail(reviewPage, s, submissionId, studentReason)
      await openTeacherAppealDetail(appealPage, s, submissionId, studentReason)

      await openAppealResolveDialog(appealPage, appealResponse)
      await appealPage.getByRole('button', { name: '设为已处理' }).click()
      await expect(appealPage.getByRole('dialog', { name: '处理作业申诉' })).toBeHidden({ timeout: 15000 })
      await expectAuthoritativeAppealState(appealPage, '已处理', appealResponse)

      const gradeSection = reviewPage.locator('.review-section--grade')
      await gradeSection.getByRole('textbox').last().fill(lateReviewComment)
      await gradeSection.getByRole('button', { name: '保存评分' }).click()

      await expect(reviewPage.locator('.review-section--comment-readonly')).toContainText(lateReviewComment, {
        timeout: 20000
      })
      await expectAuthoritativeAppealState(reviewPage, '已处理', appealResponse)

      const history = await apiHomeworkSubmissionHistory(studentToken, s.homework_id)
      expect(history.summary?.appeal_status).toBe('resolved')
      expect(history.summary?.appeal_teacher_response).toBe(appealResponse)
      expect(history.summary?.review_comment).toBe(lateReviewComment)
    } finally {
      await reviewContext.close().catch(() => {})
      await appealContext.close().catch(() => {})
    }
  })

  test('terminal homework appeal detail stays non-actionable after reload and history navigation', async ({ page }) => {
    const { s, submissionId, studentToken, studentReason } = await seedAppealedSubmission()
    const teacherResponse = `E2E reload terminal appeal ${s.suffix}_${Date.now()}`

    await openTeacherAppealDetail(page, s, submissionId, studentReason)
    await openAppealResolveDialog(page, teacherResponse)
    await page.getByRole('button', { name: '设为已处理' }).click()
    await expect(page.getByRole('dialog', { name: '处理作业申诉' })).toBeHidden({ timeout: 15000 })
    await expectAuthoritativeAppealState(page, '已处理', teacherResponse)

    await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 })
    await expectAuthoritativeAppealState(page, '已处理', teacherResponse)

    await page.getByTestId('homework-submission-review-back').click()
    await expect(page).toHaveURL(new RegExp(`/homework/${s.homework_id}/submissions`), { timeout: 20000 })
    await page.getByTestId(`homework-submission-detail-${s.student_plain.username}`).click()
    await expect(page).toHaveURL(new RegExp(`/homework/${s.homework_id}/submissions/${submissionId}`), { timeout: 20000 })
    await expectAuthoritativeAppealState(page, '已处理', teacherResponse)

    const history = await apiHomeworkSubmissionHistory(studentToken, s.homework_id)
    expect(history.summary?.appeal_status).toBe('resolved')
    expect(history.summary?.appeal_teacher_response).toBe(teacherResponse)
  })
})
