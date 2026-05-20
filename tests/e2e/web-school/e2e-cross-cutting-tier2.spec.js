/**
 * Tier-2 cross-cutting E2E: points/logs/semesters UI smoke, parent portal edges,
 * triple-submit stress, dual-role interference, API-heavy concurrency (no flaky disabled clicks).
 */
const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario, enterSeededRequiredCourse } = require('./fixtures.cjs')
const { login } = require('./future-advanced-coverage-helpers.cjs')

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

async function apiPostJsonExpect(pathname, token, body) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify(body)
  })
  const text = await res.text()
  let json = null
  try {
    json = text ? JSON.parse(text) : null
  } catch {
    /* ignore */
  }
  return { status: res.status, json, text }
}

async function apiPutJsonExpect(pathname, token, body) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify(body)
  })
  const text = await res.text()
  let json = null
  try {
    json = text ? JSON.parse(text) : null
  } catch {
    /* ignore */
  }
  return { status: res.status, json, text }
}

async function apiHomeworkSubmissionHistory(token, homeworkId) {
  return apiGetJson(`/api/homeworks/${homeworkId}/submission/me/history`, token)
}

test.describe('E2E tier-2 cross-cutting scenarios', () => {
  test.describe.configure({ timeout: 180_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e scenario — set E2E_DEV_SEED_TOKEN and globalSetup')
    }
  })

  test('01 cold PointsDisplay: leaderboard shell and ranking table render after login', async ({ page }) => {
    const s = scenario()
    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto('/points-display', { waitUntil: 'load', timeout: 60000 })
    await expect(page.locator('.display-container')).toBeVisible({ timeout: 25000 })
    await expect(page.locator('.ranking-card')).toBeVisible({ timeout: 15000 })
    await expect(page.locator('.ranking-card').getByRole('table').first()).toBeVisible({ timeout: 15000 })
  })

  test('02 teacher Points hub: stats cards and ranking tab load without error overlay', async ({ page }) => {
    const s = scenario()
    await login(page, s.teacher_own.username, s.password_teacher_student)
    await page.goto('/points', { waitUntil: 'load', timeout: 60000 })
    await expect(page.locator('.points-container')).toBeVisible({ timeout: 20000 })
    await expect(page.getByText('学生总数')).toBeVisible({ timeout: 15000 })
    await page.getByRole('tab', { name: '积分排行' }).click()
    await expect(page.getByRole('columnheader', { name: '排名' })).toBeVisible({ timeout: 15000 })
  })

  test('03 admin Logs cold load: stats row and filter controls visible', async ({ page }) => {
    const s = scenario()
    await login(page, s.admin.username, s.admin.password)
    await page.goto('/logs', { waitUntil: 'load', timeout: 60000 })
    await expect(page.locator('.logs-container')).toBeVisible({ timeout: 20000 })
    await expect(page.getByText('今日日志').first()).toBeVisible({ timeout: 15000 })
  })

  test('04 triple concurrent submission POST storm converges to persisted attempts via API', async () => {
    const s = scenario()
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const stamp = Date.now()
    const bodies = Array.from({ length: 3 }, (_, i) => ({
      content: `storm-${stamp}-${i}`,
      attachment_name: null,
      attachment_url: null,
      remove_attachment: false,
      used_llm_assist: false,
      submission_mode: 'full'
    }))
    await Promise.all(
      bodies.map(b =>
        fetch(`${apiBase()}/api/homeworks/${s.homework_id}/submission`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${stTok}`, 'Content-Type': 'application/json' },
          body: JSON.stringify(b)
        })
      )
    )
    await expect
      .poll(async () => (await apiHomeworkSubmissionHistory(stTok, s.homework_id)).attempts?.length || 0, {
        timeout: 30000
      })
      .toBeGreaterThanOrEqual(1)
  })

  test('05 parent portal: invalid parent code verify returns valid false (unauthenticated)', async () => {
    const res = await fetch(`${apiBase()}/api/parent/verify/NOTREAL99`)
    expect(res.ok).toBeTruthy()
    const data = await res.json()
    expect(data.valid).toBe(false)
  })

  test('06 teacher publishes homework; student cold-opens homework list and sees new row', async ({
    page,
    browser
  }) => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const title = `E2E_T2_HW_${s.suffix}_${Date.now()}`
    await apiPostJson('/api/homeworks', teacherTok, {
      class_id: s.class_id_1,
      subject_id: s.course_required_id,
      title,
      content: 'tier2 cold list',
      max_score: 100,
      grade_precision: 'integer',
      auto_grading_enabled: false,
      allow_late_submission: true,
      late_submission_affects_score: false
    })
    const ctx = await browser.newContext()
    const p = await ctx.newPage()
    try {
      await login(p, s.student_plain.username, s.password_teacher_student)
      await enterSeededRequiredCourse(p, s.suffix)
      await p.goto('/homework', { waitUntil: 'load', timeout: 60000 })
      await expect(p.getByRole('row', { name: new RegExp(escapeRegex(title)) })).toBeVisible({ timeout: 25000 })
    } finally {
      await ctx.close().catch(() => {})
    }
  })

  test('07 admin semester workflow: list loads; duplicate create rejected; unique create succeeds', async () => {
    const s = scenario()
    const adminTok = await obtainAccessToken(s.admin.username, s.admin.password)
    const semesters = await apiGetJson('/api/semesters', adminTok)
    const baseName = semesters[0]?.name || '2026春季'
    const dup = await apiPostJsonExpect('/api/semesters', adminTok, { name: baseName, year: 2026 })
    expect(dup.status).toBe(400)
    const uniq = `E2E_SEM_${s.suffix}_${Date.now()}`
    const created = await apiPostJson('/api/semesters', adminTok, { name: uniq, year: 2026 })
    expect(created.name).toBeTruthy()
    const again = await apiGetJson('/api/semesters', adminTok)
    expect((again || []).some(x => `${x.name}`.includes(uniq) || x.name === uniq)).toBe(true)
  })

  test('08 student elective drop then catalog API reflects unenrolled for elective', async () => {
    const s = scenario()
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    await apiPostJson(`/api/subjects/${s.course_elective_id}/student-self-enroll`, stTok, {})
    let catalog = await apiGetJson('/api/subjects/course-catalog', stTok)
    let row = catalog.find(c => Number(c.id) === Number(s.course_elective_id))
    expect(row?.is_enrolled === true).toBeTruthy()
    const drop = await apiPostJsonExpect(`/api/subjects/${s.course_elective_id}/student-self-drop`, stTok, {})
    expect(drop.status).toBe(200)
    catalog = await apiGetJson('/api/subjects/course-catalog', stTok)
    row = catalog.find(c => Number(c.id) === Number(s.course_elective_id))
    expect(row?.is_enrolled !== true).toBeTruthy()
  })

  test('09 concurrent teacher notification creates converge; student list shows all titles', async () => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const stamp = Date.now()
    const titles = [`T2_N1_${stamp}`, `T2_N2_${stamp}`, `T2_N3_${stamp}`]
    await Promise.all(
      titles.map(t =>
        apiPostJson('/api/notifications', teacherTok, {
          title: t,
          content: 'fan',
          audience: 'class',
          subject_id: s.course_required_id,
          class_id: s.class_id_1,
          notification_kind: 'general'
        })
      )
    )
    const data = await apiGetJson(`/api/notifications?subject_id=${s.course_required_id}&page_size=50`, stTok)
    const cells = (data.data || []).map(n => n.title)
    for (const t of titles) {
      expect(cells.some(c => `${c}`.includes(t))).toBe(true)
    }
  })

  test('10 targeted notification: student_b sees title; student_plain does not (API isolation)', async () => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    await apiPostJson(`/api/subjects/${s.course_required_id}/roster-enroll`, teacherTok, {
      student_ids: [s.student_b.student_row_id]
    })
    const title = `T2_PRIV_${s.suffix}_${Date.now()}`
    await apiPostJson('/api/notifications', teacherTok, {
      title,
      content: 'private',
      subject_id: s.course_required_id,
      class_id: s.class_id_1,
      target_student_id: s.student_b.student_row_id,
      notification_kind: 'general'
    })
    const tokB = await obtainAccessToken(s.student_b.username, s.password_teacher_student)
    const tokA = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const listB = await apiGetJson(`/api/notifications?subject_id=${s.course_required_id}&page_size=50`, tokB)
    const listA = await apiGetJson(`/api/notifications?subject_id=${s.course_required_id}&page_size=50`, tokA)
    expect((listB.data || []).some(n => n.title === title)).toBe(true)
    expect((listA.data || []).some(n => n.title === title)).toBe(false)
  })
})
