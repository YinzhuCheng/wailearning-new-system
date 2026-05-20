/**
 * Ten additive API/UI smoke checks from agent triage (pagination, auth edges, seed contract).
 * Requires globalSetup + resetE2eScenario (same as pitfall guard rails).
 */
const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario, enterSeededRequiredCourse } = require('./fixtures.cjs')
const { login, obtainAccessToken, apiGetJson } = require('./future-advanced-coverage-helpers.cjs')

const scenario = () => loadE2eScenario()

function apiBase() {
  return (process.env.E2E_API_URL || 'http://127.0.0.1:8012').replace(/\/$/, '')
}

async function fetchStatus(method, pathname, { token } = {}) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method,
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  })
  return res.status
}

test.describe('E2E agent follow-up batch (10 cases)', () => {
  test.describe.configure({ timeout: 120_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e seed; run globalSetup with E2E_DEV_SEED_TOKEN')
    }
  })

  test('01 GET /api/homeworks rejects page_size above le=100 with 422 (teacher)', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const status = await fetchStatus('GET', `/api/homeworks?page=1&page_size=200`, { token: tok })
    expect(status).toBe(422)
  })

  test('02 GET /api/homeworks with page_size=100 succeeds (teacher boundary)', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const data = await apiGetJson(`/api/homeworks?page=1&page_size=100`, tok)
    expect(data).toHaveProperty('data')
  })

  test('03 GET /api/materials rejects page_size above le=100 with 422 (teacher)', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const status = await fetchStatus(
      'GET',
      `/api/materials?subject_id=${s.course_required_id}&page=1&page_size=500`,
      { token: tok }
    )
    expect(status).toBe(422)
  })

  test('04 GET /api/classes returns 200 for teacher', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const data = await apiGetJson('/api/classes', tok)
    expect(Array.isArray(data)).toBeTruthy()
  })

  test('05 GET /api/semesters returns 200 for admin', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.admin.username, s.admin.password)
    const data = await apiGetJson('/api/semesters', tok)
    expect(Array.isArray(data)).toBeTruthy()
  })

  test('06 GET /api/settings/public is unauthenticated 200', async () => {
    const status = await fetchStatus('GET', '/api/settings/public')
    expect(status).toBe(200)
  })

  test('07 GET /api/health is unauthenticated 200', async () => {
    const status = await fetchStatus('GET', '/api/health')
    expect(status).toBe(200)
  })

  test('08 Student homework list for course: page_size over limit 422', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const path = `/api/homeworks/courses/${s.course_required_id}/students/${s.student_plain.student_row_id}/homeworks?page=1&page_size=500`
    const status = await fetchStatus('GET', path, { token: tok })
    expect(status).toBe(422)
  })

  test('09 Student enters seeded course card from /courses (navigation)', async ({ page }) => {
    const s = scenario()
    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)
    await expect(page).toHaveURL(/\/course-home/)
  })

  test('10 Wrong password login returns 401', async () => {
    const s = scenario()
    const body = new URLSearchParams()
    body.set('username', s.admin.username)
    body.set('password', 'DefinitelyWrongPassword999!')
    const res = await fetch(`${apiBase()}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body
    })
    expect(res.status).toBe(401)
  })
})
