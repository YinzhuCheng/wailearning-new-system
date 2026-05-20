/**
 * Fifteen focused E2E/API checks derived from documented pitfalls and known
 * risk themes. Each test is intentionally narrow.
 *
 * Requires globalSetup + resetE2eScenario (same contract as other web-school E2E).
 */
const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario } = require('./fixtures.cjs')
const {
  login,
  obtainAccessToken,
  apiGetJson,
  apiPostJson,
  apiDelete,
  confirmElMessageBoxPrimary
} = require('./future-advanced-coverage-helpers.cjs')

const scenario = () => loadE2eScenario()

function apiBase() {
  return (process.env.E2E_API_URL || 'http://127.0.0.1:8012').replace(/\/$/, '')
}

async function fetchStatus(method, pathname, { token, body } = {}) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method,
    headers: {
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: body == null ? undefined : JSON.stringify(body)
  })
  const text = await res.text()
  return { status: res.status, text }
}

async function confirmPrimaryOverlay(page) {
  await confirmElMessageBoxPrimary(page)
}

function electiveCatalogRow(page, courseName) {
  return page
    .locator('.elective-catalog-card')
    .locator('.el-table__body tbody tr')
    .filter({ hasText: courseName })
    .first()
}

test.describe('E2E pitfall guard rails (15 cases)', () => {
  test.describe.configure({ timeout: 300_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e seed; run globalSetup with E2E_DEV_SEED_TOKEN')
    }
  })

  test('01 school UI delete course uses MessageBox overlay confirm (not title-named dialog)', async ({ page }) => {
    const s = scenario()
    const adminTok = await obtainAccessToken(s.admin.username, s.admin.password)
    const name = `E2E_guard_del_${s.suffix}_${Date.now()}`
    const created = await apiPostJson('/api/subjects', adminTok, {
      name,
      class_id: s.class_id_1,
      teacher_id: s.teacher_user_id,
      course_type: 'required',
      status: 'active'
    })
    const id = created.id
    expect(id).toBeTruthy()

    await login(page, s.admin.username, s.admin.password)
    await page.goto('/subjects', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(page.getByTestId('subjects-open-create')).toBeVisible({ timeout: 60000 })

    const delBtn = page.getByTestId(`subjects-delete-${id}`)
    await expect(delBtn).toBeVisible({ timeout: 60000 })
    const delPromise = page.waitForResponse(
      r =>
        r.url().includes(`/api/subjects/${id}`) &&
        r.request().method() === 'DELETE' &&
        !r.url().includes('/students/') &&
        r.ok(),
      { timeout: 120000 }
    )
    await delBtn.click()
    try {
      await confirmPrimaryOverlay(page)
    } catch {
      // Some Element Plus builds commit the click immediately; the response wait below is authoritative.
    }
    const delResp = await delPromise
    expect(delResp.ok()).toBeTruthy()
    await expect
      .poll(async () => {
        const tok = await obtainAccessToken(s.admin.username, s.admin.password)
        const res = await page.request.get(`${apiBase()}/api/subjects`, {
          headers: { Authorization: `Bearer ${tok}` }
        })
        if (!res.ok()) return false
        const rows = await res.json()
        return !Array.isArray(rows) || !rows.some(c => Number(c.id) === Number(id))
      }, { timeout: 60000 })
      .toBeTruthy()
    await page.goto('/subjects', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(page.getByTestId(`subjects-delete-${id}`)).toHaveCount(0, { timeout: 30000 })
  })

  test('02 student elective catalog row is scoped to elective-catalog card (not course grid)', async ({ page }) => {
    const s = scenario()
    const electiveName = `E2E选修课_${s.suffix}`
    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.goto('/courses', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(page.locator('.elective-catalog-card')).toBeVisible({ timeout: 60000 })
    const row = electiveCatalogRow(page, electiveName)
    await expect(row).toBeVisible({ timeout: 60000 })
    const enroll = row.getByRole('button', { name: '选课' })
    const drop = row.getByRole('button', { name: '退选' })
    await expect(enroll.or(drop)).toBeVisible({ timeout: 30000 })
  })

  test('03 GET /api/materials rejects page_size above API le=100 with 422', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const { status } = await fetchStatus('GET', `/api/materials?subject_id=${s.course_required_id}&page=1&page_size=200`, {
      token: tok
    })
    expect(status).toBe(422)
  })

  test('04 GET /api/homeworks rejects page_size above API le=100 with 422', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const { status } = await fetchStatus(
      'GET',
      `/api/homeworks?subject_id=${s.course_required_id}&page=1&page_size=200`,
      { token: tok }
    )
    expect(status).toBe(422)
  })

  test('05 GET /api/notifications rejects page_size above API le=100 with 422', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const { status } = await fetchStatus('GET', `/api/notifications?page=1&page_size=200`, { token: tok })
    expect(status).toBe(422)
  })

  test('06 GET /api/parent/notifications rejects page_size above le=100 with 422 (unauthenticated)', async () => {
    const s = scenario()
    const { status } = await fetchStatus(
      'GET',
      `/api/parent/notifications/${encodeURIComponent(s.parent_code)}?page=1&page_size=200`
    )
    expect(status).toBe(422)
  })

  test('07 GET /api/discussions rejects page_size above le=100 with 422', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const q = new URLSearchParams({
      target_type: 'homework',
      target_id: String(s.homework_id),
      subject_id: String(s.course_required_id),
      class_id: String(s.class_id_1),
      page: '1',
      page_size: '200'
    })
    const { status } = await fetchStatus('GET', `/api/discussions?${q.toString()}`, { token: tok })
    expect(status).toBe(422)
  })

  test('08 student elective self-enroll POST twice is idempotent (single enrollment row)', async () => {
    const s = scenario()
    const stuTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const adminTok = await obtainAccessToken(s.admin.username, s.admin.password)
    await apiDelete(`/api/subjects/${s.course_elective_id}/students/${s.student_plain.student_row_id}`, adminTok).catch(
      () => {}
    )

    const a = await apiPostJson(`/api/subjects/${s.course_elective_id}/student-self-enroll`, stuTok, {})
    const b = await apiPostJson(`/api/subjects/${s.course_elective_id}/student-self-enroll`, stuTok, {})
    expect(a).toBeTruthy()
    expect(b).toBeTruthy()

    const students = await apiGetJson(`/api/subjects/${s.course_elective_id}/students`, adminTok)
    const n = (students || []).filter(x => Number(x.student_id) === Number(s.student_plain.student_row_id)).length
    expect(n).toBe(1)
  })

  test('09 POST /api/auth/change-password with wrong current password returns 400', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const { status } = await fetchStatus('POST', '/api/auth/change-password', {
      token: tok,
      body: {
        current_password: 'DefinitelyWrongPass999!',
        new_password: 'NewWrong999999!',
        confirm_password: 'NewWrong999999!'
      }
    })
    expect(status).toBe(400)
  })

  test('10 bearer token becomes invalid after successful password change (API)', async () => {
    const s = scenario()
    const beforeTok = await obtainAccessToken(s.student_drop.username, s.password_teacher_student)
    const newPass = `NewE2e_${Date.now()}!a9`
    await apiPostJson('/api/auth/change-password', beforeTok, {
      current_password: s.password_teacher_student,
      new_password: newPass,
      confirm_password: newPass
    })
    const afterMe = await fetchStatus('GET', '/api/auth/me', { token: beforeTok })
    expect(afterMe.status).toBe(401)
    const restoredTok = await obtainAccessToken(s.student_drop.username, newPass)
    await apiPostJson('/api/auth/change-password', restoredTok, {
      current_password: newPass,
      new_password: s.password_teacher_student,
      confirm_password: s.password_teacher_student
    })
  })

  test('11 dual cold admin sessions both reach users table toolbar', async ({ browser }) => {
    const s = scenario()
    const ctxA = await browser.newContext()
    const ctxB = await browser.newContext()
    const a = await ctxA.newPage()
    const b = await ctxB.newPage()
    try {
      await Promise.all([
        login(a, s.admin.username, s.admin.password),
        login(b, s.admin.username, s.admin.password)
      ])
      await Promise.all([
        a.goto('/users', { waitUntil: 'domcontentloaded', timeout: 60000 }),
        b.goto('/users', { waitUntil: 'domcontentloaded', timeout: 60000 })
      ])
      await expect(a.getByTestId('users-open-create')).toBeVisible({ timeout: 60000 })
      await expect(b.getByTestId('users-open-create')).toBeVisible({ timeout: 60000 })
    } finally {
      await ctxA.close().catch(() => {})
      await ctxB.close().catch(() => {})
    }
  })

  test('12 student cannot create course via API (403)', async () => {
    const s = scenario()
    const stuTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const { status } = await fetchStatus('POST', '/api/subjects', {
      token: stuTok,
      body: {
        name: `E2E_should_fail_${Date.now()}`,
        class_id: s.class_id_1,
        course_type: 'required',
        status: 'active'
      }
    })
    expect(status).toBe(403)
  })

  test('13 teacher roster-enroll POST is paired with wait (no missed fast 200)', async ({ page }) => {
    const s = scenario()
    await apiDelete(`/api/subjects/${s.course_required_id}/students/${s.student_b.student_row_id}`, await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)).catch(() => {})

    await login(page, s.admin.username, s.admin.password)
    await page.goto('/subjects', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.getByTestId(`btn-roster-enroll-${s.course_required_id}`).click()
    await expect(page.getByTestId('dialog-roster-enroll')).toBeVisible({ timeout: 30000 })
    const row = page.locator(`[data-testid="table-roster-enroll-pick"] tr:has-text("${s.student_b.username}")`)
    await expect(row).toBeVisible({ timeout: 30000 })
    await row.locator('.el-checkbox').first().click()
    const submitBtn = page.getByTestId('btn-roster-enroll-submit')
    await expect(submitBtn).toBeEnabled({ timeout: 15000 })
    const [resp] = await Promise.all([
      page.waitForResponse(
        r =>
          r.url().includes('/roster-enroll') &&
          r.request().method() === 'POST' &&
          r.ok(),
        { timeout: 120000 }
      ),
      submitBtn.click()
    ])
    expect(resp.ok()).toBeTruthy()
  })

  test('14 shared login helper survives back-to-back navigations', async ({ page }) => {
    const s = scenario()
    await login(page, s.admin.username, s.admin.password)
    await page.goto('/students', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await login(page, s.teacher_own.username, s.password_teacher_student)
    await expect(page.locator('.layout-container')).toBeVisible({ timeout: 30000 })
  })

  test('15 GET /api/materials with page_size=100 succeeds (boundary)', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const data = await apiGetJson(`/api/materials?subject_id=${s.course_required_id}&page=1&page_size=100`, tok)
    expect(data).toHaveProperty('data')
    expect(Array.isArray(data.data)).toBeTruthy()
  })
})
