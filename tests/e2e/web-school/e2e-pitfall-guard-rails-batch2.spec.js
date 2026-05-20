/**
 * Ten additional API contract checks: `page_size` upper bounds vary by router (Pitfall 39).
 * Complements `e2e-pitfall-guard-rails.spec.js` without duplicating its cases.
 *
 * Requires globalSetup + resetE2eScenario.
 */
const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario } = require('./fixtures.cjs')
const { obtainAccessToken, apiGetJson } = require('./future-advanced-coverage-helpers.cjs')

const scenario = () => loadE2eScenario()

function apiBase() {
  return (process.env.E2E_API_URL || 'http://127.0.0.1:8012').replace(/\/$/, '')
}

async function fetchStatus(method, pathname, { token } = {}) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method,
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  })
  return { status: res.status }
}

test.describe('E2E pitfall guard rails batch 2 (10 cases)', () => {
  test.describe.configure({ timeout: 120_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e seed; run globalSetup with E2E_DEV_SEED_TOKEN')
    }
  })

  test('01 GET /api/logs rejects page_size above le=100 with 422 (admin)', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.admin.username, s.admin.password)
    const { status } = await fetchStatus('GET', `/api/logs?page=1&page_size=200`, { token: tok })
    expect(status).toBe(422)
  })

  test('02 GET /api/points/exchanges rejects page_size above le=100 with 422 (teacher)', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const { status } = await fetchStatus('GET', `/api/points/exchanges?page=1&page_size=200`, { token: tok })
    expect(status).toBe(422)
  })

  test('03 GET /api/points/records/{student} rejects page_size above le=100 with 422 (teacher)', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const sid = s.student_plain.student_row_id
    const { status } = await fetchStatus('GET', `/api/points/records/${sid}?page=1&page_size=200`, { token: tok })
    expect(status).toBe(422)
  })

  test('04 GET /api/parent/scores rejects page_size above le=100 with 422 (unauthenticated)', async () => {
    const s = scenario()
    const { status } = await fetchStatus(
      'GET',
      `/api/parent/scores/${encodeURIComponent(s.parent_code)}?page=1&page_size=200`
    )
    expect(status).toBe(422)
  })

  test('05 GET /api/parent/homework rejects page_size above le=100 with 422 (unauthenticated)', async () => {
    const s = scenario()
    const { status } = await fetchStatus(
      'GET',
      `/api/parent/homework/${encodeURIComponent(s.parent_code)}?page=1&page_size=200`
    )
    expect(status).toBe(422)
  })

  test('06 GET /api/homeworks/{id}/submissions rejects page_size above le=100 with 422 (teacher)', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const { status } = await fetchStatus(
      'GET',
      `/api/homeworks/${s.homework_id}/submissions?page=1&page_size=200`,
      { token: tok }
    )
    expect(status).toBe(422)
  })

  test('07 GET /api/students accepts page_size=200 (le=1000)', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const data = await apiGetJson(`/api/students?class_id=${s.class_id_1}&page=1&page_size=200`, tok)
    expect(data).toHaveProperty('data')
    expect(Array.isArray(data.data)).toBeTruthy()
  })

  test('08 GET /api/students rejects page_size above le=1000 with 422', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const { status } = await fetchStatus(
      'GET',
      `/api/students?class_id=${s.class_id_1}&page=1&page_size=2001`,
      { token: tok }
    )
    expect(status).toBe(422)
  })

  test('09 GET /api/logs with page_size=100 succeeds (admin boundary)', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.admin.username, s.admin.password)
    const data = await apiGetJson(`/api/logs?page=1&page_size=100`, tok)
    expect(data).toHaveProperty('data')
    expect(Array.isArray(data.data)).toBeTruthy()
  })

  test('10 GET /api/points/exchanges with page_size=100 succeeds (teacher boundary)', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const data = await apiGetJson(`/api/points/exchanges?page=1&page_size=100`, tok)
    expect(data).toHaveProperty('data')
    expect(Array.isArray(data.data)).toBeTruthy()
  })
})
