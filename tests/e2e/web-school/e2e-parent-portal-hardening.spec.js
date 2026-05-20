/**
 * Parent portal browser-backed hardening.
 *
 * This spec intentionally runs from the school Playwright package so it can
 * reuse the existing FastAPI seed/reset harness. The external runner starts
 * the parent Vite app when this spec name is passed.
 */
const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario } = require('./fixtures.cjs')
const { obtainAccessToken } = require('./future-advanced-coverage-helpers.cjs')

const scenario = () => loadE2eScenario()

function apiBase() {
  return (process.env.E2E_API_URL || 'http://127.0.0.1:8012').replace(/\/$/, '')
}

function parentBase() {
  return (process.env.PLAYWRIGHT_PARENT_BASE_URL || 'http://127.0.0.1:3014').replace(/\/$/, '')
}

async function apiStatus(pathname, { method = 'GET', token, body } = {}) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method,
    headers: {
      ...(body == null ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: body == null ? undefined : JSON.stringify(body)
  })
  return { status: res.status, text: await res.text() }
}

async function seedHiddenParentContent(s, hiddenPrefix) {
  const teacherToken = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
  await apiStatus(`/api/subjects/${s.course_elective_id}/students/${s.student_plain.student_row_id}`, {
    method: 'DELETE',
    token: teacherToken
  })
  const hiddenHomework = `${hiddenPrefix} hidden elective homework ${Date.now()}`
  const hiddenNotice = `${hiddenPrefix} hidden elective notice ${Date.now()}`
  const visibleNotice = `${hiddenPrefix} visible class notice ${Date.now()}`
  const hw = await apiStatus('/api/homeworks', {
    method: 'POST',
    token: teacherToken,
    body: {
      title: hiddenHomework,
      content: 'parent UI should not render this unenrolled elective homework',
      content_format: 'plain',
      class_id: s.class_id_1,
      subject_id: s.course_elective_id,
      due_date: null,
      max_score: 100,
      grade_precision: 'integer',
      auto_grading_enabled: false,
      allow_late_submission: true,
      late_submission_affects_score: false,
      max_submissions: null,
      llm_routing_spec: null
    }
  })
  expect(hw.status).toBe(200)
  const hidden = await apiStatus('/api/notifications', {
    method: 'POST',
    token: teacherToken,
    body: {
      title: hiddenNotice,
      content: 'parent UI should not render this unenrolled elective notice',
      content_format: 'plain',
      priority: 'normal',
      class_id: s.class_id_1,
      subject_id: s.course_elective_id
    }
  })
  expect(hidden.status).toBe(200)
  const visible = await apiStatus('/api/notifications', {
    method: 'POST',
    token: teacherToken,
    body: {
      title: visibleNotice,
      content: 'parent UI should render this class notice',
      content_format: 'plain',
      priority: 'normal',
      class_id: s.class_id_1
    }
  })
  expect(visible.status).toBe(200)
  return { hiddenHomework, hiddenNotice, visibleNotice }
}

async function seedVisibleParentEnrollmentContent(s, prefix) {
  const teacherToken = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
  const enrolled = await apiStatus(`/api/subjects/${s.course_elective_id}/student-self-enroll`, {
    method: 'POST',
    token: await obtainAccessToken(s.student_plain.username, s.password_teacher_student),
    body: {}
  })
  expect([200, 400]).toContain(enrolled.status)
  const visibleHomework = `${prefix} visible elective homework ${Date.now()}`
  const visibleNotice = `${prefix} visible elective notice ${Date.now()}`
  const hw = await apiStatus('/api/homeworks', {
    method: 'POST',
    token: teacherToken,
    body: {
      title: visibleHomework,
      content: 'parent UI should initially render this enrolled elective homework',
      content_format: 'plain',
      class_id: s.class_id_1,
      subject_id: s.course_elective_id,
      due_date: null,
      max_score: 100,
      grade_precision: 'integer',
      auto_grading_enabled: false,
      allow_late_submission: true,
      late_submission_affects_score: false,
      max_submissions: null,
      llm_routing_spec: null
    }
  })
  expect(hw.status).toBe(200)
  const notice = await apiStatus('/api/notifications', {
    method: 'POST',
    token: teacherToken,
    body: {
      title: visibleNotice,
      content: 'parent UI should initially render this enrolled elective notice',
      content_format: 'plain',
      priority: 'normal',
      class_id: s.class_id_1,
      subject_id: s.course_elective_id
    }
  })
  expect(notice.status).toBe(200)
  return { visibleHomework, visibleNotice, teacherToken }
}

test.describe('parent portal hardening E2E (10 cases)', () => {
  test.describe.configure({ timeout: 180_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e seed; run via scripts/playwright-external-runner.cjs')
    }
  })

  test('01 parent login binds code and loads the linked student dashboard', async ({ page }) => {
    const s = scenario()
    await page.goto(`${parentBase()}/login`)
    await page.getByRole('textbox').fill(s.parent_code)
    await page.getByRole('button').click()
    await expect(page).toHaveURL(/\/home$/, { timeout: 30000 })
    await expect(page.locator('.header')).toContainText('E2E')
    const stored = await page.evaluate(() => ({
      parentCode: localStorage.getItem('parent_code'),
      studentId: localStorage.getItem('student_id')
    }))
    expect(stored.parentCode).toBe(s.parent_code)
    expect(Number(stored.studentId)).toBe(Number(s.student_plain.student_row_id))
  })

  test('02 parent homework UI hides same-class unenrolled elective homework', async ({ page }) => {
    const s = scenario()
    const seeded = await seedHiddenParentContent(s, 'E2E_PARENT_HW')
    await page.goto(`${parentBase()}/login`)
    await page.getByRole('textbox').fill(s.parent_code)
    await page.getByRole('button').click()
    await expect(page).toHaveURL(/\/home$/, { timeout: 30000 })
    await page.goto(`${parentBase()}/homework`)
    await expect(page.locator('.homework-list')).toContainText('E2E_UI', { timeout: 30000 })
    await expect(page.locator('.homework-list')).not.toContainText(seeded.hiddenHomework)
  })

  test('03 parent notifications UI hides unenrolled elective notices but shows class notices', async ({ page }) => {
    const s = scenario()
    const seeded = await seedHiddenParentContent(s, 'E2E_PARENT_NOTICE')
    await page.goto(`${parentBase()}/login`)
    await page.getByRole('textbox').fill(s.parent_code)
    await page.getByRole('button').click()
    await expect(page).toHaveURL(/\/home$/, { timeout: 30000 })
    await page.goto(`${parentBase()}/notifications`)
    await expect(page.locator('.notification-list')).toContainText(seeded.visibleNotice, { timeout: 30000 })
    await expect(page.locator('.notification-list')).not.toContainText(seeded.hiddenNotice)
  })

  test('04 invalid parent code stays on login and does not bind local storage', async ({ page }) => {
    await page.goto(`${parentBase()}/login`)
    await page.getByRole('textbox').fill('BADCODE1')
    await page.getByRole('button').click()

    await expect(page).toHaveURL(/\/login$/, { timeout: 30000 })
    const stored = await page.evaluate(() => ({
      parentCode: localStorage.getItem('parent_code'),
      studentId: localStorage.getItem('student_id')
    }))
    expect(stored.parentCode).toBeNull()
    expect(stored.studentId).toBeNull()
  })

  test('05 revoked parent code local session is cleared on protected homework route', async ({ page }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const revoked = await apiStatus(`/api/parent/students/${s.student_plain.student_row_id}/revoke-code`, {
      method: 'DELETE',
      token: teacherToken
    })
    expect(revoked.status).toBe(200)

    await page.goto(`${parentBase()}/login`)
    await page.evaluate(({ code, student }) => {
      localStorage.setItem('parent_code', code)
      localStorage.setItem('student_name', student.name)
      localStorage.setItem('student_id', String(student.student_row_id))
    }, { code: s.parent_code, student: s.student_plain })
    await page.goto(`${parentBase()}/homework`)

    await expect(page).toHaveURL(/\/login$/, { timeout: 30000 })
    const stored = await page.evaluate(() => localStorage.getItem('parent_code'))
    expect(stored).toBeNull()
  })

  test('06 parent notification list is isolated from student JWT read state', async ({ page }) => {
    const s = scenario()
    const seeded = await seedHiddenParentContent(s, 'E2E_PARENT_READSTATE')
    const studentToken = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const list = await apiStatus('/api/notifications?page_size=100', { token: studentToken })
    expect(list.status).toBe(200)
    const visibleNotice = JSON.parse(list.text).data.find(row => row.title === seeded.visibleNotice)
    expect(visibleNotice).toBeTruthy()
    const read = await apiStatus(`/api/notifications/${visibleNotice.id}/read`, {
      method: 'POST',
      token: studentToken
    })
    expect(read.status).toBe(200)

    await page.goto(`${parentBase()}/login`)
    await page.getByRole('textbox').fill(s.parent_code)
    await page.getByRole('button').click()
    await expect(page).toHaveURL(/\/home$/, { timeout: 30000 })
    await page.goto(`${parentBase()}/notifications`)
    await expect(page.locator('.notification-list')).toContainText(seeded.visibleNotice, { timeout: 30000 })
    await expect(page.locator('.notification-list')).not.toContainText(seeded.hiddenNotice)
  })

  test('07 invalid login clears an existing stale parent binding', async ({ page }) => {
    const s = scenario()
    await page.goto(`${parentBase()}/login`)
    await page.evaluate(({ code, student }) => {
      localStorage.setItem('parent_code', code)
      localStorage.setItem('student_name', student.name)
      localStorage.setItem('student_id', String(student.student_row_id))
    }, { code: s.parent_code, student: s.student_plain })

    await page.getByRole('textbox').fill('BADCODE2')
    await page.getByRole('button').click()

    await expect(page).toHaveURL(/\/login$/, { timeout: 30000 })
    const stored = await page.evaluate(() => ({
      parentCode: localStorage.getItem('parent_code'),
      studentName: localStorage.getItem('student_name'),
      studentId: localStorage.getItem('student_id')
    }))
    expect(stored.parentCode).toBeNull()
    expect(stored.studentName).toBeNull()
    expect(stored.studentId).toBeNull()
  })

  test('08 protected route clears partial parent binding without student id', async ({ page }) => {
    const s = scenario()
    await page.goto(`${parentBase()}/login`)
    await page.evaluate((code) => {
      localStorage.setItem('parent_code', code)
      localStorage.setItem('student_name', 'stale parent')
      localStorage.removeItem('student_id')
    }, s.parent_code)

    await page.goto(`${parentBase()}/scores`)

    await expect(page).toHaveURL(/\/login$/, { timeout: 30000 })
    const stored = await page.evaluate(() => ({
      parentCode: localStorage.getItem('parent_code'),
      studentName: localStorage.getItem('student_name')
    }))
    expect(stored.parentCode).toBeNull()
    expect(stored.studentName).toBeNull()
  })

  test('09 parent homework UI drops elective rows after enrollment is removed in another session', async ({ page }) => {
    const s = scenario()
    const seeded = await seedVisibleParentEnrollmentContent(s, 'E2E_PARENT_DRIFT_HW')

    await page.goto(`${parentBase()}/login`)
    await page.getByRole('textbox').fill(s.parent_code)
    await page.getByRole('button').click()
    await expect(page).toHaveURL(/\/home$/, { timeout: 30000 })
    await page.goto(`${parentBase()}/homework`)
    await expect(page.locator('.homework-list')).toContainText(seeded.visibleHomework, { timeout: 30000 })

    const removed = await apiStatus(`/api/subjects/${s.course_elective_id}/students/${s.student_plain.student_row_id}`, {
      method: 'DELETE',
      token: seeded.teacherToken
    })
    expect([200, 404]).toContain(removed.status)

    await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(page.locator('.homework-list')).not.toContainText(seeded.visibleHomework)
  })

  test('10 parent notifications UI drops elective rows after enrollment is removed in another session', async ({ page }) => {
    const s = scenario()
    const seeded = await seedVisibleParentEnrollmentContent(s, 'E2E_PARENT_DRIFT_NOTICE')

    await page.goto(`${parentBase()}/login`)
    await page.getByRole('textbox').fill(s.parent_code)
    await page.getByRole('button').click()
    await expect(page).toHaveURL(/\/home$/, { timeout: 30000 })
    await page.goto(`${parentBase()}/notifications`)
    await expect(page.locator('.notification-list')).toContainText(seeded.visibleNotice, { timeout: 30000 })

    const removed = await apiStatus(`/api/subjects/${s.course_elective_id}/students/${s.student_plain.student_row_id}`, {
      method: 'DELETE',
      token: seeded.teacherToken
    })
    expect([200, 404]).toContain(removed.status)

    await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(page.locator('.notification-list')).not.toContainText(seeded.visibleNotice)
  })
})
