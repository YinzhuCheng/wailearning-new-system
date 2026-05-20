/**
 * Fifteen additive high-difficulty E2E checks: authz edges, pagination caps, seed/dev API gates,
 * LLM admin vs student boundaries, notification mark-all-read idempotency, and harness foot-guns.
 *
 * Prerequisites: Playwright globalSetup with ``E2E_DEV_SEED_TOKEN`` (same contract as
 * ``e2e-postgres-hazard-tier.spec.js``). Run **serially** with other Playwright jobs on the default
 * ports (see ``docs/testing/TEST_EXECUTION_PITFALLS.md`` Pitfall 41: ECONNRESET from parallel
 * webServer / fixed-port contention on ``<E2E_API_HOST>:8012``).
 */
const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario } = require('./fixtures.cjs')
const { obtainAccessToken, apiGetJson, apiPostJson } = require('./future-advanced-coverage-helpers.cjs')

const scenario = () => loadE2eScenario()

function apiBase() {
  return (process.env.E2E_API_URL || 'http://127.0.0.1:8012').replace(/\/$/, '')
}

async function fetchStatus(method, pathname, { token, body, headers = {} } = {}) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method,
    headers: {
      ...(body != null ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers
    },
    body: body == null ? undefined : JSON.stringify(body)
  })
  return res.status
}

async function fetchJson(method, pathname, opts = {}) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method,
    headers: {
      ...(opts.body != null ? { 'Content-Type': 'application/json' } : {}),
      ...(opts.token ? { Authorization: `Bearer ${opts.token}` } : {}),
      ...(opts.headers || {})
    },
    body: opts.body == null ? undefined : JSON.stringify(opts.body)
  })
  const text = await res.text()
  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }
  return { status: res.status, data, text }
}

test.describe('E2E agent hazard tier (15 cases)', () => {
  test.describe.configure({ timeout: 300_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e seed; set E2E_DEV_SEED_TOKEN and globalSetup')
    }
  })

  test('01 admin GET /api/logs rejects page_size above 100 with 422', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.admin.username, s.admin.password)
    const st = await fetchStatus('GET', '/api/logs?page=1&page_size=200', { token: tok })
    expect(st).toBe(422)
  })

  test('02 student GET /api/notifications rejects page_size above 100 with 422', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const st = await fetchStatus('GET', '/api/notifications?page=1&page_size=200', { token: tok })
    expect(st).toBe(422)
  })

  test('03 student cannot read peer student-quota row for other teachers course (403 or 404)', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const foreign = Number(s.course_other_teacher_id)
    const st = await fetchStatus('GET', `/api/llm-settings/courses/student-quota/${foreign}`, { token: tok })
    expect([403, 404]).toContain(st)
  })

  test('04 admin bulk quota override for course subject then clear', async () => {
    const s = scenario()
    const adminTok = await obtainAccessToken(s.admin.username, s.admin.password)
    const subj = Number(s.course_required_id)
    await apiPostJson('/api/llm-settings/admin/quota-overrides/bulk', adminTok, {
      scope: 'subject',
      subject_id: subj,
      daily_tokens: 77_777
    })
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const q1 = await apiGetJson(`/api/llm-settings/courses/student-quota/${subj}`, stTok)
    expect(q1.daily_student_token_limit).toBe(77_777)
    await apiPostJson('/api/llm-settings/admin/quota-overrides/bulk', adminTok, {
      scope: 'subject',
      subject_id: subj,
      clear_override: true
    })
    const q2 = await apiGetJson(`/api/llm-settings/courses/student-quota/${subj}`, stTok)
    expect(q2.uses_personal_override).toBe(false)
  })

  test('05 teacher cannot POST admin bulk quota override', async () => {
    const s = scenario()
    const th = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const st = await fetchStatus(
      'POST',
      '/api/llm-settings/admin/quota-overrides/bulk',
      {
        token: th,
        body: { scope: 'subject', subject_id: s.course_required_id, daily_tokens: 12345 }
      }
    )
    expect(st).toBe(403)
  })

  test('06 student cannot GET admin global quota policy', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const st = await fetchStatus('GET', '/api/llm-settings/admin/quota-policy', { token: tok })
    expect(st).toBe(403)
  })

  test('07 parallel dual POST mark-all-read both return 200', async () => {
    const s = scenario()
    const th = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const subj = Number(s.course_required_id)
    const cls = Number(s.class_id_1)
    for (let i = 0; i < 2; i += 1) {
      const cr = await fetchJson('POST', '/api/notifications', {
        token: th,
        body: { title: `dual-${i}`, content: 'x', class_id: cls, subject_id: subj }
      })
      expect(cr.status).toBe(200)
    }
    const url = `${apiBase()}/api/notifications/mark-all-read?subject_id=${subj}`
    const [a, b] = await Promise.all([
      fetch(url, { method: 'POST', headers: { Authorization: `Bearer ${stTok}` } }),
      fetch(url, { method: 'POST', headers: { Authorization: `Bearer ${stTok}` } })
    ])
    expect(a.ok && b.ok).toBe(true)
    const sync = await apiGetJson(`/api/notifications/sync-status?subject_id=${subj}`, stTok)
    expect(sync.unread_count).toBe(0)
  })

  test('08 e2e grading-state rejects missing seed token with 403', async () => {
    const s = scenario()
    expect(s.suffix).toBeTruthy()
    const st = await fetchStatus('GET', '/api/e2e/dev/grading-state')
    expect(st).toBe(403)
  })

  test('09 forgot-password empty username returns 200 without throwing', async () => {
    const { status, data } = await fetchJson('POST', '/api/auth/forgot-password', {
      body: { username: '   ' }
    })
    expect(status).toBe(200)
    expect(data && data.message).toBeTruthy()
  })

  test('10 public registration disabled returns 403', async () => {
    const { status } = await fetchJson('POST', '/api/auth/register', {
      body: {
        username: 'should_never_exist_register_hz',
        password: 'DoesNotMatter9!',
        real_name: 'x',
        role: 'student',
        class_id: 1
      }
    })
    expect([400, 403]).toContain(status)
  })

  test('11 unauthenticated GET /api/users is 401', async () => {
    const st = await fetchStatus('GET', '/api/users?page=1&page_size=20')
    expect(st).toBe(401)
  })

  test('12 student GET /api/logs forbidden', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const st = await fetchStatus('GET', '/api/logs?page=1&page_size=20', { token: tok })
    expect(st).toBe(403)
  })

  test('13 admin PUT quota policy rejects non-positive estimated_image_tokens with 422', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.admin.username, s.admin.password)
    const before = await apiGetJson('/api/llm-settings/admin/quota-policy', tok)
    const { status } = await fetchJson('PUT', '/api/llm-settings/admin/quota-policy', {
      token: tok,
      body: { ...before, estimated_image_tokens: 0 }
    })
    expect(status).toBe(422)
  })

  test('14 teacher creates notification; student lists with subject_id filter', async () => {
    const s = scenario()
    const th = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const subj = Number(s.course_required_id)
    const cls = Number(s.class_id_1)
    const cr = await fetchJson('POST', '/api/notifications', {
      token: th,
      body: { title: 'scoped', content: 'c', class_id: cls, subject_id: subj }
    })
    expect(cr.status).toBe(200)
    const list = await apiGetJson(`/api/notifications?subject_id=${subj}&page=1&page_size=20`, stTok)
    expect(Array.isArray(list.data)).toBe(true)
    expect(list.data.some(r => r.title === 'scoped')).toBe(true)
  })

  test('15 mock-llm configure requires X-E2E-Seed-Token (403 when wrong)', async () => {
    const s = scenario()
    expect(s.suffix).toBeTruthy()
    const { status } = await fetchJson(
      'POST',
      '/api/e2e/dev/mock-llm/configure',
      {
        headers: { 'X-E2E-Seed-Token': 'wrong-token-for-hazard-15' },
        body: { profiles: { x: { steps: [{ kind: 'ok', score: 1, comment: 'n' }] } } }
      }
    )
    expect(status).toBe(403)
  })
})
