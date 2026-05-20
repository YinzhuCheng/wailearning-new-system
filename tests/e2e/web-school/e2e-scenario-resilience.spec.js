const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario, enterSeededRequiredCourse } = require('./fixtures.cjs')
const { clickCourseSwitcherOption, login } = require('./future-advanced-coverage-helpers.cjs')
const scenario = () => loadE2eScenario()

function apiBase() {
  return (process.env.E2E_API_URL || 'http://127.0.0.1:8012').replace(/\/$/, '')
}

function escapeRegex(text) {
  return `${text || ''}`.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

async function obtainAccessToken(username, password) {
  const body = new URLSearchParams()
  body.set('username', username)
  body.set('password', password)
  const res = await fetch(`${apiBase()}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body
  })
  if (!res.ok) {
    throw new Error(`login failed ${res.status}: ${await res.text()}`)
  }
  const data = await res.json()
  return data.access_token
}

async function apiGetJson(pathname, token) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  })
  if (!res.ok) {
    throw new Error(`GET ${pathname} failed ${res.status}: ${await res.text()}`)
  }
  return res.json()
}

async function apiPostJson(pathname, token, body) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify(body)
  })
  if (!res.ok) {
    throw new Error(`POST ${pathname} failed ${res.status}: ${await res.text()}`)
  }
  return res.json()
}

async function apiPutJson(pathname, token, body) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify(body)
  })
  if (!res.ok) {
    throw new Error(`PUT ${pathname} failed ${res.status}: ${await res.text()}`)
  }
  return res.json()
}

async function apiPatchJson(pathname, token, body) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify(body)
  })
  if (!res.ok) {
    throw new Error(`PATCH ${pathname} failed ${res.status}: ${await res.text()}`)
  }
  return res.json()
}

async function apiDelete(pathname, token) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method: 'DELETE',
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  })
  if (!res.ok) {
    throw new Error(`DELETE ${pathname} failed ${res.status}: ${await res.text()}`)
  }
  return res.json()
}

async function apiListHomeworkRows(token, subjectId) {
  const url = new URL(`${apiBase()}/api/homeworks`)
  url.searchParams.set('subject_id', String(subjectId))
  url.searchParams.set('page_size', '100')
  const res = await fetch(url.toString(), {
    headers: { Authorization: `Bearer ${token}` }
  })
  if (!res.ok) {
    throw new Error(`homeworks list failed ${res.status}: ${await res.text()}`)
  }
  const data = await res.json()
  return data.data || []
}

async function apiListCourseStudents(token, subjectId) {
  return apiGetJson(`/api/subjects/${subjectId}/students`, token)
}

async function apiGetCourseLlmConfig(token, subjectId) {
  return apiGetJson(`/api/llm-settings/courses/${subjectId}`, token)
}

async function apiSubjectNameById(token, subjectId) {
  const subject = await apiGetJson(`/api/subjects/${subjectId}`, token)
  if (!subject?.name) {
    throw new Error(`subject ${subjectId} has no name`)
  }
  return subject.name
}

async function apiHomeworkTitleById(token, homeworkId) {
  const homework = await apiGetJson(`/api/homeworks/${homeworkId}`, token)
  if (!homework?.title) {
    throw new Error(`homework ${homeworkId} has no title`)
  }
  return homework.title
}

async function apiListClasses(token) {
  return apiGetJson('/api/classes', token)
}

async function apiStudentCourseCatalog(token) {
  return apiGetJson('/api/subjects/course-catalog', token)
}

async function apiCatalogCourseNameById(token, courseId) {
  const catalog = await apiStudentCourseCatalog(token)
  const row = Array.isArray(catalog) ? catalog.find(item => Number(item.id) === Number(courseId)) : null
  if (!row?.name) {
    throw new Error(`catalog course ${courseId} not found`)
  }
  return row.name
}

async function apiHomeworkSubmissionHistory(token, homeworkId) {
  return apiGetJson(`/api/homeworks/${homeworkId}/submission/me/history`, token)
}

async function apiListNotifications(token, params = {}) {
  const url = new URL(`${apiBase()}/api/notifications`)
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value))
    }
  }
  const res = await fetch(url.toString(), {
    headers: { Authorization: `Bearer ${token}` }
  })
  if (!res.ok) {
    throw new Error(`notifications list failed ${res.status}: ${await res.text()}`)
  }
  return res.json()
}

async function apiListScoreAppeals(token, params = {}) {
  const url = new URL(`${apiBase()}/api/scores/appeals`)
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value))
    }
  }
  const res = await fetch(url.toString(), {
    headers: { Authorization: `Bearer ${token}` }
  })
  if (!res.ok) {
    throw new Error(`score appeals list failed ${res.status}: ${await res.text()}`)
  }
  return res.json()
}

async function latestNotificationFor(token, predicate, params = {}) {
  const list = await apiListNotifications(token, { page_size: 100, ...params })
  const rows = (list.data || []).filter(predicate)
  rows.sort((a, b) => Number(b.id || 0) - Number(a.id || 0))
  return rows[0] || null
}

async function apiListUsers(token) {
  return apiGetJson('/api/users', token)
}

async function apiBatchSetClass(token, userIds, classId) {
  return apiPostJson('/api/users/batch-set-class', token, {
    user_ids: userIds,
    class_id: classId
  })
}

async function apiRosterEnroll(token, subjectId, studentIds) {
  return apiPostJson(`/api/subjects/${subjectId}/roster-enroll`, token, {
    student_ids: studentIds
  })
}

async function apiFindUserIdByUsername(token, username) {
  const users = await apiListUsers(token)
  const user = users.find(row => row.username === username)
  if (!user) {
    throw new Error(`user ${username} not found`)
  }
  return user.id
}

async function currentSelectedCourseId(page) {
  return page.evaluate(() => {
    const raw = localStorage.getItem('selected_course')
    if (!raw) return null
    try {
      const parsed = JSON.parse(raw)
      return parsed?.id ?? null
    } catch {
      return null
    }
  })
}

function changePasswordSubmit(page) {
  return page.locator('.pwd-actions .el-button--primary')
}

function notificationCreateButton(page) {
  return page.locator('.notifications-page .header-actions > .el-button--primary').first()
}

function notificationMarkAllReadButton(page) {
  return page.locator('.notifications-page .header-actions .el-badge .el-button').first()
}

function notificationDialog(page) {
  return page.locator('.el-dialog').filter({ has: page.locator('.md-panel') }).last()
}

function homeworkRow(page, title) {
  return page.getByRole('row', { name: new RegExp(escapeRegex(title)) })
}

function courseCard(page, courseName) {
  return page.locator('article.course-card').filter({
    has: page.getByRole('heading', { name: courseName })
  })
}

function courseCatalogRow(page, courseName) {
  return page.locator('tr').filter({ hasText: courseName }).first()
}

/** Catalog table only (not the course-card grid below, which can repeat the same title). */
function electiveCatalogRow(page, courseName) {
  return page
    .locator('.elective-catalog-card')
    .locator('.el-table__body tbody tr')
    .filter({ hasText: courseName })
    .filter({ visible: true })
    .first()
}

async function clickElectiveCatalogEnroll(page, courseName) {
  const row = electiveCatalogRow(page, courseName)
  await expect(row).toBeVisible({ timeout: 90000 })
  const btn = row.getByRole('button').first()
  await expect(btn).toBeEnabled({ timeout: 60000 })
  await btn.click()
}

async function clickElectiveCatalogDrop(page, courseName) {
  const row = electiveCatalogRow(page, courseName)
  await expect(row).toBeVisible({ timeout: 90000 })
  const btn = row.getByRole('button').first()
  // Button stays disabled until local `courses` includes this elective (MyCourses.vue isElectiveEnrollment).
  await expect(btn).toBeEnabled({ timeout: 60000 })
  await btn.click()
}

function homeworkFormDialog(page) {
  return page.locator('.el-dialog').filter({ has: page.getByTestId('homework-form-save') }).last()
}

async function openHomeworkEditDialog(page, title) {
  const row = homeworkRow(page, title)
  await expect(row).toBeVisible({ timeout: 20000 })
  await row.getByTestId('homework-btn-edit').click()
  await expect(homeworkFormDialog(page)).toBeVisible({ timeout: 15000 })
}

/** Batch-class UI helper removed 鈥?large SQLite accumulations make Users-table selection flaky; tests use `POST /api/users/batch-set-class` instead (same backend semantics). */

async function submitSeededHomeworkAndReview(browser, s, teacherToken, options = {}) {
  const reviewScore = options.reviewScore ?? 78
  const reviewComment = options.reviewComment ?? `E2E璇勯槄_${s.suffix}_${Date.now()}`
  const content = options.content ?? `E2E鎻愪氦_${s.suffix}_${Date.now()}`
  const studentToken = options.studentToken || await obtainAccessToken(s.student_plain.username, s.student_plain.password)
  await apiPostJson(`/api/homeworks/${s.homework_id}/submission`, studentToken, {
    content,
    attachment_name: null,
    attachment_url: null,
    remove_attachment: false,
    used_llm_assist: false,
    submission_mode: 'full'
  })
  await expect
    .poll(async () => {
      const history = await apiHomeworkSubmissionHistory(studentToken, s.homework_id)
      return history.summary?.id || null
    }, { timeout: 90000 })
    .not.toBeNull()

  const history = await apiHomeworkSubmissionHistory(studentToken, s.homework_id)
  const submissionId = history.summary?.id
  if (!submissionId) {
    throw new Error('submission summary not found')
  }
  await apiPutJson(`/api/homeworks/${s.homework_id}/submissions/${submissionId}/review`, teacherToken, {
    review_score: reviewScore,
    review_comment: reviewComment
  })
  return { submissionId, content, reviewScore, reviewComment }
}

test.describe('E2E resilience scenarios', () => {
  test.describe.configure({ timeout: 300_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e/.cache/scenario.json; run with Playwright globalSetup first')
    }
  })

  test('concurrent stale homework edit converges to one final state across teacher and student views', async ({ browser }) => {
    const s = scenario()
    const intermediateTitle = `E2E骞跺彂涓棿鎬乢${s.suffix}_${Date.now()}`
    const finalTitle = `E2E骞跺彂鏈€缁堟€乢${s.suffix}_${Date.now()}`
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const initialTitle = await apiHomeworkTitleById(teacherToken, s.homework_id)

    const teacherA = await browser.newContext()
    const teacherB = await browser.newContext()
    const studentCtx = await browser.newContext()
    const pageA = await teacherA.newPage()
    const pageB = await teacherB.newPage()
    const studentPage = await studentCtx.newPage()

    try {
      await login(pageA, s.teacher_own.username, s.teacher_own.password)
      await login(pageB, s.teacher_own.username, s.teacher_own.password)

      await enterSeededRequiredCourse(pageA, s.suffix)
      await enterSeededRequiredCourse(pageB, s.suffix)
      await pageA.goto('/homework')
      await pageB.goto('/homework')

      await openHomeworkEditDialog(pageA, initialTitle)
      await pageA.getByTestId('homework-form-title').fill(finalTitle)

      await openHomeworkEditDialog(pageB, initialTitle)
      await pageB.getByTestId('homework-form-title').fill(intermediateTitle)
      await pageB.getByTestId('homework-form-save').click()
      await expect(homeworkFormDialog(pageB)).toBeHidden({ timeout: 25000 })
      await expect(homeworkRow(pageB, intermediateTitle)).toBeVisible({ timeout: 20000 })

      await pageA.getByTestId('homework-form-save').click()
      await expect(homeworkFormDialog(pageA)).toBeHidden({ timeout: 25000 })
      await expect(homeworkRow(pageA, finalTitle)).toBeVisible({ timeout: 20000 })

      await expect
        .poll(async () => {
          const rows = await apiListHomeworkRows(teacherToken, s.course_required_id)
          return {
            finalCount: rows.filter(row => row.title === finalTitle).length,
            intermediateCount: rows.filter(row => row.title === intermediateTitle).length,
            initialCount: rows.filter(row => row.title === initialTitle).length
          }
        }, { timeout: 30000 })
        .toEqual({ finalCount: 1, intermediateCount: 0, initialCount: 0 })

      await login(studentPage, s.student_plain.username, s.student_plain.password)
      await enterSeededRequiredCourse(studentPage, s.suffix)
      await studentPage.goto('/homework')
      await expect(homeworkRow(studentPage, finalTitle)).toBeVisible({ timeout: 20000 })
      await expect(homeworkRow(studentPage, intermediateTitle)).toHaveCount(0)
      await expect(homeworkRow(studentPage, initialTitle)).toHaveCount(0)
    } finally {
      await teacherA.close().catch(() => {})
      await teacherB.close().catch(() => {})
      await studentCtx.close().catch(() => {})
    }
  })

  test('retrying homework creation after API failure leaves one authoritative record', async ({ page }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const title = `E2E閲嶈瘯浣滀笟_${s.suffix}_${Date.now()}`
    const beforeRows = await apiListHomeworkRows(teacherToken, s.course_required_id)
    let failedOnce = false
    const baselineConfig = await apiGetCourseLlmConfig(teacherToken, s.course_required_id)

    await apiPutJson(`/api/llm-settings/courses/${s.course_required_id}`, teacherToken, {
      is_enabled: true,
      response_language: baselineConfig.response_language || null,
      max_input_tokens: baselineConfig.max_input_tokens,
      max_output_tokens: baselineConfig.max_output_tokens,
      system_prompt: baselineConfig.system_prompt || '',
      teacher_prompt: baselineConfig.teacher_prompt || '',
      endpoints: baselineConfig.endpoints || [],
      groups: baselineConfig.groups || []
    })

    await login(page, s.teacher_own.username, s.teacher_own.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto('/homework')

    await page.route('**/api/homeworks', async route => {
      const request = route.request()
      if (!failedOnce && request.method() === 'POST') {
        failedOnce = true
        await route.fulfill({
          status: 503,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'simulated create failure' })
        })
        return
      }
      await route.continue()
    })

    await page.getByTestId('homework-btn-create').click()
    await page.getByTestId('homework-form-title').fill(title)
    await page.getByTestId('homework-form-save').click()
    await expect(homeworkFormDialog(page)).toBeVisible({ timeout: 15000 })
    await expect(page.getByTestId('homework-form-save')).toBeEnabled({ timeout: 15000 })

    await page.getByTestId('homework-form-save').click()
    await expect(homeworkFormDialog(page)).toBeHidden({ timeout: 25000 })
    await expect(homeworkRow(page, title)).toBeVisible({ timeout: 20000 })

    const afterRows = await apiListHomeworkRows(teacherToken, s.course_required_id)
    const createdRows = afterRows.filter(row => row.title === title)
    expect(createdRows).toHaveLength(1)
    expect(afterRows).toHaveLength(beforeRows.length + 1)
  })

  test('student mid-session class migration invalidates stale course access and backend enrollment', async ({ browser }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const studentUserId = await apiFindUserIdByUsername(adminToken, s.student_plain.username)
    const classes = await apiListClasses(adminToken)
    const class2 = classes.find(row => Number(row.id) === Number(s.class_id_2))
    if (!class2) {
      throw new Error(`class ${s.class_id_2} not found`)
    }

    const studentCtx = await browser.newContext()
    const studentPage = await studentCtx.newPage()
    const requiredCourseName = await apiSubjectNameById(adminToken, s.course_required_id)

    try {
      await login(studentPage, s.student_plain.username, s.student_plain.password)
      await studentPage.goto('/courses')
      await expect(courseCard(studentPage, requiredCourseName)).toBeVisible({ timeout: 20000 })

      await apiBatchSetClass(adminToken, [studentUserId], s.class_id_2)

      await expect
        .poll(async () => {
          const me = await apiGetJson('/api/auth/me', studentToken)
          const students = await apiListCourseStudents(adminToken, s.course_required_id)
          return {
            classId: Number(me.class_id || 0),
            stillEnrolled: students.some(row => Number(row.student_id) === Number(s.student_plain.student_row_id))
          }
        }, { timeout: 30000 })
        .toEqual({ classId: Number(s.class_id_2), stillEnrolled: false })

      await studentPage.goto('/courses')
      await studentPage.reload()
      await expect(courseCard(studentPage, requiredCourseName)).toHaveCount(0)
    } finally {
      await apiBatchSetClass(adminToken, [studentUserId], s.class_id_1).catch(() => {})
      await studentCtx.close().catch(() => {})
    }
  })

  test('stale roster dialog after class migration does not enroll the moved student into the old class course', async ({ browser }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const studentUserId = await apiFindUserIdByUsername(adminToken, s.student_b.username)
    const classes = await apiListClasses(adminToken)
    const class2 = classes.find(row => Number(row.id) === Number(s.class_id_2))
    if (!class2) {
      throw new Error(`class ${s.class_id_2} not found`)
    }

    try {
      await apiBatchSetClass(adminToken, [studentUserId], s.class_id_2)
      await apiRosterEnroll(adminToken, s.course_required_id, [s.student_b.student_row_id])

      await expect
        .poll(async () => {
          const rows = await apiListCourseStudents(adminToken, s.course_required_id)
          return rows.filter(row => Number(row.student_id) === Number(s.student_b.student_row_id)).length
        }, { timeout: 30000 })
        .toBe(0)
    } finally {
      await apiBatchSetClass(adminToken, [studentUserId], s.class_id_1).catch(() => {})
    }
  })

  test('two student contexts self-enrolling the same elective remain idempotent and converge to one enrollment', async ({ browser }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const electiveName = await apiCatalogCourseNameById(studentToken, s.course_elective_id)

    const ctxA = await browser.newContext()
    const ctxB = await browser.newContext()
    const pageA = await ctxA.newPage()
    const pageB = await ctxB.newPage()

    try {
      await login(pageA, s.student_plain.username, s.student_plain.password)
      await login(pageB, s.student_plain.username, s.student_plain.password)
      await pageA.goto('/courses')
      await pageB.goto('/courses')

      await clickElectiveCatalogEnroll(pageA, electiveName)
      await clickElectiveCatalogEnroll(pageB, electiveName)

      await expect
        .poll(
          async () => {
            const catalog = await apiStudentCourseCatalog(studentToken)
            const elective = catalog.find(row => Number(row.id) === Number(s.course_elective_id))
            const students = await apiListCourseStudents(adminToken, s.course_elective_id)
            return {
              enrolledInCatalog: Boolean(elective?.is_enrolled),
              enrollmentRows: students.filter(row => Number(row.student_id) === Number(s.student_plain.student_row_id)).length
            }
          },
          { timeout: 30000, intervals: [250, 500, 1000] }
        )
        .toEqual({
          enrolledInCatalog: true,
          enrollmentRows: 1
        })
    } finally {
      await ctxA.close().catch(() => {})
      await ctxB.close().catch(() => {})
    }
  })

  test('stale self-drop from two student contexts leaves the elective removed exactly once', async ({ browser }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)

    await apiPostJson(`/api/subjects/${s.course_elective_id}/student-self-enroll`, studentToken, {})
    const electiveName = await apiCatalogCourseNameById(studentToken, s.course_elective_id)

    const ctxA = await browser.newContext()
    const ctxB = await browser.newContext()
    const pageA = await ctxA.newPage()
    const pageB = await ctxB.newPage()

    try {
      await login(pageA, s.student_plain.username, s.student_plain.password)
      await login(pageB, s.student_plain.username, s.student_plain.password)
      await pageA.goto('/courses')
      await pageB.goto('/courses')

      await clickElectiveCatalogDrop(pageA, electiveName)
      await clickElectiveCatalogDrop(pageB, electiveName)

      await expect
        .poll(
          async () => {
            const catalog = await apiStudentCourseCatalog(studentToken)
            const elective = catalog.find(row => Number(row.id) === Number(s.course_elective_id))
            const students = await apiListCourseStudents(adminToken, s.course_elective_id)
            return {
              enrolledInCatalog: Boolean(elective?.is_enrolled),
              enrollmentRows: students.filter(row => Number(row.student_id) === Number(s.student_plain.student_row_id)).length
            }
          },
          { timeout: 30000, intervals: [250, 500, 1000] }
        )
        .toEqual({
          enrolledInCatalog: false,
          enrollmentRows: 0
        })
    } finally {
      await ctxA.close().catch(() => {})
      await ctxB.close().catch(() => {})
    }
  })

  test('profile save retries cleanly after API failure and persists one final display name', async ({ page }) => {
    const s = scenario()
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const newName = `E2E閲嶈瘯鏀瑰悕_${s.suffix}_${Date.now()}`
    let failedOnce = false

    await login(page, s.student_plain.username, s.student_plain.password)
    await page.route('**/api/auth/me', async route => {
      if (!failedOnce && route.request().method() === 'PATCH') {
        failedOnce = true
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'simulated profile save failure' })
        })
        return
      }
      await route.continue()
    })

    await page.goto('/personal-settings')
    await page.getByTestId('personal-profile-real-name').fill(newName)
    await page.getByTestId('personal-profile-save').click()
    await expect(page.getByTestId('personal-profile-real-name')).toHaveValue(newName, { timeout: 15000 })
    await page.getByTestId('personal-profile-save').click()

    await expect
      .poll(async () => {
        const me = await apiGetJson('/api/auth/me', studentToken)
        return me.real_name
      }, { timeout: 30000 })
      .toBe(newName)
  })

  test('student submission retries after API failure and persists exactly one attempt', async ({ page }) => {
    const s = scenario()
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const content = `E2E閲嶈瘯鎻愪氦_${s.suffix}_${Date.now()}`
    let failedOnce = false

    await login(page, s.student_plain.username, s.student_plain.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto(`/homework/${s.homework_id}/submit`)

    await page.route(`**/api/homeworks/${s.homework_id}/submission`, async route => {
      if (!failedOnce && route.request().method() === 'POST') {
        failedOnce = true
        await route.fulfill({
          status: 504,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'simulated submission timeout' })
        })
        return
      }
      await route.continue()
    })

    await page.getByTestId('homework-submit-content').fill(content)
    await page.getByTestId('homework-submit-save').click()
    await expect(page.getByTestId('homework-submit-content')).toHaveValue(content, { timeout: 15000 })
    await page.getByTestId('homework-submit-save').click()

    await expect
      .poll(async () => {
        const history = await apiHomeworkSubmissionHistory(studentToken, s.homework_id)
        return {
          attempts: history.attempts.length,
          content: history.summary?.content || ''
        }
      }, { timeout: 30000 })
      .toEqual({
        attempts: 1,
        content
      })
  })

  test('duplicate appeal attempts from stale student pages collapse to one authoritative pending appeal', async ({ browser }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const submitContent = `E2E appeal submit ${s.suffix}_${Date.now()}`
    const appealText = `Concurrent appeal dedupe reason ${s.suffix}`

    const setupPageCtx = await browser.newContext()
    const setupPage = await setupPageCtx.newPage()
    try {
      await login(setupPage, s.student_plain.username, s.student_plain.password)
      await enterSeededRequiredCourse(setupPage, s.suffix)
      await setupPage.goto(`/homework/${s.homework_id}/submit`)
      await setupPage.getByTestId('homework-submit-content').fill(submitContent)
      await setupPage.getByTestId('homework-submit-save').click()
    } finally {
      await setupPageCtx.close().catch(() => {})
    }

    await expect
      .poll(async () => {
        const h = await apiHomeworkSubmissionHistory(studentToken, s.homework_id)
        return h.summary?.id || null
      }, { timeout: 90000 })
      .not.toBeNull()

    const history = await apiHomeworkSubmissionHistory(studentToken, s.homework_id)
    const submissionId = history.summary?.id
    if (!submissionId) {
      throw new Error('submission summary not found')
    }
    await apiPutJson(`/api/homeworks/${s.homework_id}/submissions/${submissionId}/review`, teacherToken, {
      review_score: 78,
      review_comment: `E2E before appeal review ${s.suffix}`
    })

    const ctxA = await browser.newContext()
    const ctxB = await browser.newContext()
    const pageA = await ctxA.newPage()
    const pageB = await ctxB.newPage()

    try {
      await login(pageA, s.student_plain.username, s.student_plain.password)
      await login(pageB, s.student_plain.username, s.student_plain.password)
      await enterSeededRequiredCourse(pageA, s.suffix)
      await enterSeededRequiredCourse(pageB, s.suffix)
      await pageA.goto(`/homework/${s.homework_id}/submit`)
      await pageB.goto(`/homework/${s.homework_id}/submit`)

      await pageA.getByTestId('homework-submit-open-appeal').click()
      await pageA.getByTestId('homework-submit-appeal-reason').fill(appealText)
      await pageA.getByTestId('homework-submit-appeal-confirm').click()

      await pageB.getByTestId('homework-submit-open-appeal').click()
      await pageB.getByTestId('homework-submit-appeal-reason').fill(`${appealText}_retry`)
      await pageB.getByTestId('homework-submit-appeal-confirm').click()

      await expect
        .poll(async () => {
          const fresh = await apiHomeworkSubmissionHistory(studentToken, s.homework_id)
          return fresh.summary?.appeal_status || null
        }, { timeout: 30000 })
        .toBe('pending')
    } finally {
      await ctxA.close().catch(() => {})
      await ctxB.close().catch(() => {})
    }
  })

  test('course LLM config keeps system quota out of course form and recovers cleanly after a failed save', async ({ page }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const courseName = await apiSubjectNameById(teacherToken, s.course_required_id)
    let failedOnce = false

    await login(page, s.teacher_own.username, s.teacher_own.password)
    await page.goto('/subjects')

    const row = page.getByRole('row', { name: new RegExp(escapeRegex(courseName)) })
    await expect(row).toBeVisible({ timeout: 15000 })
    await row.getByRole('button', { name: /LLM/ }).click()

    const dialog = page.getByRole('dialog', { name: /LLM/ })
    await expect(dialog).toBeVisible({ timeout: 15000 })

    const enableSwitch = dialog.getByRole('switch')
    await expect(enableSwitch).toHaveAttribute('aria-checked', 'true', { timeout: 15000 })
    await expect(dialog.locator('.attachment-help').first()).toBeVisible({ timeout: 15000 })
    await expect(dialog.getByText(/quota_timezone|estimated_chars_per_token|estimated_image_tokens/)).toHaveCount(0)
    await page.getByTestId('llm-course-enable').click()
    await expect(enableSwitch).toHaveAttribute('aria-checked', 'false')

    await page.route(`**/api/llm-settings/courses/${s.course_required_id}`, async route => {
      if (!failedOnce && route.request().method() === 'PUT') {
        failedOnce = true
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'simulated llm save failure' })
        })
        return
      }
      await route.continue()
    })

    await page.getByTestId('llm-course-save').click()
    await expect(dialog).toBeVisible({ timeout: 15000 })
    await expect(enableSwitch).toHaveAttribute('aria-checked', 'false')

    await page.getByTestId('llm-course-save').click()
    await expect(dialog).toBeHidden({ timeout: 25000 })

    await expect
      .poll(async () => {
        const config = await apiGetCourseLlmConfig(teacherToken, s.course_required_id)
        return {
          is_enabled: Boolean(config.is_enabled)
        }
      }, { timeout: 30000 })
      .toEqual({
        is_enabled: false
      })
  })

  test('student deep-link to homework submit auto-selects course context after fresh login', async ({ page }) => {
    const s = scenario()

    await login(page, s.student_plain.username, s.student_plain.password)
    await page.goto(`/homework/${s.homework_id}/submit`)

    await expect(page).toHaveURL(new RegExp(`/homework/${s.homework_id}/submit$`))
    await expect(page.getByTestId('homework-submit-content')).toBeVisible({ timeout: 20000 })
    await expect.poll(() => currentSelectedCourseId(page), { timeout: 15000 }).toBe(s.course_required_id)
  })

  test('student deep-link to student scores auto-selects course context after fresh login', async ({ page }) => {
    const s = scenario()

    await login(page, s.student_plain.username, s.student_plain.password)
    await page.goto('/student-scores')

    await expect(page).toHaveURL(/\/student-scores$/)
    await expect(page.locator('.student-scores-page')).toBeVisible({ timeout: 20000 })
    await expect(page.locator('textarea').first()).toBeVisible({ timeout: 20000 })
    await expect.poll(() => currentSelectedCourseId(page), { timeout: 15000 }).toBeTruthy()
  })

  test('student deep-link to notifications auto-selects course context after fresh login', async ({ page }) => {
    const s = scenario()

    await login(page, s.student_plain.username, s.student_plain.password)
    await page.goto('/notifications')

    await expect(page).toHaveURL(/\/notifications$/)
    await expect(page.locator('.notifications-page')).toBeVisible({ timeout: 20000 })
    await expect.poll(() => currentSelectedCourseId(page), { timeout: 15000 }).toBeTruthy()
  })

  test('student deep-link to material reader auto-selects course context after fresh login', async ({ page }) => {
    const s = scenario()

    await login(page, s.student_plain.username, s.student_plain.password)
    await page.goto(`/materials/read/${s.material_discussion_id}`)

    await expect(page).toHaveURL(new RegExp(`/materials/read/${s.material_discussion_id}$`))
    await expect(page.getByTestId('material-read-back')).toBeVisible({ timeout: 20000 })
    await expect(page.locator('.material-read-title')).toBeVisible({ timeout: 20000 })
    await expect.poll(() => currentSelectedCourseId(page), { timeout: 15000 }).toBe(s.course_required_id)
  })

  test('deep-link homework submit recovers from a stale invalid selected_course cache', async ({ page }) => {
    const s = scenario()

    await login(page, s.student_plain.username, s.student_plain.password)
    await page.evaluate(() => {
      localStorage.setItem('selected_course', JSON.stringify({ id: 999999, name: 'stale-course' }))
    })
    await page.goto(`/homework/${s.homework_id}/submit`)

    await expect(page).toHaveURL(new RegExp(`/homework/${s.homework_id}/submit$`))
    await expect(page.getByTestId('homework-submit-content')).toBeVisible({ timeout: 20000 })
    await expect.poll(() => currentSelectedCourseId(page), { timeout: 15000 }).toBe(s.course_required_id)
  })

  test('material reader deep-link recovers from a stale invalid selected_course cache', async ({ page }) => {
    const s = scenario()

    await login(page, s.student_plain.username, s.student_plain.password)
    await page.evaluate(() => {
      localStorage.setItem('selected_course', JSON.stringify({ id: 999999, name: 'stale-course' }))
    })
    await page.goto(`/materials/read/${s.material_discussion_id}`)

    await expect(page).toHaveURL(new RegExp(`/materials/read/${s.material_discussion_id}$`))
    await expect(page.getByTestId('material-read-back')).toBeVisible({ timeout: 20000 })
    await expect(page.locator('.material-read-title')).toBeVisible({ timeout: 20000 })
    await expect.poll(() => currentSelectedCourseId(page), { timeout: 15000 }).toBe(s.course_required_id)
  })

  test('parallel cold student deep-links converge across notifications, scores, homework submit, and material reader', async ({ browser }) => {
    const s = scenario()

    const notificationsCtx = await browser.newContext()
    const scoresCtx = await browser.newContext()
    const homeworkCtx = await browser.newContext()
    const materialsCtx = await browser.newContext()
    const notificationsPage = await notificationsCtx.newPage()
    const scoresPage = await scoresCtx.newPage()
    const homeworkPage = await homeworkCtx.newPage()
    const materialsPage = await materialsCtx.newPage()

    try {
      await Promise.all([
        login(notificationsPage, s.student_plain.username, s.student_plain.password),
        login(scoresPage, s.student_plain.username, s.student_plain.password),
        login(homeworkPage, s.student_plain.username, s.student_plain.password),
        login(materialsPage, s.student_plain.username, s.student_plain.password)
      ])

      await Promise.all([
        notificationsPage.goto('/notifications'),
        scoresPage.goto('/student-scores'),
        homeworkPage.goto(`/homework/${s.homework_id}/submit`),
        materialsPage.goto(`/materials/read/${s.material_discussion_id}`)
      ])

      await Promise.all([
        expect(notificationsPage).toHaveURL(/\/notifications$/, { timeout: 20000 }),
        expect(scoresPage).toHaveURL(/\/student-scores$/, { timeout: 20000 }),
        expect(homeworkPage).toHaveURL(new RegExp(`/homework/${s.homework_id}/submit$`), { timeout: 20000 }),
        expect(materialsPage).toHaveURL(new RegExp(`/materials/read/${s.material_discussion_id}$`), { timeout: 20000 })
      ])

      await Promise.all([
        expect(notificationsPage.getByTestId('sidebar-notifications')).toBeVisible({ timeout: 20000 }),
        expect(scoresPage.locator('textarea').first()).toBeVisible({ timeout: 20000 }),
        expect(homeworkPage.getByTestId('homework-submit-content')).toBeVisible({ timeout: 20000 }),
        expect(materialsPage.getByTestId('material-read-back')).toBeVisible({ timeout: 20000 })
      ])

      await Promise.all([
        expect.poll(() => currentSelectedCourseId(notificationsPage), { timeout: 15000 }).toBe(s.course_required_id),
        expect.poll(() => currentSelectedCourseId(scoresPage), { timeout: 15000 }).toBe(s.course_required_id),
        expect.poll(() => currentSelectedCourseId(homeworkPage), { timeout: 15000 }).toBe(s.course_required_id),
        expect.poll(() => currentSelectedCourseId(materialsPage), { timeout: 15000 }).toBe(s.course_required_id)
      ])
    } finally {
      await notificationsCtx.close().catch(() => {})
      await scoresCtx.close().catch(() => {})
      await homeworkCtx.close().catch(() => {})
      await materialsCtx.close().catch(() => {})
    }
  })

  test('concurrent duplicate homework appeal requests return one success and one conflict without a server error', async () => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_b.username, s.student_b.password)
    const appealText = `E2E concurrent homework appeal ${s.suffix}_${Date.now()}`
    await apiPostJson(`/api/homeworks/${s.homework_id}/submission`, studentToken, {
      content: `E2E before homework appeal ${s.suffix}_${Date.now()}`,
      attachment_name: null,
      attachment_url: null,
      remove_attachment: false,
      used_llm_assist: false,
      submission_mode: 'full'
    })

    const history = await apiHomeworkSubmissionHistory(studentToken, s.homework_id)
    const submissionId = history.summary?.id
    if (!submissionId) {
      throw new Error('submission summary not found')
    }
    await apiPutJson(`/api/homeworks/${s.homework_id}/submissions/${submissionId}/review`, teacherToken, {
      review_score: 84,
      review_comment: `E2E before concurrent homework appeal review ${s.suffix}`
    })

    const results = await Promise.all([
      fetch(`${apiBase()}/api/homeworks/${s.homework_id}/submissions/${submissionId}/appeal`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${studentToken}`
        },
        body: JSON.stringify({ reason_text: appealText })
      }),
      fetch(`${apiBase()}/api/homeworks/${s.homework_id}/submissions/${submissionId}/appeal`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${studentToken}`
        },
        body: JSON.stringify({ reason_text: `${appealText}_duplicate` })
      })
    ])
    const statuses = results.map(resp => resp.status).sort((a, b) => a - b)
    expect(statuses).toEqual([200, 400])

    await expect
      .poll(async () => {
        const history = await apiHomeworkSubmissionHistory(studentToken, s.homework_id)
        const notifications = await apiListNotifications(teacherToken, { subject_id: s.course_required_id, page_size: 100 })
        return {
          appealStatus: history.summary?.appeal_status || null,
          matchingNotifications: (notifications.data || []).filter(row =>
            row.notification_kind === 'grade_appeal' &&
            Number(row.related_homework_id) === Number(s.homework_id) &&
            Number(row.related_student_id) === Number(s.student_b.student_row_id)
          ).length
        }
      }, { timeout: 30000 })
      .toEqual({
        appealStatus: 'pending',
        matchingNotifications: 1
      })
  })

  test('teacher explicit homework appeal rejection keeps teacher detail, student history, and notification state aligned', async ({ page }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const studentReason = `E2E homework reject ${s.suffix}_${Date.now()}`
    const teacherResponse = `Rejected after rubric review ${s.suffix}_${Date.now()}`

    await apiPostJson(`/api/homeworks/${s.homework_id}/submission`, studentToken, {
      content: `E2E homework appeal rejection body ${s.suffix}_${Date.now()}`,
      attachment_name: null,
      attachment_url: null,
      remove_attachment: false,
      used_llm_assist: false,
      submission_mode: 'full'
    })

    const history = await apiHomeworkSubmissionHistory(studentToken, s.homework_id)
    const submissionId = history.summary?.id
    if (!submissionId) {
      throw new Error('submission summary not found')
    }

    await apiPutJson(`/api/homeworks/${s.homework_id}/submissions/${submissionId}/review`, teacherToken, {
      review_score: 83,
      review_comment: `before reject ${s.suffix}`
    })

    await apiPostJson(`/api/homeworks/${s.homework_id}/submissions/${submissionId}/appeal`, studentToken, {
      reason_text: studentReason
    })

    await login(page, s.teacher_own.username, s.teacher_own.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto(`/homework/${s.homework_id}/submissions`)
    await page.getByTestId(`homework-submission-detail-${s.student_plain.username}`).click()
    await expect(page).toHaveURL(new RegExp(`/homework/${s.homework_id}/submissions/${submissionId}`), { timeout: 20000 })
    await expect(page.getByText(studentReason)).toBeVisible({ timeout: 20000 })

    const reviewStudentSection = page.locator('.review-section--student')
    const appealResolveButton = reviewStudentSection.locator('.review-meta-action').last()
    await expect(appealResolveButton).toBeVisible({ timeout: 20000 })
    await appealResolveButton.click()
    const appealDialog = page.locator('.el-dialog').filter({ has: page.locator('.review-appeal-dialog textarea') }).last()
    await expect(appealDialog).toBeVisible({ timeout: 15000 })
    await appealDialog.locator('textarea').fill(teacherResponse)
    await appealDialog.locator('.el-dialog__footer .el-button--danger').click()
    await expect(appealDialog).toBeHidden({ timeout: 15000 })
    await expect(reviewStudentSection.getByText('申诉已拒绝', { exact: true })).toBeVisible({ timeout: 20000 })
    await expect(reviewStudentSection.getByText(teacherResponse, { exact: true })).toBeVisible({ timeout: 20000 })

    await expect
      .poll(async () => {
        const studentHistory = await apiHomeworkSubmissionHistory(studentToken, s.homework_id)
        const notifications = await apiListNotifications(teacherToken, { subject_id: s.course_required_id, page_size: 100 })
        const matchingNotification = (notifications.data || []).find(row =>
          row.notification_kind === 'grade_appeal' &&
          Number(row.related_homework_id) === Number(s.homework_id) &&
          Number(row.related_student_id) === Number(s.student_plain.student_row_id)
        )
        return {
          appealStatus: studentHistory.summary?.appeal_status || null,
          teacherResponse: studentHistory.summary?.appeal_teacher_response || null,
          notificationStatus: matchingNotification?.appeal_status || null,
          notificationTitle: matchingNotification?.title || ''
        }
      }, { timeout: 30000 })
      .toMatchObject({
        appealStatus: 'rejected',
        teacherResponse,
        notificationStatus: 'rejected'
      })
  })

  test('student deep-link to homework list auto-selects course context after fresh login', async ({ page }) => {
    const s = scenario()

    await login(page, s.student_plain.username, s.student_plain.password)
    await page.goto('/homework')

    await expect(page).toHaveURL(/\/homework$/)
    await expect(page.locator('.homework-page')).toBeVisible({ timeout: 20000 })
    await expect.poll(() => currentSelectedCourseId(page), { timeout: 15000 }).toBe(s.course_required_id)
  })

  test('student deep-link to notifications recovers from a stale invalid selected_course cache', async ({ page }) => {
    const s = scenario()

    await login(page, s.student_plain.username, s.student_plain.password)
    await page.evaluate(() => {
      localStorage.setItem('selected_course', JSON.stringify({ id: 999999, name: 'stale-course' }))
    })
    await page.goto('/notifications')

    await expect(page).toHaveURL(/\/notifications$/)
    await expect(page.locator('.notifications-page')).toBeVisible({ timeout: 20000 })
    await expect.poll(() => currentSelectedCourseId(page), { timeout: 15000 }).toBeTruthy()
  })

  test('concurrent score appeal requests create at most one pending row for the same component', async () => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const reasonText = `E2E score appeal ${s.suffix}_${Date.now()}`
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const payloadA = {
      semester: '2026-绉嬪',
      target_component: 'total',
      reason_text: reasonText,
      score_id: null
    }
    const payloadB = {
      semester: '2026-绉嬪',
      target_component: 'total',
      reason_text: `${reasonText}_duplicate`,
      score_id: null
    }

    const responses = await Promise.all([
      fetch(`${apiBase()}/api/scores/appeals?subject_id=${s.course_required_id}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${studentToken}`
        },
        body: JSON.stringify(payloadA)
      }),
      fetch(`${apiBase()}/api/scores/appeals?subject_id=${s.course_required_id}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${studentToken}`
        },
        body: JSON.stringify(payloadB)
      })
    ])
    const statuses = responses.map(resp => resp.status).sort((a, b) => a - b)
    expect(statuses).toEqual([200, 400])

    await expect
      .poll(async () => {
        const rows = await apiListScoreAppeals(teacherToken, {
          subject_id: s.course_required_id,
          status: 'pending'
        })
        return rows.filter(row =>
          Number(row.subject_id) === Number(s.course_required_id) &&
          row.target_component === 'total' &&
          String(row.reason_text || '').startsWith(reasonText)
        ).length
      }, { timeout: 30000 })
      .toBe(1)
  })

  test('teacher notifications contain one score-appeal row after duplicate concurrent score appeals', async () => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const reasonText = `E2E鎴愮哗閫氱煡_${s.suffix}_${Date.now()}`
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    await Promise.all([
      fetch(`${apiBase()}/api/scores/appeals?subject_id=${s.course_required_id}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${studentToken}`
        },
        body: JSON.stringify({
          semester: '2026-绉嬪',
          target_component: 'homework_avg',
          reason_text: reasonText,
          score_id: null
        })
      }),
      fetch(`${apiBase()}/api/scores/appeals?subject_id=${s.course_required_id}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${studentToken}`
        },
        body: JSON.stringify({
          semester: '2026-绉嬪',
          target_component: 'homework_avg',
          reason_text: `${reasonText}_duplicate`,
          score_id: null
        })
      })
    ])

    await expect
      .poll(async () => {
        const notifications = await apiListNotifications(teacherToken, { subject_id: s.course_required_id, page_size: 100 })
        return (notifications.data || []).filter(row =>
          row.notification_kind === 'score_grade_appeal' &&
          Number(row.subject_id) === Number(s.course_required_id) &&
          Number(row.related_student_id) === Number(s.student_plain.student_row_id) &&
          String(row.content || '').includes(reasonText)
        ).length
      }, { timeout: 30000 })
      .toBe(1)
  })

  test('teacher notifications score-appeal deep-link stays actionable after appeal resolves', async ({ page }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const semesters = await apiGetJson('/api/semesters', teacherToken)
    const semester = semesters[0]?.name || '2026鏄ュ'
    const reasonText = `E2E score appeal deeplink ${s.suffix}_${Date.now()}`

    const created = await apiPostJson(`/api/scores/appeals?subject_id=${s.course_required_id}`, studentToken, {
      semester,
      target_component: 'total',
      reason_text: reasonText,
      score_id: null
    })

    await apiPutJson(`/api/scores/appeals/${created.id}`, teacherToken, {
      teacher_response: 'resolved from red-team regression',
      status: 'resolved'
    })

    await login(page, s.teacher_own.username, s.teacher_own.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto('/notifications', { waitUntil: 'load', timeout: 60000 })

    const notification = await expect
      .poll(
        () =>
          latestNotificationFor(
            teacherToken,
            row => Number(row.related_score_appeal_id) === Number(created.id),
            { subject_id: s.course_required_id }
          ),
        { timeout: 30000 }
      )
      .not.toBeNull()
      .then(async () =>
        latestNotificationFor(
          teacherToken,
          row => Number(row.related_score_appeal_id) === Number(created.id),
          { subject_id: s.course_required_id }
        )
      )
    const targetRow = page.locator('tr').filter({ hasText: notification.title }).first()
    await expect(targetRow).toBeVisible({ timeout: 30000 })
    await page.getByTestId(`notification-appeal-action-${notification.id}`).click()

    await expect(page).toHaveURL(
      new RegExp(`/scores\\?appeal_id=${created.id}&subject_id=${s.course_required_id}|/scores\\?subject_id=${s.course_required_id}&appeal_id=${created.id}`),
      { timeout: 20000 }
    )
    await expect.poll(() => currentSelectedCourseId(page), { timeout: 15000 }).toBe(s.course_required_id)
    await expect(page.locator(`[data-testid="score-appeal-row-${created.id}"]`)).toBeVisible({ timeout: 20000 })
    await expect(page.locator('.appeal-focus-banner')).toContainText('resolved', { timeout: 20000 })
  })

  test('teacher score-appeal deep-link with a foreign subject_id does not fall back to the currently selected course', async ({ page }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const semesters = await apiGetJson('/api/semesters', teacherToken)
    const semester = semesters[0]?.name || '2026鏄ュ'
    const reasonText = `E2E missing score appeal course ${s.suffix}_${Date.now()}`

    const created = await apiPostJson(`/api/scores/appeals?subject_id=${s.course_required_id}`, studentToken, {
      semester,
      target_component: 'total',
      reason_text: reasonText,
      score_id: null
    })

    await login(page, s.teacher_own.username, s.teacher_own.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await expect.poll(() => currentSelectedCourseId(page), { timeout: 15000 }).toBe(s.course_required_id)

    await page.goto(`/scores?subject_id=${s.course_other_teacher_id}&appeal_id=${created.id}`, {
      waitUntil: 'load',
      timeout: 60000
    })

    const warning = page.getByTestId('scores-appeal-course-missing')
    await expect(warning).toBeVisible({ timeout: 20000 })
    await expect(warning).toContainText(String(created.id))
    await expect(page.locator(`[data-testid="score-appeal-row-${created.id}"]`)).toHaveCount(0)
    await expect(page.locator('.appeals-card')).toHaveCount(0)
    await expect(page.locator('.appeal-focus-banner')).toHaveCount(0)
  })

  test('teacher score-appeal deep-link with a missing appeal_id inside an accessible course is not silently treated as a successful locate', async ({ page }) => {
    const s = scenario()

    await login(page, s.teacher_own.username, s.teacher_own.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await expect.poll(() => currentSelectedCourseId(page), { timeout: 15000 }).toBe(s.course_required_id)

    await page.goto(`/scores?subject_id=${s.course_required_id}&appeal_id=999999`, {
      waitUntil: 'load',
      timeout: 60000
    })

    await expect(page.getByTestId('scores-appeal-target-missing')).toBeVisible({ timeout: 20000 })
    await expect(page.locator('.appeals-card')).toBeVisible({ timeout: 20000 })
    await expect(page.locator('[data-testid^="score-appeal-row-"]')).toHaveCount(0)
  })

  test('teacher can recover from a foreign score-appeal deep-link by manually switching to another accessible course', async ({ page }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const semesters = await apiGetJson('/api/semesters', teacherToken)
    const semester = semesters[0]?.name || '2026鏄ュ'

    await apiPostJson(`/api/scores/appeals?subject_id=${s.course_required_id}`, studentToken, {
      semester,
      target_component: 'total',
      reason_text: `E2E manual recover ${s.suffix}_${Date.now()}`,
      score_id: null
    })

    await apiPostJson(`/api/subjects/${s.course_elective_id}/student-self-enroll`, studentToken, {}).catch(() => {})

    await login(page, s.teacher_own.username, s.teacher_own.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto(`/scores?subject_id=${s.course_other_teacher_id}&appeal_id=999999`, {
      waitUntil: 'load',
      timeout: 60000
    })

    await expect(page.getByTestId('scores-appeal-course-missing')).toBeVisible({ timeout: 20000 })
    await clickCourseSwitcherOption(page, await apiSubjectNameById(teacherToken, s.course_elective_id))
    await expect.poll(() => currentSelectedCourseId(page), { timeout: 15000 }).toBe(s.course_elective_id)
    await expect(page.getByTestId('scores-appeal-course-missing')).toHaveCount(0)
    await expect(page.locator('.appeals-card')).toBeVisible({ timeout: 20000 })
  })

  test('teacher manual recovery from a foreign score-appeal deep-link clears stale query context and survives reload', async ({ page }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const semesters = await apiGetJson('/api/semesters', teacherToken)
    const semester = semesters[0]?.name || '2026鏄ュ'

    await apiPostJson(`/api/scores/appeals?subject_id=${s.course_required_id}`, studentToken, {
      semester,
      target_component: 'total',
      reason_text: `E2E manual recover reload ${s.suffix}_${Date.now()}`,
      score_id: null
    })

    await apiPostJson(`/api/subjects/${s.course_elective_id}/student-self-enroll`, studentToken, {}).catch(() => {})

    await login(page, s.teacher_own.username, s.teacher_own.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto(`/scores?subject_id=${s.course_other_teacher_id}&appeal_id=999999`, {
      waitUntil: 'load',
      timeout: 60000
    })

    await expect(page.getByTestId('scores-appeal-course-missing')).toBeVisible({ timeout: 20000 })
    await clickCourseSwitcherOption(page, await apiSubjectNameById(teacherToken, s.course_elective_id))
    await expect.poll(() => currentSelectedCourseId(page), { timeout: 15000 }).toBe(s.course_elective_id)
    await expect.poll(() => page.url(), { timeout: 15000 }).not.toContain('subject_id=')
    await expect.poll(() => page.url(), { timeout: 15000 }).not.toContain('appeal_id=')

    await page.reload({ waitUntil: 'load', timeout: 60000 })
    await expect.poll(() => currentSelectedCourseId(page), { timeout: 15000 }).toBe(s.course_elective_id)
    await expect(page.getByTestId('scores-appeal-course-missing')).toHaveCount(0)
    await expect(page.locator('.appeals-card')).toBeVisible({ timeout: 20000 })
  })

  test('teacher manual recovery from a foreign score-appeal deep-link is not re-poisoned by a later local refresh', async ({ page }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const semesters = await apiGetJson('/api/semesters', teacherToken)
    const semester = semesters[0]?.name || '2026鏄ュ'

    await apiPostJson(`/api/scores/appeals?subject_id=${s.course_required_id}`, studentToken, {
      semester,
      target_component: 'total',
      reason_text: `E2E manual recover refresh ${s.suffix}_${Date.now()}`,
      score_id: null
    })

    await apiPostJson(`/api/subjects/${s.course_elective_id}/student-self-enroll`, studentToken, {}).catch(() => {})

    await login(page, s.teacher_own.username, s.teacher_own.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto(`/scores?subject_id=${s.course_other_teacher_id}&appeal_id=999999`, {
      waitUntil: 'load',
      timeout: 60000
    })

    await expect(page.getByTestId('scores-appeal-course-missing')).toBeVisible({ timeout: 20000 })
    await clickCourseSwitcherOption(page, await apiSubjectNameById(teacherToken, s.course_elective_id))
    await expect.poll(() => currentSelectedCourseId(page), { timeout: 15000 }).toBe(s.course_elective_id)
    await page.locator('.appeals-card .card-header-inline .el-button').first().click()
    await expect(page.getByTestId('scores-appeal-course-missing')).toHaveCount(0)
    await expect(page.locator('.appeals-card')).toBeVisible({ timeout: 20000 })
    await expect.poll(() => page.url(), { timeout: 15000 }).not.toContain('subject_id=')
    await expect.poll(() => page.url(), { timeout: 15000 }).not.toContain('appeal_id=')
  })

  test('teacher explicit current-course recovery button clears a foreign score-appeal deep-link warning', async ({ page }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const semesters = await apiGetJson('/api/semesters', teacherToken)
    const semester = semesters[0]?.name || '2026鏄ュ'

    await apiPostJson(`/api/scores/appeals?subject_id=${s.course_required_id}`, studentToken, {
      semester,
      target_component: 'total',
      reason_text: `E2E same course recover ${s.suffix}_${Date.now()}`,
      score_id: null
    })

    await login(page, s.teacher_own.username, s.teacher_own.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await expect.poll(() => currentSelectedCourseId(page), { timeout: 15000 }).toBe(s.course_required_id)

    await page.goto(`/scores?subject_id=${s.course_other_teacher_id}&appeal_id=999999`, {
      waitUntil: 'load',
      timeout: 60000
    })

    await expect(page.getByTestId('scores-appeal-course-missing')).toBeVisible({ timeout: 20000 })
    await page.getByTestId('scores-appeal-use-current-course').click()
    await expect(page.getByTestId('scores-appeal-course-missing')).toHaveCount(0)
    await expect(page.locator('.appeals-card')).toBeVisible({ timeout: 20000 })
    await expect.poll(() => page.url(), { timeout: 15000 }).not.toContain('subject_id=')
    await expect.poll(() => page.url(), { timeout: 15000 }).not.toContain('appeal_id=')
  })

  test('teacher explicit current-course recovery clears stale query context and survives reload', async ({ page }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const semesters = await apiGetJson('/api/semesters', teacherToken)
    const semester = semesters[0]?.name || '2026鏄ュ'

    await apiPostJson(`/api/scores/appeals?subject_id=${s.course_required_id}`, studentToken, {
      semester,
      target_component: 'total',
      reason_text: `E2E current course recover reload ${s.suffix}_${Date.now()}`,
      score_id: null
    })

    await login(page, s.teacher_own.username, s.teacher_own.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await expect.poll(() => currentSelectedCourseId(page), { timeout: 15000 }).toBe(s.course_required_id)

    await page.goto(`/scores?subject_id=${s.course_other_teacher_id}&appeal_id=999999`, {
      waitUntil: 'load',
      timeout: 60000
    })

    await expect(page.getByTestId('scores-appeal-course-missing')).toBeVisible({ timeout: 20000 })
    await page.getByTestId('scores-appeal-use-current-course').click()
    await expect(page.getByTestId('scores-appeal-course-missing')).toHaveCount(0)
    await expect(page.locator('.appeals-card')).toBeVisible({ timeout: 20000 })
    await expect.poll(() => page.url(), { timeout: 15000 }).not.toContain('subject_id=')
    await expect.poll(() => page.url(), { timeout: 15000 }).not.toContain('appeal_id=')

    await page.reload({ waitUntil: 'load', timeout: 60000 })
    await expect.poll(() => currentSelectedCourseId(page), { timeout: 15000 }).toBe(s.course_required_id)
    await expect(page.getByTestId('scores-appeal-course-missing')).toHaveCount(0)
    await expect(page.locator('.appeals-card')).toBeVisible({ timeout: 20000 })
    await expect.poll(() => page.url(), { timeout: 15000 }).not.toContain('subject_id=')
    await expect.poll(() => page.url(), { timeout: 15000 }).not.toContain('appeal_id=')
  })

  test('student deep-link to student scores recovers from a stale invalid selected_course cache', async ({ page }) => {
    const s = scenario()

    await login(page, s.student_plain.username, s.student_plain.password)
    await page.evaluate(() => {
      localStorage.setItem('selected_course', JSON.stringify({ id: 999999, name: 'stale-course' }))
    })
    await page.goto('/student-scores')

    await expect(page).toHaveURL(/\/student-scores$/)
    await expect(page.locator('textarea').first()).toBeVisible({ timeout: 20000 })
    await expect.poll(() => currentSelectedCourseId(page), { timeout: 15000 }).toBeTruthy()
  })

  test('duplicate stale teacher roster-enroll submits create one authoritative elective enrollment', async ({ browser }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const electiveName = await apiSubjectNameById(teacherToken, s.course_elective_id)

    await apiDelete(`/api/subjects/${s.course_elective_id}/students/${s.student_b.student_row_id}`, teacherToken).catch(() => {})

    const ctxA = await browser.newContext()
    const pageA = await ctxA.newPage()

    try {
      await Promise.all([
        apiRosterEnroll(teacherToken, s.course_elective_id, [s.student_b.student_row_id]),
        apiRosterEnroll(teacherToken, s.course_elective_id, [s.student_b.student_row_id])
      ])

      await expect
        .poll(async () => {
          const rows = await apiListCourseStudents(teacherToken, s.course_elective_id)
          return rows.filter(row => Number(row.student_id) === Number(s.student_b.student_row_id)).length
        }, { timeout: 30000 })
        .toBe(1)

      await login(pageA, s.teacher_own.username, s.teacher_own.password)
      await pageA.goto('/subjects')
      await expect(pageA.getByRole('row', { name: new RegExp(escapeRegex(electiveName)) })).toBeVisible({ timeout: 15000 })
    } finally {
      await apiDelete(`/api/subjects/${s.course_elective_id}/students/${s.student_b.student_row_id}`, teacherToken).catch(() => {})
      await ctxA.close().catch(() => {})
    }
  })

  test('concurrent stale student elective drops converge to one final unenrolled state', async ({ browser }) => {
    const s = scenario()
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const electiveName = await apiCatalogCourseNameById(studentToken, s.course_elective_id)

    await apiPostJson(`/api/subjects/${s.course_elective_id}/student-self-enroll`, studentToken, {}).catch(() => {})

    await expect
      .poll(async () => {
        const catalog = await apiStudentCourseCatalog(studentToken)
        const row = catalog.find(r => Number(r.id) === Number(s.course_elective_id))
        return Boolean(row?.is_enrolled)
      }, { timeout: 45000 })
      .toBe(true)

    const ctxA = await browser.newContext()
    const ctxB = await browser.newContext()
    const pageA = await ctxA.newPage()
    const pageB = await ctxB.newPage()

    try {
      await login(pageA, s.student_plain.username, s.student_plain.password)
      await login(pageB, s.student_plain.username, s.student_plain.password)
      await pageA.goto('/courses')
      await pageB.goto('/courses')

      await clickElectiveCatalogDrop(pageA, electiveName)
      await clickElectiveCatalogDrop(pageB, electiveName)

      await expect
        .poll(async () => {
          const rows = await apiListCourseStudents(teacherToken, s.course_elective_id)
          const catalog = await apiStudentCourseCatalog(studentToken)
          const elective = catalog.find(row => Number(row.id) === Number(s.course_elective_id))
          return {
            enrollments: rows.filter(row => Number(row.student_id) === Number(s.student_plain.student_row_id)).length,
            isEnrolled: Boolean(elective?.is_enrolled)
          }
        }, { timeout: 30000 })
        .toEqual({
          enrollments: 0,
          isEnrolled: false
        })
    } finally {
      await ctxA.close().catch(() => {})
      await ctxB.close().catch(() => {})
    }
  })

  test('stale student elective page self-enroll uses the migrated class snapshot', async ({ browser }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_b.username, s.student_b.password)
    const studentUserId = await apiFindUserIdByUsername(adminToken, s.student_b.username)
    const classes = await apiListClasses(adminToken)
    const class2 = classes.find(row => Number(row.id) === Number(s.class_id_2))
    if (!class2) {
      throw new Error(`class ${s.class_id_2} not found`)
    }

    await apiDelete(`/api/subjects/${s.course_elective_id}/students/${s.student_b.student_row_id}`, teacherToken).catch(() => {})

    const studentCtx = await browser.newContext()
    const studentPage = await studentCtx.newPage()

    try {
      await login(studentPage, s.student_b.username, s.student_b.password)
      await studentPage.goto('/courses')
      const electiveName = await apiCatalogCourseNameById(studentToken, s.course_elective_id)
      await expect(courseCatalogRow(studentPage, electiveName)).toBeVisible({ timeout: 20000 })

      await apiBatchSetClass(adminToken, [studentUserId], s.class_id_2)

      await clickElectiveCatalogEnroll(studentPage, electiveName)

      await expect
        .poll(async () => {
          const me = await apiGetJson('/api/auth/me', studentToken)
          const rows = await apiListCourseStudents(teacherToken, s.course_elective_id)
          return {
            classId: Number(me.class_id || 0),
            enrollments: rows
              .filter(row => Number(row.student_id) === Number(s.student_b.student_row_id))
              .map(row => Number(row.class_id || 0))
          }
        }, { timeout: 30000 })
        .toEqual({
          classId: Number(s.class_id_2),
          enrollments: [Number(s.class_id_2)]
        })
    } finally {
      await apiBatchSetClass(adminToken, [studentUserId], s.class_id_1).catch(() => {})
      await apiDelete(`/api/subjects/${s.course_elective_id}/students/${s.student_b.student_row_id}`, teacherToken).catch(() => {})
      await studentCtx.close().catch(() => {})
    }
  })

  test('opening the same fresh notification from two stale student tabs converges to a single read state', async ({ browser }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const title = `E2E閫氱煡鍙屽紑宸茶_${s.suffix}_${Date.now()}`

    await apiPostJson('/api/notifications', teacherToken, {
      title,
      content: 'parallel read convergence',
      priority: 'important',
      is_pinned: false,
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })

    const ctxA = await browser.newContext()
    const ctxB = await browser.newContext()
    const pageA = await ctxA.newPage()
    const pageB = await ctxB.newPage()

    try {
      await login(pageA, s.student_plain.username, s.student_plain.password)
      await login(pageB, s.student_plain.username, s.student_plain.password)
      await enterSeededRequiredCourse(pageA, s.suffix)
      await enterSeededRequiredCourse(pageB, s.suffix)
      await pageA.goto('/notifications')
      await pageB.goto('/notifications')

      const rowA = pageA.locator('tr').filter({ hasText: title }).first()
      const rowB = pageB.locator('tr').filter({ hasText: title }).first()
      await expect(rowA).toBeVisible({ timeout: 20000 })
      await expect(rowB).toBeVisible({ timeout: 20000 })

      await Promise.all([rowA.click(), rowB.click()])

      await expect
        .poll(async () => {
          const list = await apiListNotifications(studentToken, { subject_id: s.course_required_id, page_size: 100 })
          const match = (list.data || []).find(row => row.title === title)
          return Boolean(match?.is_read)
        }, { timeout: 30000 })
        .toBe(true)
    } finally {
      await ctxA.close().catch(() => {})
      await ctxB.close().catch(() => {})
    }
  })

  test('dual-tab student mark-all-read leaves every fresh course notification read', async ({ browser }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const titles = [
      `E2E閫氱煡鎵归噺宸茶A_${s.suffix}_${Date.now()}`,
      `E2E閫氱煡鎵归噺宸茶B_${s.suffix}_${Date.now()}`
    ]

    for (const title of titles) {
      await apiPostJson('/api/notifications', teacherToken, {
        title,
        content: 'mark-all-read convergence',
        priority: 'normal',
        is_pinned: false,
        class_id: s.class_id_1,
        subject_id: s.course_required_id
      })
    }

    const ctxA = await browser.newContext()
    const ctxB = await browser.newContext()
    const pageA = await ctxA.newPage()
    const pageB = await ctxB.newPage()

    try {
      await login(pageA, s.student_plain.username, s.student_plain.password)
      await login(pageB, s.student_plain.username, s.student_plain.password)
      await enterSeededRequiredCourse(pageA, s.suffix)
      await enterSeededRequiredCourse(pageB, s.suffix)
      await pageA.goto('/notifications')
      await pageB.goto('/notifications')

      const markAllUrl = new URL(`${apiBase()}/api/notifications/mark-all-read`)
      markAllUrl.searchParams.set('subject_id', String(s.course_required_id))
      await Promise.all([
        fetch(markAllUrl.toString(), { method: 'POST', headers: { Authorization: `Bearer ${studentToken}` } }),
        fetch(markAllUrl.toString(), { method: 'POST', headers: { Authorization: `Bearer ${studentToken}` } }),
        fetch(markAllUrl.toString(), { method: 'POST', headers: { Authorization: `Bearer ${studentToken}` } })
      ])

      await expect
        .poll(async () => {
          const list = await apiListNotifications(studentToken, { subject_id: s.course_required_id, page_size: 100 })
          return titles.map(title => {
            const row = (list.data || []).find(item => item.title === title)
            return Boolean(row?.is_read)
          })
        }, { timeout: 45000 })
        .toEqual([true, true])
    } finally {
      await ctxA.close().catch(() => {})
      await ctxB.close().catch(() => {})
    }
  })

  test('profile save retries after a transient failure and persists one final display name', async ({ page }) => {
    const s = scenario()
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const originalName = (await apiGetJson('/api/auth/me', studentToken)).real_name
    const nextName = `E2E鏀瑰悕閲嶈瘯_${s.suffix}_${Date.now()}`
    let failedOnce = false

    try {
      await login(page, s.student_plain.username, s.student_plain.password)
      await page.goto('/personal-settings')

      await page.route('**/api/auth/me', async route => {
        if (!failedOnce && route.request().method() === 'PATCH') {
          failedOnce = true
          await route.fulfill({
            status: 503,
            contentType: 'application/json',
            body: JSON.stringify({ detail: 'simulated profile save failure' })
          })
          return
        }
        await route.continue()
      })

      await page.getByTestId('personal-profile-real-name').fill(nextName)
      await page.getByTestId('personal-profile-save').click()
      await expect(page.getByTestId('personal-profile-real-name')).toHaveValue(nextName, { timeout: 15000 })
      await page.getByTestId('personal-profile-save').click()

      await expect
        .poll(async () => (await apiGetJson('/api/auth/me', studentToken)).real_name, { timeout: 30000 })
        .toBe(nextName)
    } finally {
      await apiPatchJson('/api/auth/me', studentToken, { real_name: originalName }).catch(() => {})
    }
  })

  test('stale dual-tab profile saves converge to the last submitted display name', async ({ browser }) => {
    const s = scenario()
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const originalName = (await apiGetJson('/api/auth/me', studentToken)).real_name
    const intermediateName = `E2E涓汉璁剧疆涓棿鎬乢${s.suffix}_${Date.now()}`
    const finalName = `E2E涓汉璁剧疆鏈€缁堟€乢${s.suffix}_${Date.now()}`

    const ctxA = await browser.newContext()
    const ctxB = await browser.newContext()
    const pageA = await ctxA.newPage()
    const pageB = await ctxB.newPage()

    try {
      await login(pageA, s.student_plain.username, s.student_plain.password)
      await login(pageB, s.student_plain.username, s.student_plain.password)
      await pageA.goto('/personal-settings')
      await pageB.goto('/personal-settings')

      await pageA.getByTestId('personal-profile-real-name').fill(finalName)
      await pageB.getByTestId('personal-profile-real-name').fill(intermediateName)
      await pageB.getByTestId('personal-profile-save').click()
      await expect
        .poll(async () => (await apiGetJson('/api/auth/me', studentToken)).real_name, { timeout: 45000 })
        .toBe(intermediateName)
      await pageA.getByTestId('personal-profile-save').click()

      await expect
        .poll(async () => (await apiGetJson('/api/auth/me', studentToken)).real_name, { timeout: 45000 })
        .toBe(finalName)
    } finally {
      await apiPatchJson('/api/auth/me', studentToken, { real_name: originalName }).catch(() => {})
      await ctxA.close().catch(() => {})
      await ctxB.close().catch(() => {})
    }
  })

  test('password change can recover from a wrong-current-password attempt and invalidates the old password', async ({ page }) => {
    const s = scenario()
    const nextPassword = `TempPass_${Date.now()}!`

    try {
      await login(page, s.student_plain.username, s.student_plain.password)
      await page.goto('/personal-settings')

      const passwordInputs = page.locator('input[type="password"]')
      await passwordInputs.nth(0).fill('definitely-wrong-password')
      await passwordInputs.nth(1).fill(nextPassword)
      await passwordInputs.nth(2).fill(nextPassword)
      await changePasswordSubmit(page).click()

      await passwordInputs.nth(0).fill(s.student_plain.password)
      await passwordInputs.nth(1).fill(nextPassword)
      await passwordInputs.nth(2).fill(nextPassword)
      await changePasswordSubmit(page).click()

      await expect
        .poll(async () => {
          try {
            await obtainAccessToken(s.student_plain.username, s.student_plain.password)
            return 'old-still-valid'
          } catch {
            await obtainAccessToken(s.student_plain.username, nextPassword)
            return 'new-only'
          }
        }, { timeout: 30000 })
        .toBe('new-only')
    } finally {
      const newToken = await obtainAccessToken(s.student_plain.username, nextPassword).catch(() => null)
      if (newToken) {
        await apiPostJson('/api/auth/change-password', newToken, {
          current_password: nextPassword,
          new_password: s.student_plain.password,
          confirm_password: s.student_plain.password
        }).catch(() => {})
      }
    }
  })

  test('retrying notification publish after API failure leaves one authoritative notification row', async ({ page }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const title = `E2E閫氱煡閲嶈瘯_${s.suffix}_${Date.now()}`
    let failedOnce = false

    await login(page, s.teacher_own.username, s.teacher_own.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto('/notifications')

    await page.route('**/api/notifications', async route => {
      const request = route.request()
      if (!failedOnce && request.method() === 'POST') {
        failedOnce = true
        await route.fulfill({
          status: 503,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'simulated notification create failure' })
        })
        return
      }
      await route.continue()
    })

    await notificationCreateButton(page).click()
    const dialog = notificationDialog(page)
    await expect(dialog).toBeVisible({ timeout: 15000 })
    await dialog.locator('input').first().fill(title)
    await dialog.locator('textarea').first().fill('notification retry convergence')
    await dialog.locator('.el-dialog__footer .el-button--primary').click()
    await expect(dialog).toBeVisible({ timeout: 15000 })
    await dialog.locator('.el-dialog__footer .el-button--primary').click()
    await expect(dialog).toBeHidden({ timeout: 25000 })

    await expect
      .poll(async () => {
        const list = await apiListNotifications(teacherToken, { subject_id: s.course_required_id, page_size: 100 })
        return (list.data || []).filter(row => row.title === title).length
      }, { timeout: 30000 })
      .toBe(1)
  })

  test('opening notifications after a stale selected_course cache still preserves fresh read state after mark-all-read', async ({ page }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const title = `E2E閫氱煡鑴忕紦瀛樺凡璇籣${s.suffix}_${Date.now()}`

    await apiPostJson('/api/notifications', teacherToken, {
      title,
      content: 'stale selected course recovery',
      priority: 'normal',
      is_pinned: false,
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })

    await login(page, s.student_plain.username, s.student_plain.password)
    await page.evaluate(() => {
      localStorage.setItem('selected_course', JSON.stringify({ id: 999999, name: 'stale-course' }))
    })
    await page.goto('/notifications')
    await expect.poll(() => currentSelectedCourseId(page), { timeout: 15000 }).toBeTruthy()
    await notificationMarkAllReadButton(page).click()

    await expect
      .poll(async () => {
        const list = await apiListNotifications(studentToken, { subject_id: s.course_required_id, page_size: 100 })
        const row = (list.data || []).find(item => item.title === title)
        return Boolean(row?.is_read)
      }, { timeout: 30000 })
      .toBe(true)
  })

  test('notifications detail click recovers when teacher deletes the row before the fetch completes', async ({ page }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const title = `E2E閫氱煡鐐瑰嚮鍒犺_${s.suffix}_${Date.now()}`

    const pageErrors = []
    page.on('pageerror', error => {
      pageErrors.push(String(error))
    })

    const row = await apiPostJson('/api/notifications', teacherToken, {
      title,
      content: 'delete-mid-click',
      priority: 'normal',
      is_pinned: false,
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })

    await login(page, s.student_plain.username, s.student_plain.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto('/notifications', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(page.locator('.notifications-page')).toBeVisible({ timeout: 20000 })

    let deletedBeforeDetailFetch = false
    await page.route(`**/api/notifications/${row.id}`, async route => {
      if (!deletedBeforeDetailFetch && route.request().method() === 'GET') {
        deletedBeforeDetailFetch = true
        await apiDelete(`/api/notifications/${row.id}`, teacherToken).catch(() => {})
      }
      await route.continue()
    })

    const targetRow = page.locator('tr').filter({ hasText: title }).first()
    await expect(targetRow).toBeVisible({ timeout: 20000 })
    await targetRow.click()

    await expect.poll(async () => pageErrors.length, { timeout: 15000 }).toBe(0)
    await expect(page).toHaveURL(/\/notifications$/, { timeout: 20000 })
    await expect(page.locator('.notifications-page')).toBeVisible({ timeout: 20000 })
    await expect(page.locator('body')).toBeVisible()
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(page.locator('.notifications-page')).toBeVisible({ timeout: 20000 })
  })

  test('notifications mark-all-read remains stable when a teacher deletes one unread row mid-flight', async ({ page }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const pageErrors = []
    page.on('pageerror', error => {
      pageErrors.push(String(error))
    })

    const created = []
    for (const suffix of ['A', 'B']) {
      created.push(
        await apiPostJson('/api/notifications', teacherToken, {
          title: `E2E閫氱煡鎵归噺鍒犻櫎_${suffix}_${s.suffix}_${Date.now()}`,
          content: 'mark-all-read delete race',
          priority: 'normal',
          is_pinned: false,
          class_id: s.class_id_1,
          subject_id: s.course_required_id
        })
      )
    }

    await login(page, s.student_plain.username, s.student_plain.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto('/notifications', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(page.locator('.notifications-page')).toBeVisible({ timeout: 20000 })

    const targetRow = page.locator('tr').filter({ hasText: created[0].title }).first()
    await expect(targetRow).toBeVisible({ timeout: 20000 })

    const markAllUrl = new URL(`${apiBase()}/api/notifications/mark-all-read`)
    markAllUrl.searchParams.set('subject_id', String(s.course_required_id))
    await Promise.all([
      notificationMarkAllReadButton(page).click(),
      apiDelete(`/api/notifications/${created[0].id}`, teacherToken).catch(() => {})
    ])

    await expect.poll(async () => pageErrors.length, { timeout: 15000 }).toBe(0)
    await expect(page).toHaveURL(/\/notifications$/, { timeout: 20000 })
    const sync = await fetch(`${apiBase()}/api/notifications/sync-status?subject_id=${s.course_required_id}`, {
      headers: { Authorization: `Bearer ${studentToken}` }
    }).then(res => res.json())
    expect(Number(sync.unread_count)).toBeGreaterThanOrEqual(0)
    await expect(page.locator('.notifications-page')).toBeVisible({ timeout: 20000 })
    await expect(page.locator('body')).toBeVisible()
  })

  test('teacher homework appeal detail stays consistent after a terminal review transition and reload', async ({ page }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const studentReason = `E2E homework appeal detail ${s.suffix}_${Date.now()}`
    const teacherResponse = `E2E homework detail resolved ${s.suffix}_${Date.now()}`

    const submission = await apiPostJson(`/api/homeworks/${s.homework_id}/submission`, studentToken, {
      content: `appeal detail ${s.suffix}_${Date.now()}`
    })
    await apiPutJson(`/api/homeworks/${s.homework_id}/submissions/${submission.id}/review`, teacherToken, {
      review_score: 82,
      review_comment: 'before detail consistency'
    })
    await apiPostJson(`/api/homeworks/${s.homework_id}/submissions/${submission.id}/appeal`, studentToken, {
      reason_text: studentReason
    })

    await login(page, s.teacher_own.username, s.teacher_own.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto(`/homework/${s.homework_id}/submissions/${submission.id}`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    const pageAppealText = page.locator('.submission-review-page .review-appeal-text')
    await expect(pageAppealText.filter({ hasText: studentReason }).first()).toBeVisible({ timeout: 20000 })

    await page.locator('.review-meta-action.el-button--danger').click()
    await page.getByRole('textbox').last().fill(teacherResponse)
    await page.locator('.el-dialog__footer .el-button--primary').last().click()

    await expect(pageAppealText.filter({ hasText: studentReason }).first()).toBeVisible({ timeout: 20000 })
    await expect(pageAppealText.filter({ hasText: teacherResponse }).first()).toBeVisible({ timeout: 20000 })

    await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(pageAppealText.filter({ hasText: studentReason }).first()).toBeVisible({ timeout: 20000 })
    await expect(pageAppealText.filter({ hasText: teacherResponse }).first()).toBeVisible({ timeout: 20000 })
    const history = await apiHomeworkSubmissionHistory(studentToken, s.homework_id)
    expect(history.summary?.appeal_status).toBe('resolved')
    expect(history.summary?.appeal_teacher_response).toBe(teacherResponse)
  })

  test('admin stale batch-class flip-flop converges to the last move and restores the student course access', async ({ browser }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const studentUserId = await apiFindUserIdByUsername(adminToken, s.student_plain.username)
    const classes = await apiListClasses(adminToken)
    const class1 = classes.find(row => Number(row.id) === Number(s.class_id_1))
    const class2 = classes.find(row => Number(row.id) === Number(s.class_id_2))
    if (!class1 || !class2) {
      throw new Error('expected seed classes not found')
    }

    const studentCtx = await browser.newContext()
    const studentPage = await studentCtx.newPage()
    const requiredCourseName = await apiCatalogCourseNameById(studentToken, s.course_required_id)

    try {
      await login(studentPage, s.student_plain.username, s.student_plain.password)

      await apiBatchSetClass(adminToken, [studentUserId], s.class_id_2)

      await expect
        .poll(async () => {
          const me = await apiGetJson('/api/auth/me', studentToken)
          return Number(me.class_id || 0)
        }, { timeout: 45000 })
        .toBe(Number(s.class_id_2))

      await apiBatchSetClass(adminToken, [studentUserId], s.class_id_1)

      await expect
        .poll(async () => {
          const me = await apiGetJson('/api/auth/me', studentToken)
          const catalog = await apiStudentCourseCatalog(studentToken)
          return {
            classId: Number(me.class_id || 0),
            requiredVisible: catalog.some(row => Number(row.id) === Number(s.course_required_id))
          }
        }, { timeout: 45000 })
        .toEqual({
          classId: Number(s.class_id_1),
          requiredVisible: true
        })

      await studentPage.goto('/courses')
      await expect(courseCatalogRow(studentPage, requiredCourseName)).toBeVisible({ timeout: 20000 })
    } finally {
      await apiBatchSetClass(adminToken, [studentUserId], s.class_id_1).catch(() => {})
      await studentCtx.close().catch(() => {})
    }
  })
})
