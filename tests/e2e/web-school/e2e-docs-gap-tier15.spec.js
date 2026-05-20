/**
 * Fifteen additive API-heavy E2E checks targeting gaps after documentation refactor:
 * discussion router bounds & scope errors, cross-route page_size discipline,
 * homework enrollment boundary (student without enrollment), orphan-course boundaries,
 * dual-gate acceptance patterns, and SQLite grading-queue bleed across resets.
 *
 * Run incrementally (repo root):
 *   cd apps/web/school && npx playwright test ../../tests/e2e/web-school/e2e-docs-gap-tier15.spec.js --project=chromium
 *
 * Doc hooks: docs/architecture/CORE_BUSINESS_FLOWS.md, docs/testing/TEST_EXECUTION_PITFALLS.md (Pitfall 69).
 */
const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario } = require('./fixtures.cjs')
const {
  obtainAccessToken,
  apiPostJson,
  configureMockLlm,
  processGradingTasks,
  seedHeaders,
  createPreset,
  validatePreset,
  setFlatCourseConfig,
  createHomework,
  apiBase
} = require('./future-advanced-coverage-helpers.cjs')

const scenario = () => loadE2eScenario()

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

test.describe('E2E docs-gap tier (15 cases)', () => {
  test.describe.configure({ timeout: 300_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e seed; set E2E_DEV_SEED_TOKEN and globalSetup')
    }
  })

  test('01 discussions GET rejects page_size above 100 with 422', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const hwId = Number(s.homework_id)
    const subj = Number(s.course_required_id)
    const cls = Number(s.class_id_1)
    const st = await fetchStatus(
      'GET',
      `/api/discussions?target_type=homework&target_id=${hwId}&subject_id=${subj}&class_id=${cls}&page=1&page_size=200`,
      { token: tok }
    )
    expect(st).toBe(422)
  })

  test('02 discussions GET rejects class_id mismatch with homework with 400', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const hwId = Number(s.homework_id)
    const subj = Number(s.course_required_id)
    const wrongClass = Number(s.class_id_2)
    const st = await fetchStatus(
      'GET',
      `/api/discussions?target_type=homework&target_id=${hwId}&subject_id=${subj}&class_id=${wrongClass}&page=1`,
      { token: tok }
    )
    expect(st).toBe(400)
  })

  test('03 teacher can invoke_llm on discussion create (200)', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const hwId = Number(s.homework_id)
    const subj = Number(s.course_required_id)
    const cls = Number(s.class_id_1)
    const { status } = await fetchJson('POST', '/api/discussions', {
      token: tok,
      body: {
        target_type: 'homework',
        target_id: hwId,
        subject_id: subj,
        class_id: cls,
        body: 'teacher tries LLM',
        invoke_llm: true
      }
    })
    expect(status).toBe(200)
  })

  test('04 student cannot GET submission/me for homework in another class (403 or 404)', async () => {
    const s = scenario()
    const adminTok = await obtainAccessToken(s.admin.username, s.password_admin)
    const otherCourseId = Number(s.course_other_teacher_id)
    const class2 = Number(s.class_id_2)
    const hwOther = await apiPostJson('/api/homeworks', adminTok, {
      title: `GAP_CROSS_CLASS_${s.suffix}`,
      content: 'cross-class probe',
      class_id: class2,
      subject_id: otherCourseId,
      max_score: 100,
      grade_precision: 'integer',
      auto_grading_enabled: false,
      allow_late_submission: true,
      late_submission_affects_score: false
    })
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const st = await fetchStatus('GET', `/api/homeworks/${hwOther.id}/submission/me`, { token: stTok })
    expect([403, 404]).toContain(st)
  })

  test('05 student cannot POST submission for homework in another class (403 enrollment or 404 roster)', async () => {
    const s = scenario()
    const adminTok = await obtainAccessToken(s.admin.username, s.password_admin)
    const otherCourseId = Number(s.course_other_teacher_id)
    const class2 = Number(s.class_id_2)
    const hwOther = await apiPostJson('/api/homeworks', adminTok, {
      title: `GAP_CROSS_CLASS_POST_${s.suffix}`,
      content: 'cross-class post',
      class_id: class2,
      subject_id: otherCourseId,
      max_score: 100,
      grade_precision: 'integer',
      auto_grading_enabled: false,
      allow_late_submission: true,
      late_submission_affects_score: false
    })
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const st = await fetchStatus('POST', `/api/homeworks/${hwOther.id}/submission`, {
      token: stTok,
      body: { content: 'nope', submission_mode: 'full' }
    })
    expect([403, 404]).toContain(st)
  })

  test('06 teacher GET homework list rejects page_size above 100 with 422', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const subj = Number(s.course_required_id)
    const st = await fetchStatus(
      'GET',
      `/api/homeworks?subject_id=${subj}&page=1&page_size=500`,
      { token: tok }
    )
    expect(st).toBe(422)
  })

  test('07 teacher GET materials rejects page_size above 100 with 422', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const subj = Number(s.course_required_id)
    const st = await fetchStatus(
      'GET',
      `/api/materials?subject_id=${subj}&page=1&page_size=250`,
      { token: tok }
    )
    expect(st).toBe(422)
  })

  test('08 student GET materials rejects page_size above 100 with 422', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const subj = Number(s.course_required_id)
    const st = await fetchStatus(
      'GET',
      `/api/materials?subject_id=${subj}&page=1&page_size=120`,
      { token: tok }
    )
    expect(st).toBe(422)
  })

  test('09 class_teacher cannot list homework for orphan subject (class-unbound course)', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.class_teacher.username, s.password_teacher_student)
    const orphanId = Number(s.course_orphan_id)
    const st = await fetchStatus('GET', `/api/homeworks?subject_id=${orphanId}&page=1&page_size=20`, {
      token: tok
    })
    expect([403, 404]).toContain(st)
  })

  test('10 teacher in another class cannot GET peer student points (403)', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.teacher_other.username, s.password_teacher_student)
    const peerRowId = Number(s.student_plain.student_row_id)
    const st = await fetchStatus('GET', `/api/points/students/${peerRowId}`, { token: tok })
    expect(st).toBe(403)
  })

  test('11 admin GET /api/students rejects page_size above 1000 with 422', async () => {
    const s = scenario()
    const tok = await obtainAccessToken(s.admin.username, s.password_admin)
    const st = await fetchStatus('GET', `/api/students?page=1&page_size=5000`, { token: tok })
    expect(st).toBe(422)
  })

  test('12 mock-llm configure succeeds with seed + admin bearer when dual gate on', async () => {
    const s = scenario()
    expect(s.suffix).toBeTruthy()
    const profile = `gap_${s.suffix}`
    await configureMockLlm({
      [profile]: {
        steps: [{ kind: 'ok', score: 8, comment: 'gap-tier', usage: { prompt_tokens: 1, completion_tokens: 1 } }],
        repeat_last: true
      }
    })
    const state = await fetchJson('GET', '/api/e2e/dev/mock-llm/state', {
      headers: seedHeaders()
    })
    expect(state.status).toBe(200)
    expect(Object.keys(state.data.profiles || {})).toContain(profile)
  })

  test('13 seed-only POST process-grading returns 403 when admin JWT required but missing', async () => {
    const s = scenario()
    expect(s.suffix).toBeTruthy()
    const tokenOnly = process.env.E2E_DEV_SEED_TOKEN || 'test-playwright-seed'
    const res = await fetch(`${apiBase()}/api/e2e/dev/process-grading`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-E2E-Seed-Token': tokenOnly
      },
      body: JSON.stringify({ max_tasks: 1 })
    })
    const dual = ['1', 'true', 'yes', 'on'].includes(String(process.env.E2E_DEV_REQUIRE_ADMIN_JWT || '').trim().toLowerCase())
    if (dual) {
      expect(res.status).toBe(403)
    } else {
      expect(res.status).toBe(200)
    }
  })

  test('14 grading worker drains mocked task after configure + submit + process', async () => {
    const s = scenario()
    const adminTok = await obtainAccessToken(s.admin.username, s.password_admin)
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const subj = Number(s.course_required_id)
    const profile = `gap_grade_${s.suffix}`
    await configureMockLlm({
      [profile]: {
        steps: [
          {
            kind: 'ok',
            score: 91,
            comment: 'doc-gap-tier',
            usage: { prompt_tokens: 10, completion_tokens: 10, total_tokens: 20 }
          }
        ],
        repeat_last: true
      }
    })
    const preset = await createPreset(adminTok, `gap_preset_${s.suffix}`, profile)
    await validatePreset(adminTok, preset.id)
    await setFlatCourseConfig(adminTok, subj, [preset.id])
    const hw = await createHomework(adminTok, s, `GAP_DOC_${s.suffix}`, {
      auto_grading_enabled: true,
      content: 'graded via mock'
    })
    await fetchJson('POST', `/api/homeworks/${hw.id}/submission`, {
      token: stTok,
      body: { content: 'answer for doc gap', submission_mode: 'full' }
    })
    const processed = await processGradingTasks(8)
    expect(processed).toBeGreaterThanOrEqual(1)
    const hist = await fetchJson('GET', `/api/homeworks/${hw.id}/submission/me/history`, { token: stTok })
    expect(hist.status).toBe(200)
    const attempts = hist.data && hist.data.attempts ? hist.data.attempts : []
    expect(attempts.length).toBeGreaterThanOrEqual(1)
  })

  test('15 sync-status returns numeric unread_count after teacher notification', async () => {
    const s = scenario()
    const th = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const subj = Number(s.course_required_id)
    const cls = Number(s.class_id_1)
    const cr = await fetchJson('POST', '/api/notifications', {
      token: th,
      body: {
        title: `doc-gap-${s.suffix}`,
        content: 'sync probe',
        class_id: cls,
        subject_id: subj
      }
    })
    expect(cr.status).toBe(200)
    const sync = await fetchJson('GET', `/api/notifications/sync-status?subject_id=${subj}`, { token: stTok })
    expect(sync.status).toBe(200)
    expect(typeof sync.data.unread_count).toBe('number')
    expect(sync.data.unread_count).toBeGreaterThanOrEqual(1)
  })
})
