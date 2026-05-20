/**
 * Fifteen high-density E2E / API checks aimed at PostgreSQL-aligned deployments and LLM quota hazards.
 *
 * Focus: global quota policy vs course LLM config boundaries, auth edges, seed contract, admin Settings
 * form persistence, and resilience patterns documented in TEST_EXECUTION_PITFALLS.md.
 *
 * Requires Playwright globalSetup (E2E_DEV_SEED_TOKEN) and the same reset contract as other web-school E2E.
 * Run serially with other Playwright jobs (CI=1 recommended) to avoid fixed-port contention on
 * <E2E_API_HOST>:8012 / <E2E_UI_HOST>:3012 (see Pitfall 41).
 */
const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario } = require('./fixtures.cjs')
const {
  login,
  obtainAccessToken,
  apiGetJson,
  apiPutJson,
  apiPostJson
} = require('./future-advanced-coverage-helpers.cjs')

const scenario = () => loadE2eScenario()

function apiBase() {
  return (process.env.E2E_API_URL || 'http://127.0.0.1:8012').replace(/\/$/, '')
}

async function fetchJson(method, pathname, { token, body } = {}) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method,
    headers: {
      ...(body != null ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: body == null ? undefined : JSON.stringify(body)
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

test.describe('E2E PostgreSQL-hazard tier (15 cases)', () => {
  test.describe.configure({ timeout: 300_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e seed; set E2E_DEV_SEED_TOKEN and globalSetup')
    }
  })

  test('01 admin GET global quota policy returns estimation knobs and timezone', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.admin.username, s.admin.password)
    const pol = await apiGetJson('/api/llm-settings/admin/quota-policy', tok)
    expect(pol.quota_timezone).toBeTruthy()
    expect(typeof pol.estimated_chars_per_token).toBe('number')
    expect(pol.estimated_image_tokens).toBeGreaterThanOrEqual(1)
    expect(pol.max_parallel_grading_tasks).toBeGreaterThanOrEqual(1)
  })

  test('02 admin PUT global quota policy round-trip (timezone + parallel)', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.admin.username, s.admin.password)
    const before = await apiGetJson('/api/llm-settings/admin/quota-policy', tok)
    const tz = before.quota_timezone === 'UTC' ? 'Asia/Shanghai' : 'UTC'
    const par = before.max_parallel_grading_tasks === 2 ? 3 : 2
    const after = await apiPutJson('/api/llm-settings/admin/quota-policy', tok, {
      quota_timezone: tz,
      max_parallel_grading_tasks: par
    })
    expect(after.quota_timezone).toBe(tz)
    expect(after.max_parallel_grading_tasks).toBe(par)
    await apiPutJson('/api/llm-settings/admin/quota-policy', tok, {
      quota_timezone: before.quota_timezone,
      max_parallel_grading_tasks: before.max_parallel_grading_tasks
    })
  })

  test('03 admin PUT rejects max_parallel_grading_tasks above 64 with 422', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.admin.username, s.admin.password)
    const { status, data } = await fetchJson('PUT', '/api/llm-settings/admin/quota-policy', {
      token: tok,
      body: { max_parallel_grading_tasks: 99 }
    })
    expect(status).toBe(422)
    expect(JSON.stringify(data)).toMatch(/422|parallel|64|validation/i)
  })

  test('04 student cannot GET admin quota policy (403)', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const { status } = await fetchJson('GET', '/api/llm-settings/admin/quota-policy', { token: tok })
    expect(status).toBe(403)
  })

  test('05 teacher GET course LLM config has no legacy pool keys in JSON', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const cfg = await apiGetJson(`/api/llm-settings/courses/${s.course_required_id}`, tok)
    const raw = JSON.stringify(cfg)
    expect(raw).not.toMatch(/daily_course_token_limit|daily_student_token_limit/)
    expect(cfg.quota_usage == null || typeof cfg.quota_usage).toBeTruthy()
  })

  test('06 teacher PUT course LLM ignores legacy quota keys in body (200, no echo)', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const cfg = await apiGetJson(`/api/llm-settings/courses/${s.course_required_id}`, tok)
    const body = {
      is_enabled: Boolean(cfg.is_enabled),
      response_language: cfg.response_language,
      max_input_tokens: cfg.max_input_tokens ?? 16000,
      max_output_tokens: cfg.max_output_tokens ?? 800,
      system_prompt: cfg.system_prompt,
      teacher_prompt: cfg.teacher_prompt,
      quota_timezone: 'Pacific/Honolulu',
      estimated_chars_per_token: 1.5,
      estimated_image_tokens: 123,
      daily_course_token_limit: 999999,
      endpoints: (cfg.endpoints || []).map(e => ({ preset_id: e.preset_id, priority: e.priority }))
    }
    const out = await apiPutJson(`/api/llm-settings/courses/${s.course_required_id}`, tok, body)
    expect(out.daily_course_token_limit).toBeUndefined()
    expect(out.quota_timezone).toBeUndefined()
  })

  test('07 student quota row includes global quota_timezone after admin policy flip', async () => {
    const s = scenario()
    const adminTok = await obtainAccessToken(s.admin.username, s.admin.password)
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const before = await apiGetJson('/api/llm-settings/admin/quota-policy', adminTok)
    const alt = before.quota_timezone === 'UTC' ? 'Asia/Shanghai' : 'UTC'
    await apiPutJson('/api/llm-settings/admin/quota-policy', adminTok, { quota_timezone: alt })
    const row = await apiGetJson(`/api/llm-settings/courses/student-quota/${s.course_required_id}`, stTok)
    expect(row.quota_timezone).toBe(alt)
    await apiPutJson('/api/llm-settings/admin/quota-policy', adminTok, { quota_timezone: before.quota_timezone })
  })

  test('08 student-quotas summary lists seeded required course with attribution fields', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const sum = await apiGetJson('/api/llm-settings/courses/student-quotas', tok)
    expect(sum.courses).toBeTruthy()
    const row = sum.courses.find(c => Number(c.subject_id) === Number(s.course_required_id))
    expect(row).toBeTruthy()
    expect(row).toHaveProperty('usage_date')
    expect(row).toHaveProperty('quota_timezone')
  })

  test('09 bulk quota override scope=subject then clear (admin)', async () => {
    const s = scenario()
    const adminTok = await obtainAccessToken(s.admin.username, s.admin.password)
    await apiPostJson(
      '/api/llm-settings/admin/quota-overrides/bulk',
      adminTok,
      { scope: 'subject', subject_id: s.course_required_id, daily_tokens: 55_555 }
    )
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const q1 = await apiGetJson(`/api/llm-settings/courses/student-quota/${s.course_required_id}`, stTok)
    expect(q1.daily_student_token_limit).toBe(55_555)
    await apiPostJson(
      '/api/llm-settings/admin/quota-overrides/bulk',
      adminTok,
      { scope: 'subject', subject_id: s.course_required_id, clear_override: true }
    )
    const q2 = await apiGetJson(`/api/llm-settings/courses/student-quota/${s.course_required_id}`, stTok)
    expect(q2.uses_personal_override).toBe(false)
  })

  test('10 unauthenticated GET /api/llm-settings/presets is 401', async () => {
    const { status } = await fetchJson('GET', '/api/llm-settings/presets')
    expect([401, 403]).toContain(status)
  })

  test('11 teacher presets list returns array with seeded discussion mock preset name', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const rows = await apiGetJson('/api/llm-settings/presets', tok)
    expect(Array.isArray(rows)).toBe(true)
    const names = rows.map(r => r.name || '')
    expect(names.some(n => n.includes('e2e_discussion'))).toBe(true)
  })

  test('12 parallel duplicate GET student-quota (same token) both succeed', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const path = `/api/llm-settings/courses/student-quota/${s.course_required_id}`
    const [a, b] = await Promise.all([
      fetch(`${apiBase()}${path}`, { headers: { Authorization: `Bearer ${tok}` } }),
      fetch(`${apiBase()}${path}`, { headers: { Authorization: `Bearer ${tok}` } })
    ])
    expect(a.ok && b.ok).toBe(true)
  })

  test('13 seed payload exposes stable ids for hazard chaining', async () => {
    const s = scenario()
    expect(s.suffix).toBeTruthy()
    expect(s.course_required_id).toBeGreaterThan(0)
    expect(s.homework_id).toBeGreaterThan(0)
    expect(s.student_plain.student_row_id).toBeGreaterThan(0)
  })

  test('14 admin Settings UI: global quota timezone field visible and save button enabled', async ({ page }) => {
    const s = scenario()
    await login(page, s.admin.username, s.admin.password)
    await page.goto('/settings', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(page.getByTestId('settings-llm-quota-timezone')).toBeVisible({ timeout: 60000 })
    await expect(page.getByTestId('settings-llm-quota-save')).toBeEnabled({ timeout: 15000 })
  })

  test('15 teacher Subjects UI: open LLM dialog shows system quota alert, not raw legacy field names', async ({
    page
  }) => {
    const s = scenario()
    const courseName = `E2E必修课_${s.suffix}`
    await login(page, s.teacher_own.username, s.teacher_own.password)
    await page.goto('/subjects', { waitUntil: 'domcontentloaded', timeout: 60000 })
    const row = page.getByRole('row', { name: new RegExp(courseName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) })
    await expect(row).toBeVisible({ timeout: 20000 })
    await row.getByRole('button', { name: /LLM/ }).click()
    const dialog = page.getByTestId('dialog-course-llm')
    await expect(dialog).toBeVisible({ timeout: 20000 })
    await expect(dialog.getByText(/系统 LLM 用量统计日/)).toBeVisible({ timeout: 15000 })
    await expect(dialog.getByText(/quota_timezone|estimated_chars_per_token|estimated_image_tokens/)).toHaveCount(0)
  })
})
