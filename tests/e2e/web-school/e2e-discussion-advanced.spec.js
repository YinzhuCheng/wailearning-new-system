/**
 * Course discussion (homework + materials): multi-role, concurrency, pagination,
 * cold navigation, error codes, and settings integration.
 * Requires globalSetup seed + E2E_DEV_SEED_TOKEN (same as other e2e specs).
 */
const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario, enterSeededRequiredCourse } = require('./fixtures.cjs')
const { login } = require('./future-advanced-coverage-helpers.cjs')

const scenario = () => loadE2eScenario()

function apiBase() {
  return (process.env.E2E_API_URL || 'http://127.0.0.1:8012').replace(/\/$/, '')
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

async function apiPostDiscussion(token, body) {
  const res = await fetch(`${apiBase()}/api/discussions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify(body)
  })
  const text = await res.text()
  return { status: res.status, json: text ? JSON.parse(text) : null, text }
}

async function apiListDiscussions(token, params) {
  const u = new URL(`${apiBase()}/api/discussions`)
  Object.entries(params).forEach(([k, v]) => u.searchParams.set(k, String(v)))
  const res = await fetch(u.toString(), {
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  })
  const text = await res.text()
  return { status: res.status, json: text ? JSON.parse(text) : null, text }
}

async function apiDeleteDiscussion(token, entryId) {
  const res = await fetch(`${apiBase()}/api/discussions/${entryId}`, {
    method: 'DELETE',
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  })
  return { status: res.status }
}

async function apiPatchProfile(token, body) {
  const res = await fetch(`${apiBase()}/api/auth/me`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`
    },
    body: JSON.stringify(body)
  })
  const text = await res.text()
  return { status: res.status, json: text ? JSON.parse(text) : null }
}

test.describe('E2E course discussions (homework + materials, advanced)', () => {
  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e scenario — set E2E_DEV_SEED_TOKEN and globalSetup')
    }
    if (!s.material_discussion_id) {
      testInfo.skip(true, 'Seeded scenario missing material_discussion_id (update backend e2e seed)')
    }
  })

  test('01 cold navigation: student lands on submit page and sees homework title above discussion', async ({
    page
  }) => {
    const s = scenario()
    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.goto(`/homework/${s.homework_id}/submit`, { waitUntil: 'load', timeout: 60000 })
    await expect(page.getByRole('heading', { name: '提交作业' })).toBeVisible({ timeout: 20000 })
    await expect(page.getByText(new RegExp(`E2E_UI作业_${escapeRegex(s.suffix)}`)).first()).toBeVisible({
      timeout: 15000
    })
    await expect(page.getByText('讨论区')).toBeVisible({ timeout: 15000 })
    await expect(page.getByText(/Playwright UI 测试/)).toBeVisible({ timeout: 10000 })
  })

  test('02 student posts first reply; text appears in discussion list', async ({ page }) => {
    const s = scenario()
    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.goto(`/homework/${s.homework_id}/submit`, { waitUntil: 'load', timeout: 60000 })
    const msg = `e2e-first-${Date.now()}`
    const card = page.locator('.discussion-card').filter({ has: page.getByText('讨论区') }).first()
    await card.getByRole('button', { name: '写回复' }).click()
    await card.locator('.discussion-input .el-textarea__inner').fill(msg)
    await card.getByRole('button', { name: '发表回复' }).click()
    await expect(page.locator('.discussion-row__body').filter({ hasText: msg })).toBeVisible({ timeout: 15000 })
  })

  test('03 concurrent API posts from student and teacher converge to two visible rows', async () => {
    const s = scenario()
    const [stTok, teTok] = await Promise.all([
      obtainAccessToken(s.student_plain.username, s.password_teacher_student),
      obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    ])
    const base = {
      target_type: 'homework',
      target_id: s.homework_id,
      subject_id: s.course_required_id,
      class_id: s.class_id_1
    }
    const a = `e2e-conc-a-${Date.now()}`
    const b = `e2e-conc-b-${Date.now()}`
    const [r1, r2] = await Promise.all([
      apiPostDiscussion(stTok, { ...base, body: a }),
      apiPostDiscussion(teTok, { ...base, body: b })
    ])
    expect(r1.status).toBe(200)
    expect(r2.status).toBe(200)
    const list = await apiListDiscussions(teTok, { ...base, page: 1, page_size: 50 })
    expect(list.status).toBe(200)
    const bodies = (list.json.data || []).map(x => x.body)
    expect(bodies).toContain(a)
    expect(bodies).toContain(b)
  })

  test('04 unauthenticated discussion list returns 401', async () => {
    const s = scenario()
    const res = await apiListDiscussions(null, {
      target_type: 'homework',
      target_id: s.homework_id,
      subject_id: s.course_required_id,
      class_id: s.class_id_1,
      page: 1
    })
    expect(res.status).toBe(401)
  })

  test('05 wrong class_id for course instance returns 400 on post', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const r = await apiPostDiscussion(tok, {
      target_type: 'homework',
      target_id: s.homework_id,
      subject_id: s.course_required_id,
      class_id: s.class_id_2,
      body: 'should-fail'
    })
    expect(r.status).toBe(400)
  })

  test('06 other-class teacher cannot list discussions for required course', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_other.username, s.password_teacher_student)
    const r = await apiListDiscussions(tok, {
      target_type: 'homework',
      target_id: s.homework_id,
      subject_id: s.course_required_id,
      class_id: s.class_id_1,
      page: 1
    })
    expect(r.status).toBe(403)
  })

  test('07 empty body post returns 422', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const r = await apiPostDiscussion(tok, {
      target_type: 'homework',
      target_id: s.homework_id,
      subject_id: s.course_required_id,
      class_id: s.class_id_1,
      body: '   '
    })
    expect([400, 422]).toContain(r.status)
  })

  test('08 pagination: homework title remains visible after navigating to page 2', async ({ page }) => {
    const s = scenario()
    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const base = {
      target_type: 'homework',
      target_id: s.homework_id,
      subject_id: s.course_required_id,
      class_id: s.class_id_1
    }
    const stamp = Date.now()
    for (let i = 0; i < 11; i++) {
      const r = await apiPostDiscussion(teTok, { ...base, body: `bulk-${stamp}-${i}` })
      expect(r.status).toBe(200)
    }
    await login(page, s.teacher_own.username, s.password_teacher_student)
    await page.goto(`/homework/${s.homework_id}/submissions`, { waitUntil: 'load', timeout: 60000 })
    const titlePat = new RegExp(`E2E_UI作业_${escapeRegex(s.suffix)}`)
    await expect(page.getByText(titlePat).first()).toBeVisible({ timeout: 20000 })
    await expect(page.getByText('讨论区')).toBeVisible({ timeout: 15000 })
    await page.locator('.discussion-card .el-pagination .btn-next').click()
    await expect(page.getByText(titlePat).first()).toBeVisible({ timeout: 10000 })
    await expect(page.locator('.discussion-row__body').filter({ hasText: `bulk-${stamp}-` }).first()).toBeVisible({
      timeout: 15000
    })
  })

  test('09 teacher deletes student message via UI; row disappears', async ({ page }) => {
    const s = scenario()
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const msg = `e2e-delete-me-${Date.now()}`
    const created = await apiPostDiscussion(stTok, {
      target_type: 'homework',
      target_id: s.homework_id,
      subject_id: s.course_required_id,
      class_id: s.class_id_1,
      body: msg
    })
    expect(created.status).toBe(200)
    const eid = created.json.id
    await login(page, s.teacher_own.username, s.password_teacher_student)
    await page.goto(`/homework/${s.homework_id}/submissions`, { waitUntil: 'load', timeout: 60000 })
    await expect(page.locator('.discussion-row__body').filter({ hasText: msg })).toBeVisible({ timeout: 20000 })
    const row = page.locator('.discussion-row').filter({ hasText: msg })
    await row.getByRole('button', { name: '删除' }).click()
    await page.getByRole('button', { name: '确定' }).click()
    await expect(page.locator('.discussion-row__body').filter({ hasText: msg })).toHaveCount(0, { timeout: 15000 })
    const gone = await apiListDiscussions(stTok, {
      target_type: 'homework',
      target_id: s.homework_id,
      subject_id: s.course_required_id,
      class_id: s.class_id_1,
      page: 1,
      page_size: 100
    })
    expect(gone.json.data.every(x => x.id !== eid)).toBe(true)
  })

  test('10 material detail dialog: discussion posts and survives reopen', async ({ page }) => {
    const s = scenario()
    await login(page, s.teacher_own.username, s.password_teacher_student)
    await page.goto('/courses')
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto('/materials', { waitUntil: 'load', timeout: 60000 })
    const row = page.locator('.el-table__body tbody tr').filter({ hasText: `E2E讨论资料_${s.suffix}` }).first()
    await expect(row).toBeVisible({ timeout: 20000 })
    await row.click()
    await expect(page.locator('.el-dialog').filter({ hasText: '资料详情' })).toBeVisible({ timeout: 15000 })
    const msg = `mat-dlg-${Date.now()}`
    const dialog = page.locator('.el-dialog').filter({ hasText: '资料详情' }).first()
    await dialog.getByRole('button', { name: '写回复' }).click()
    await dialog.locator('.discussion-input .el-textarea__inner').fill(msg)
    await dialog.getByRole('button', { name: '发表回复' }).click()
    await expect(page.locator('.el-dialog .discussion-row__body').filter({ hasText: msg })).toBeVisible({
      timeout: 15000
    })
    await dialog.locator('.el-dialog__footer').getByRole('button', { name: '关闭' }).click()
    await row.click()
    await expect(page.locator('.el-dialog .discussion-row__body').filter({ hasText: msg })).toBeVisible({
      timeout: 15000
    })
  })
})

function escapeRegex(text) {
  return `${text || ''}`.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}
