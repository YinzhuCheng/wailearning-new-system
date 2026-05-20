const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario, enterSeededRequiredCourse } = require('./fixtures.cjs')
const { seedHeaders } = require('./e2e-seed-headers.cjs')

const scenario = () => loadE2eScenario()
const TINY_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlH0y8AAAAASUVORK5CYII=',
  'base64'
)

function apiBase() {
  return (process.env.E2E_API_URL || 'http://127.0.0.1:8012').replace(/\/$/, '')
}

function escapeRegex(text) {
  return `${text || ''}`.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

async function login(page, username, password) {
  await page.goto('/login', { waitUntil: 'load', timeout: 60000 })
  await page.evaluate(() => {
    try {
      localStorage.clear()
      sessionStorage.clear()
    } catch {
      /* ignore */
    }
  })
  await page.goto('/login', { waitUntil: 'load', timeout: 60000 })
  await expect(page.getByTestId('login-username')).toBeVisible({ timeout: 30000 })
  await page.getByTestId('login-username').fill(username)
  await page.getByTestId('login-password').fill(password)
  await page.getByTestId('login-submit').click()
  await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 20000 })
}

async function obtainAccessToken(username, password) {
  const body = new URLSearchParams()
  body.set('username', username)
  body.set('password', password)
  const res = await fetch(`${apiBase()}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  })
  if (!res.ok) throw new Error(`login failed ${res.status}: ${await res.text()}`)
  const data = await res.json()
  return data.access_token
}

async function apiJson(pathname, { method = 'GET', token, body, headers = {} } = {}) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method,
    headers: {
      ...(body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    body:
      body == null
        ? undefined
        : body instanceof FormData
          ? body
          : typeof body === 'string'
            ? body
            : JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${method} ${pathname} failed ${res.status}: ${await res.text()}`)
  return res.json()
}

async function configureMockLlm(profiles) {
  return apiJson('/api/e2e/dev/mock-llm/configure', {
    method: 'POST',
    headers: seedHeaders(),
    body: { profiles },
  })
}

async function processQueuedTasks(maxTasks = 1) {
  const gradingState = await apiJson('/api/e2e/dev/grading-state', {
    headers: seedHeaders(),
  })
  if (gradingState.worker?.running) {
    await expect
      .poll(async () => {
        const state = await apiJson('/api/e2e/dev/grading-state', {
          headers: seedHeaders(),
        })
        return (state.tasks?.queued || 0) + (state.tasks?.processing || 0)
      }, { timeout: 30000 })
      .toBe(0)
    return { processed: null, mode: 'worker' }
  }
  let total = 0
  for (let i = 0; i < 6; i += 1) {
    const res = await apiJson('/api/e2e/dev/process-grading', {
      method: 'POST',
      headers: seedHeaders(),
      body: { max_tasks: maxTasks },
    })
    total += res.processed || 0
    if ((res.processed || 0) === 0) {
      await new Promise(resolve => setTimeout(resolve, 250))
    }
  }
  return { processed: total, mode: 'manual' }
}

async function mockLlmState() {
  return apiJson('/api/e2e/dev/mock-llm/state', {
    headers: seedHeaders(),
  })
}

async function createPreset(adminToken, name, profile, options = {}) {
  return apiJson('/api/llm-settings/presets', {
    method: 'POST',
    token: adminToken,
    body: {
      name,
      base_url: `${apiBase()}/api/e2e/dev/mock-llm/${profile}/v1/`,
      api_key: options.api_key || 'mock-api-key',
      model_name: options.model_name || 'mock-model',
      connect_timeout_seconds: options.connect_timeout_seconds || 2,
      read_timeout_seconds: options.read_timeout_seconds || 2,
      max_retries: options.max_retries ?? 0,
      initial_backoff_seconds: options.initial_backoff_seconds || 1,
      is_active: options.is_active ?? true,
    },
  })
}

async function validatePreset(adminToken, presetId) {
  return apiJson('/api/e2e/dev/mark-preset-validated', {
    method: 'POST',
    headers: seedHeaders(),
    body: { preset_id: presetId },
  })
}

async function createValidatedPreset(adminToken, name, profile, options = {}) {
  const preset = await createPreset(adminToken, name, profile, options)
  return validatePreset(adminToken, preset.id)
}

async function listPresets(token) {
  return apiJson('/api/llm-settings/presets', { token })
}

async function courseConfig(token, subjectId) {
  return apiJson(`/api/llm-settings/courses/${subjectId}`, { token })
}

async function updateCourseConfig(token, subjectId, payload) {
  return apiJson(`/api/llm-settings/courses/${subjectId}`, {
    method: 'PUT',
    token,
    body: payload,
  })
}

async function setFlatCourseConfig(token, subjectId, presetIds, extra = {}) {
  return updateCourseConfig(token, subjectId, {
    is_enabled: true,
    response_language: 'zh-CN',
    max_input_tokens: 16000,
    max_output_tokens: 1200,
    system_prompt: null,
    teacher_prompt: null,
    endpoints: presetIds.map((presetId, index) => ({ preset_id: presetId, priority: index + 1 })),
    replace_group_routing_with_flat_endpoints: true,
    ...extra,
  })
}

async function setGroupCourseConfig(token, subjectId, groups, extra = {}) {
  return updateCourseConfig(token, subjectId, {
    is_enabled: true,
    response_language: 'zh-CN',
    max_input_tokens: 16000,
    max_output_tokens: 1200,
    system_prompt: null,
    teacher_prompt: null,
    groups,
    endpoints: [],
    replace_group_routing_with_flat_endpoints: false,
    ...extra,
  })
}

async function createHomework(token, ctx, title, extra = {}) {
  return apiJson('/api/homeworks', {
    method: 'POST',
    token,
    body: {
      title,
      content: extra.content || `E2E LLM content ${title}`,
      attachment_name: null,
      attachment_url: null,
      due_date: null,
      max_score: 100,
      grade_precision: 'integer',
      auto_grading_enabled: extra.auto_grading_enabled ?? true,
      rubric_text: extra.rubric_text || null,
      rubric_staff_only: extra.rubric_staff_only || null,
      reference_answer: extra.reference_answer || null,
      response_language: extra.response_language || 'zh-CN',
      allow_late_submission: true,
      late_submission_affects_score: false,
      max_submissions: extra.max_submissions ?? null,
      llm_routing_spec: extra.llm_routing_spec ?? null,
      class_id: ctx.class_id_1,
      subject_id: ctx.course_required_id,
    },
  })
}

async function updateHomework(token, homeworkId, payload) {
  return apiJson(`/api/homeworks/${homeworkId}`, {
    method: 'PUT',
    token,
    body: payload,
  })
}

async function mySubmissionHistory(token, homeworkId) {
  return apiJson(`/api/homeworks/${homeworkId}/submission/me/history`, { token })
}

async function teacherSubmissionList(token, homeworkId) {
  return apiJson(`/api/homeworks/${homeworkId}/submissions?page=1&page_size=100`, { token })
}

async function setStudentQuotaOverride(token, studentId, dailyTokens) {
  return apiJson(`/api/llm-settings/admin/students/${studentId}/quota-override`, {
    method: 'PUT',
    token,
    body: { daily_tokens: dailyTokens, clear_override: false },
  })
}

async function clearStudentQuotaOverride(token, studentId) {
  return apiJson(`/api/llm-settings/admin/students/${studentId}/quota-override`, {
    method: 'PUT',
    token,
    body: { clear_override: true },
  })
}

async function studentQuotaSummary(token) {
  return apiJson('/api/llm-settings/courses/student-quotas', { token })
}

async function fillWrappedInput(root, value) {
  const input = root.locator('input, textarea').first()
  await input.fill(value)
}

async function chooseFeedbackFollowup(page) {
  await page.getByTestId('homework-submit-mode').locator('label').nth(1).click()
}

async function submitHomeworkUi(page, homeworkId, content, options = {}) {
  await page.goto(`/homework/${homeworkId}/submit`)
  await expect(page.getByTestId('homework-submit-save')).toBeVisible({ timeout: 20000 })
  await page.getByTestId('homework-submit-content').fill(content)
  if (options.usedLlmAssist) {
    await page.getByTestId('homework-submit-used-llm-assist').click()
  }
  if (options.feedbackFollowup) {
    await chooseFeedbackFollowup(page)
  }
  const [response] = await Promise.all([
    page.waitForResponse(resp => resp.url().includes(`/api/homeworks/${homeworkId}/submission`) && resp.request().method() === 'POST'),
    page.getByTestId('homework-submit-save').click(),
  ])
  expect(response.ok(), `submission failed: ${response.status()} ${await response.text()}`).toBeTruthy()
  if (options.token) {
    await expect
      .poll(async () => {
        const history = await mySubmissionHistory(options.token, homeworkId)
        return history.summary?.latest_task_status || null
      }, { timeout: 30000 })
      .not.toBeNull()
  }
  await expect(
    page
      .locator('.el-alert__title, .el-tag__content')
      .filter({ hasText: /自动评分任务状态|排队中|评分成功|评分失败/ })
      .first()
  ).toBeVisible({ timeout: 20000 })
}

async function openHomeworkEditDialog(page, title) {
  await page.goto('/homework')
  const row = page.getByRole('row', { name: new RegExp(escapeRegex(title)) })
  await expect(row).toBeVisible({ timeout: 20000 })
  await row.getByTestId('homework-btn-edit').click()
  await expect(page.getByRole('dialog')).toBeVisible({ timeout: 15000 })
}

async function configureHomeworkLimitPresetViaUi(page, title, preset) {
  await openHomeworkEditDialog(page, title)
  await page.getByTestId('homework-llm-routing-mode').click()
  await page.getByRole('option', { name: /仅使用下方勾选的课程端点预设/ }).click()
  await page.getByTestId('homework-llm-preset-multi').click()
  await page.getByRole('option', { name: new RegExp(`${escapeRegex(preset.name)} \\(#${preset.id}\\)`) }).click()
  await page.getByTestId('homework-form-save').click()
  await expect(page.getByRole('dialog')).toBeHidden({ timeout: 25000 })
}

async function selectSubmissionRow(page, username) {
  const row = page.locator('tr').filter({ hasText: username }).first()
  await expect(row).toBeVisible({ timeout: 20000 })
  await row.locator('.el-checkbox').first().click()
}

async function waitForSummaryStatus(token, homeworkId, status) {
  await expect
    .poll(async () => {
      const history = await mySubmissionHistory(token, homeworkId)
      return history.summary?.latest_task_status || null
    }, { timeout: 30000 })
    .toBe(status)
}

async function waitForReviewScore(token, homeworkId, score) {
  await expect
    .poll(async () => {
      const history = await mySubmissionHistory(token, homeworkId)
      return history.summary?.review_score ?? null
    }, { timeout: 30000 })
    .toBe(score)
}

test.describe('E2E LLM hard scenarios', () => {
  test.describe.configure({ timeout: 180_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e/.cache/scenario.json; run Playwright globalSetup first')
    }
  })

  test('school UI preset create+validate propagates to teacher course config and homework routing picker', async ({ page }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const presetName = `E2E_UI_PRESET_${s.suffix}_${Date.now()}`
    await configureMockLlm({ ui_visible: { steps: [{ kind: 'ok', text: 'OK' }], repeat_last: true } })

    await login(page, s.admin.username, s.admin.password)
    await page.goto('/settings')
    await page.getByTestId('settings-llm-preset-create').click()
    const presetDialog = page.getByTestId('settings-llm-preset-dialog')
    await presetDialog.getByTestId('settings-llm-preset-name').fill(presetName)
    await presetDialog.getByTestId('settings-llm-preset-base-url').fill(apiBase() + '/api/e2e/dev/mock-llm/ui_visible/v1/')
    await presetDialog.getByTestId('settings-llm-preset-api-key').fill('ui-key')
    await presetDialog.getByTestId('settings-llm-preset-model').fill('ui-model')
    await page.getByTestId('settings-llm-preset-save').click()
    await expect(page.getByText(presetName)).toBeVisible({ timeout: 20000 })

    let preset = null
    await expect
      .poll(async () => {
        preset = (await listPresets(adminToken)).find(row => row.name === presetName) || null
        return Boolean(preset)
      }, { timeout: 30000 })
      .toBe(true)

    await validatePreset(adminToken, preset.id)

    await expect
      .poll(async () => (await listPresets(adminToken)).find(row => row.id === preset.id)?.validation_status || null, { timeout: 30000 })
      .toBe('validated')


    await expect
      .poll(async () => (await listPresets(adminToken)).find(row => row.id === preset.id)?.validation_status || null, { timeout: 30000 })
      .toBe('validated')

    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    await login(page, s.teacher_own.username, s.teacher_own.password)
    await page.goto('/subjects')
    await page.getByTestId('subjects-open-llm-' + s.course_required_id).click()
    await expect(page.getByTestId('dialog-course-llm')).toBeVisible({ timeout: 20000 })
    await expect(page.getByTestId('llm-course-preset-row-' + preset.id)).toHaveCount(1)
    await page.keyboard.press('Escape')

    const presets = await listPresets(teacherToken)
    expect(presets.some(row => row.name === presetName && row.validation_status === 'validated')).toBeTruthy()
  })

  test('teacher UI save updates course defaults without wiping API-configured llm groups', async ({ page }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)

    await configureMockLlm({
      keep_a: { steps: [{ kind: 'ok' }], repeat_last: true },
      keep_b: { steps: [{ kind: 'ok' }], repeat_last: true },
    })
    const presetA = await createValidatedPreset(adminToken, `keep-a-${s.suffix}-${Date.now()}`, 'keep_a')
    const presetB = await createValidatedPreset(adminToken, `keep-b-${s.suffix}-${Date.now()}`, 'keep_b')
    await setGroupCourseConfig(teacherToken, s.course_required_id, [
      { name: 'alpha', members: [{ preset_id: presetA.id, priority: 1 }] },
      { name: 'beta', members: [{ preset_id: presetB.id, priority: 1 }] },
    ])

    await login(page, s.teacher_own.username, s.teacher_own.password)
    await page.goto('/subjects')
    await page.getByTestId(`subjects-open-llm-${s.course_required_id}`).click()
    await expect(page.getByTestId('dialog-course-llm')).toBeVisible({ timeout: 20000 })
    const enableSwitch = page.getByTestId('dialog-course-llm').getByRole('switch')
    await page.getByTestId('llm-course-enable').click()
    await expect(enableSwitch).toHaveAttribute('aria-checked', 'false')
    await page.getByTestId('llm-course-save').click()
    await expect(page.getByTestId('dialog-course-llm')).toBeHidden({ timeout: 25000 })

    await expect
      .poll(async () => {
        const config = await courseConfig(teacherToken, s.course_required_id)
        return {
          is_enabled: Boolean(config.is_enabled),
          groups: (config.groups || []).map(g => `${g.name}:${(g.members || []).map(m => m.preset_id).join(',')}`),
        }
      }, { timeout: 30000 })
      .toEqual({
        is_enabled: false,
        groups: [`alpha:${presetA.id}`, `beta:${presetB.id}`],
      })
  })

  test('two students concurrent submissions fail over from group-1 endpoint to group-2 success', async ({ browser }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentAToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const studentBToken = await obtainAccessToken(s.student_b.username, s.student_b.password)

    await configureMockLlm({
      g1_fail: { steps: [{ kind: 'http_error', status_code: 500, body: 'group1 failed' }], repeat_last: true },
      g2_ok: { steps: [{ kind: 'ok', score: 91, comment: 'group2 ok' }], repeat_last: true },
    })
    const presetFail = await createValidatedPreset(adminToken, `g1-${s.suffix}-${Date.now()}`, 'g1_fail')
    const presetOk = await createValidatedPreset(adminToken, `g2-${s.suffix}-${Date.now()}`, 'g2_ok')
    await configureMockLlm({
      g1_fail: { steps: [{ kind: 'http_error', status_code: 500, body: 'group1 failed' }], repeat_last: true },
      g2_ok: { steps: [{ kind: 'ok', score: 91, comment: 'group2 ok' }], repeat_last: true },
    })
    await setGroupCourseConfig(teacherToken, s.course_required_id, [
      { name: 'primary', members: [{ preset_id: presetFail.id, priority: 1 }] },
      { name: 'secondary', members: [{ preset_id: presetOk.id, priority: 1 }] },
    ])
    const hw = await createHomework(teacherToken, s, `E2E_LLM_GROUP_FAILOVER_${Date.now()}`)

    const ctxA = await browser.newContext()
    const ctxB = await browser.newContext()
    const pageA = await ctxA.newPage()
    const pageB = await ctxB.newPage()
    try {
      await login(pageA, s.student_plain.username, s.student_plain.password)
      await login(pageB, s.student_b.username, s.student_b.password)
      await Promise.all([
        submitHomeworkUi(pageA, hw.id, 'group failover A ' + Date.now(), { token: studentAToken }),
        submitHomeworkUi(pageB, hw.id, 'group failover B ' + Date.now(), { token: studentBToken }),
      ])
      await processQueuedTasks(4)
      await Promise.all([
        waitForSummaryStatus(studentAToken, hw.id, 'success'),
        waitForSummaryStatus(studentBToken, hw.id, 'success'),
      ])
      await Promise.all([
        waitForReviewScore(studentAToken, hw.id, 91),
        waitForReviewScore(studentBToken, hw.id, 91),
      ])
      const state = await mockLlmState()
      expect((state.profiles.g1_fail.requests || []).length).toBeGreaterThanOrEqual(2)
      expect((state.profiles.g2_ok.requests || []).length).toBeGreaterThanOrEqual(2)
    } finally {
      await ctxA.close().catch(() => {})
      await ctxB.close().catch(() => {})
    }
  })

  test('latest-passing homework routing switches to the newly validated preset after the first student finishes', async ({ browser }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentAToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const studentBToken = await obtainAccessToken(s.student_b.username, s.student_b.password)

    await configureMockLlm({ old_latest: { steps: [{ kind: 'ok', score: 61, comment: 'old latest' }], repeat_last: true } })
    const oldPreset = await createValidatedPreset(adminToken, `old-latest-${s.suffix}-${Date.now()}`, 'old_latest')
    await setFlatCourseConfig(teacherToken, s.course_required_id, [oldPreset.id])
    const hw = await createHomework(teacherToken, s, `E2E_LATEST_PASSING_${Date.now()}`, {
      llm_routing_spec: { mode: 'latest_passing_validated' },
    })

    const ctxA = await browser.newContext()
    const pageA = await ctxA.newPage()
    try {
      await login(pageA, s.student_plain.username, s.student_plain.password)
      await submitHomeworkUi(pageA, hw.id, `old latest content ${Date.now()}`, { token: studentAToken })
      await processQueuedTasks(6)
      await waitForSummaryStatus(studentAToken, hw.id, 'success')
      await waitForReviewScore(studentAToken, hw.id, 61)
      const stateBeforeSwitch = await mockLlmState()
      expect((stateBeforeSwitch.profiles.old_latest.requests || []).length).toBeGreaterThanOrEqual(1)
    } finally {
      await ctxA.close().catch(() => {})
    }

    await configureMockLlm({
      old_latest: { steps: [{ kind: 'ok', score: 61, comment: 'old latest' }], repeat_last: true },
      new_latest: { steps: [{ kind: 'ok', score: 96, comment: 'new latest' }], repeat_last: true },
    })
    await createValidatedPreset(adminToken, `new-latest-${s.suffix}-${Date.now()}`, 'new_latest')

    const ctxB = await browser.newContext()
    const pageB = await ctxB.newPage()
    try {
      await login(pageB, s.student_b.username, s.student_b.password)
      await submitHomeworkUi(pageB, hw.id, `new latest content ${Date.now()}`, { token: studentBToken })
      await processQueuedTasks(2)
      await waitForReviewScore(studentBToken, hw.id, 96)
      const state = await mockLlmState()
      expect((state.profiles.new_latest.requests || []).length).toBeGreaterThanOrEqual(1)
    } finally {
      await ctxB.close().catch(() => {})
    }
  })

  test('homework preset override limits concurrent grading to the allowed preset only', async ({ browser, page }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentAToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const studentBToken = await obtainAccessToken(s.student_b.username, s.student_b.password)

    await configureMockLlm({
      limit_a: { steps: [{ kind: 'ok', score: 40, comment: 'should not be used' }], repeat_last: true },
      limit_b: { steps: [{ kind: 'ok', score: 88, comment: 'allowed preset' }], repeat_last: true },
    })
    const presetA = await createValidatedPreset(adminToken, `limit-a-${s.suffix}-${Date.now()}`, 'limit_a')
    const presetB = await createValidatedPreset(adminToken, `limit-b-${s.suffix}-${Date.now()}`, 'limit_b')
    await configureMockLlm({
      limit_a: { steps: [{ kind: 'ok', score: 40, comment: 'should not be used' }], repeat_last: true },
      limit_b: { steps: [{ kind: 'ok', score: 88, comment: 'allowed preset' }], repeat_last: true },
    })
    await setGroupCourseConfig(teacherToken, s.course_required_id, [
      { name: 'g1', members: [{ preset_id: presetA.id, priority: 1 }] },
      { name: 'g2', members: [{ preset_id: presetB.id, priority: 1 }] },
    ])
    const title = `E2E_LIMIT_PRESETS_${Date.now()}`
    const hw = await createHomework(teacherToken, s, title)

    await updateHomework(teacherToken, hw.id, { llm_routing_spec: { mode: 'limit_to_preset_ids', preset_ids: [presetB.id] } })



    const ctxA = await browser.newContext()
    const ctxB = await browser.newContext()
    const pageA = await ctxA.newPage()
    const pageB = await ctxB.newPage()
    try {
      await login(pageA, s.student_plain.username, s.student_plain.password)
      await login(pageB, s.student_b.username, s.student_b.password)
      await Promise.all([
        submitHomeworkUi(pageA, hw.id, `limit preset A ${Date.now()}`, { token: studentAToken }),
        submitHomeworkUi(pageB, hw.id, `limit preset B ${Date.now()}`, { token: studentBToken }),
      ])
      await processQueuedTasks(4)
      await Promise.all([
        waitForReviewScore(studentAToken, hw.id, 88),
        waitForReviewScore(studentBToken, hw.id, 88),
      ])
      const state = await mockLlmState()
      expect((state.profiles.limit_a.requests || []).length).toBe(0)
      expect((state.profiles.limit_b.requests || []).length).toBeGreaterThanOrEqual(2)
    } finally {
      await ctxA.close().catch(() => {})
      await ctxB.close().catch(() => {})
    }
  })

  test('failed bad-grading payloads can be recovered through teacher batch regrade without duplicate final records', async ({ browser, page }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentAToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const studentBToken = await obtainAccessToken(s.student_b.username, s.student_b.password)

    await configureMockLlm({ bad_payload: { steps: [{ kind: 'bad_grading_payload' }], repeat_last: true } })
    const preset = await createValidatedPreset(adminToken, `bad-payload-${s.suffix}-${Date.now()}`, 'bad_payload')
    await configureMockLlm({ bad_payload: { steps: [{ kind: 'bad_grading_payload' }], repeat_last: true } })
    await setFlatCourseConfig(teacherToken, s.course_required_id, [preset.id])
    const hw = await createHomework(teacherToken, s, `E2E_BAD_PAYLOAD_${Date.now()}`)

    const ctxA = await browser.newContext()
    const ctxB = await browser.newContext()
    const pageA = await ctxA.newPage()
    const pageB = await ctxB.newPage()
    try {
      await login(pageA, s.student_plain.username, s.student_plain.password)
      await login(pageB, s.student_b.username, s.student_b.password)
      await Promise.all([
        submitHomeworkUi(pageA, hw.id, `bad payload A ${Date.now()}`, { token: studentAToken }),
        submitHomeworkUi(pageB, hw.id, `bad payload B ${Date.now()}`, { token: studentBToken }),
      ])
      await processQueuedTasks(4)
      await Promise.all([
        waitForSummaryStatus(studentAToken, hw.id, 'retry_scheduled'),
        waitForSummaryStatus(studentBToken, hw.id, 'retry_scheduled'),
      ])
    } finally {
      await ctxA.close().catch(() => {})
      await ctxB.close().catch(() => {})
    }

    await configureMockLlm({ bad_payload: { steps: [{ kind: 'ok', score: 78, comment: 'recovered' }], repeat_last: true } })
    await login(page, s.teacher_own.username, s.teacher_own.password)
    await page.goto(`/homework/${hw.id}/submissions`)
    await selectSubmissionRow(page, s.student_plain.username)
    await selectSubmissionRow(page, s.student_b.username)
    await page.getByTestId('homework-submissions-batch-regrade').click()
    await processQueuedTasks(4)

    await Promise.all([
      waitForReviewScore(studentAToken, hw.id, 78),
      waitForReviewScore(studentBToken, hw.id, 78),
    ])
    const teacherList = await teacherSubmissionList(teacherToken, hw.id)
    expect((teacherList.data || []).filter(row => row.review_score === 78)).toHaveLength(2)
  })

  test('per-student quota overrides split concurrent llm calls into one failure and one success', async ({ browser, page }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentAToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const studentBToken = await obtainAccessToken(s.student_b.username, s.student_b.password)

    await configureMockLlm({
      quota_split: {
        steps: [{
          kind: 'ok',
          score: 82,
          comment: 'quota ok',
          usage: { prompt_tokens: 80, completion_tokens: 10, total_tokens: 90 },
        }],
        repeat_last: true,
      },
    })
    const preset = await createValidatedPreset(adminToken, `quota-${s.suffix}-${Date.now()}`, 'quota_split')
    await configureMockLlm({
      quota_split: {
        steps: [{
          kind: 'ok',
          score: 82,
          comment: 'quota ok',
          usage: { prompt_tokens: 80, completion_tokens: 10, total_tokens: 90 },
        }],
        repeat_last: true,
      },
    })
    await setFlatCourseConfig(teacherToken, s.course_required_id, [preset.id])
    await setStudentQuotaOverride(adminToken, s.student_plain.student_row_id, 30)
    await setStudentQuotaOverride(adminToken, s.student_b.student_row_id, 100000)
    const hw = await createHomework(teacherToken, s, `E2E_QUOTA_SPLIT_${Date.now()}`)

    const ctxA = await browser.newContext()
    const ctxB = await browser.newContext()
    const pageA = await ctxA.newPage()
    const pageB = await ctxB.newPage()
    try {
      await login(pageA, s.student_plain.username, s.student_plain.password)
      await login(pageB, s.student_b.username, s.student_b.password)
      await Promise.all([
        submitHomeworkUi(pageA, hw.id, `quota split A ${Date.now()}`, { token: studentAToken }),
        submitHomeworkUi(pageB, hw.id, `quota split B ${Date.now()}`, { token: studentBToken }),
      ])
      await processQueuedTasks(4)
      await waitForSummaryStatus(studentAToken, hw.id, 'failed')
      await waitForSummaryStatus(studentBToken, hw.id, 'success')
      await waitForReviewScore(studentBToken, hw.id, 82)
      await login(page, s.student_plain.username, s.student_plain.password)
      await page.goto('/courses')
      await expect(page.getByText('全站 LLM 日额度')).toBeVisible({ timeout: 15000 })

      const quotaA = await studentQuotaSummary(studentAToken)
      const rowA = (quotaA.courses || []).find(row => Number(row.subject_id) === Number(s.course_required_id))
      expect(rowA).toBeTruthy()
      expect(Number(rowA?.student_remaining_tokens_today || 0)).toBeLessThanOrEqual(30)
    } finally {
      await clearStudentQuotaOverride(adminToken, s.student_plain.student_row_id).catch(() => {})
      await clearStudentQuotaOverride(adminToken, s.student_b.student_row_id).catch(() => {})
      await ctxA.close().catch(() => {})
      await ctxB.close().catch(() => {})
    }
  })

  test('teacher detail view does not execute malicious student html while grading still succeeds', async ({ page }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    await configureMockLlm({ safe_html: { steps: [{ kind: 'ok', score: 75, comment: 'safe html ok' }], repeat_last: true } })
    const preset = await createValidatedPreset(adminToken, `safe-html-${s.suffix}-${Date.now()}`, 'safe_html')
    await configureMockLlm({ safe_html: { steps: [{ kind: 'ok', score: 75, comment: 'safe html ok' }], repeat_last: true } })
    await setFlatCourseConfig(teacherToken, s.course_required_id, [preset.id])
    const hw = await createHomework(teacherToken, s, `E2E_SAFE_HTML_${Date.now()}`)

    await login(page, s.student_plain.username, s.student_plain.password)
    await submitHomeworkUi(page, hw.id, '<script>window.__e2eInjected=1</script>\n**bold** raw payload', { token: studentToken })
    await processQueuedTasks(2)
    await waitForReviewScore(studentToken, hw.id, 75)

    await login(page, s.teacher_own.username, s.teacher_own.password)
    await page.goto(`/homework/${hw.id}/submissions`)
    await page.getByTestId('homework-submission-detail-' + s.student_plain.username).click()
    await expect(page.getByTestId('homework-submission-detail-body')).toContainText('<script>window.__e2eInjected=1</script>')
    expect(await page.evaluate(() => window.__e2eInjected || 0)).toBe(0)
  })

  test('student relogin recovers failed llm status and later sees regrade success as the authoritative state', async ({ browser, page }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)

    await configureMockLlm({ relogin_flow: { steps: [{ kind: 'bad_grading_payload' }], repeat_last: true } })
    const preset = await createValidatedPreset(adminToken, `relogin-${s.suffix}-${Date.now()}`, 'relogin_flow')
    await configureMockLlm({ relogin_flow: { steps: [{ kind: 'bad_grading_payload' }], repeat_last: true } })
    await setFlatCourseConfig(teacherToken, s.course_required_id, [preset.id])
    const hw = await createHomework(teacherToken, s, `E2E_RELOGIN_${Date.now()}`)

    const studentCtx = await browser.newContext()
    const studentPage = await studentCtx.newPage()
    try {
      await login(studentPage, s.student_plain.username, s.student_plain.password)
      await submitHomeworkUi(studentPage, hw.id, `relogin content ${Date.now()}`, { token: studentToken })
      await processQueuedTasks(2)
      await waitForSummaryStatus(studentToken, hw.id, 'retry_scheduled')
    } finally {
      await studentCtx.close().catch(() => {})
    }

    const studentCtx2 = await browser.newContext()
    const studentPage2 = await studentCtx2.newPage()
    try {
      await login(studentPage2, s.student_plain.username, s.student_plain.password)
      await studentPage2.goto(`/homework/${hw.id}/submit`)
      await expect(
        studentPage2
          .locator('.el-alert__title, .el-tag__content')
          .filter({ hasText: /自动评分任务状态|排队中|处理中/ })
          .first()
      ).toBeVisible({ timeout: 20000 })
    } finally {
      await studentCtx2.close().catch(() => {})
    }

    await configureMockLlm({ relogin_flow: { steps: [{ kind: 'ok', score: 87, comment: 'relogin recovered' }], repeat_last: true } })
    await login(page, s.teacher_own.username, s.teacher_own.password)
    await page.goto(`/homework/${hw.id}/submissions`)
    await page.getByTestId('homework-submission-regrade-' + s.student_plain.username).click()
    await processQueuedTasks(2)
    await waitForReviewScore(studentToken, hw.id, 87)

    const studentCtx3 = await browser.newContext()
    const studentPage3 = await studentCtx3.newPage()
    try {
      await login(studentPage3, s.student_plain.username, s.student_plain.password)
      await studentPage3.goto('/homework/' + hw.id + '/submit')
      await expect(studentPage3.getByText('87').first()).toBeVisible({ timeout: 20000 })
    } finally {
      await studentCtx3.close().catch(() => {})
    }
  })

  test('stale selected_course can still complete feedback-followup flow and converge to the latest attempt score', async ({ page }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)

    await configureMockLlm({ followup: { steps: [{ kind: 'ok', score: 40, comment: 'please improve section 2' }], repeat_last: true } })
    const preset = await createValidatedPreset(adminToken, `followup-${s.suffix}-${Date.now()}`, 'followup')
    await configureMockLlm({ followup: { steps: [{ kind: 'ok', score: 40, comment: 'please improve section 2' }], repeat_last: true } })
    await setFlatCourseConfig(teacherToken, s.course_required_id, [preset.id])
    const hw = await createHomework(teacherToken, s, `E2E_FOLLOWUP_${Date.now()}`)

    await login(page, s.student_plain.username, s.student_plain.password)
    await page.evaluate(() => {
      localStorage.setItem('selected_course', JSON.stringify({ id: 999999, name: 'stale-course' }))
    })
    await submitHomeworkUi(page, hw.id, `followup first ${Date.now()}`, { token: studentToken })
    await processQueuedTasks(2)

    await configureMockLlm({ followup: { steps: [{ kind: 'ok', score: 89, comment: 'improved' }], repeat_last: true } })
    await page.goto(`/homework/${hw.id}/submit`)
    await chooseFeedbackFollowup(page)
    await page.getByTestId('homework-submit-content').fill(`followup second ${Date.now()}`)
    await page.getByTestId('homework-submit-save').click()
    await processQueuedTasks(2)
    await waitForReviewScore(studentToken, hw.id, 89)

    await expect
      .poll(async () => {
        const history = await mySubmissionHistory(studentToken, hw.id)
        return {
          attempts: (history.attempts || []).length,
          latestScore: history.summary?.review_score ?? null,
          mode: history.attempts?.[0]?.submission_mode || null,
        }
      }, { timeout: 30000 })
      .toEqual({
        attempts: 2,
        latestScore: 89,
        mode: 'feedback_followup',
      })
  })

  test('single-student 429 retry succeeds without creating duplicate final grading rows', async ({ page }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)

    await configureMockLlm({
      retry429: {
        steps: [
          { kind: 'rate_limit', status_code: 429, body: { error: 'slow down' } },
          { kind: 'ok', score: 66, comment: 'retry success' },
        ],
        repeat_last: true,
      },
    })
    const preset = await createValidatedPreset(adminToken, `retry429-${s.suffix}-${Date.now()}`, 'retry429', { max_retries: 1 })
    await configureMockLlm({
      retry429: {
        steps: [
          { kind: 'rate_limit', status_code: 429, body: { error: 'slow down' } },
          { kind: 'ok', score: 66, comment: 'retry success' },
        ],
        repeat_last: true,
      },
    })
    await setFlatCourseConfig(teacherToken, s.course_required_id, [preset.id])
    const hw = await createHomework(teacherToken, s, `E2E_RETRY_429_${Date.now()}`)

    await login(page, s.student_plain.username, s.student_plain.password)
    await submitHomeworkUi(page, hw.id, `retry429 ${Date.now()}`, { usedLlmAssist: true, token: studentToken })
    await processQueuedTasks(2)
    await waitForReviewScore(studentToken, hw.id, 66)

    const state = await mockLlmState()
    expect((state.profiles.retry429.requests || []).length).toBeGreaterThanOrEqual(2)
    const history = await mySubmissionHistory(studentToken, hw.id)
    expect((history.attempts || []).length).toBe(1)
    expect(history.summary?.used_llm_assist).toBe(true)
  })

  test('teacher submission log shows routing failure details before a repaired regrade succeeds', async ({ page }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)

    await configureMockLlm({ log_case: { steps: [{ kind: 'http_error', status_code: 500, body: 'log-fail' }], repeat_last: true } })
    const preset = await createValidatedPreset(adminToken, `log-case-${s.suffix}-${Date.now()}`, 'log_case')
    await configureMockLlm({ log_case: { steps: [{ kind: 'http_error', status_code: 500, body: 'log-fail' }], repeat_last: true } })
    await setFlatCourseConfig(teacherToken, s.course_required_id, [preset.id])
    const hw = await createHomework(teacherToken, s, `E2E_LOG_CASE_${Date.now()}`)

    await login(page, s.student_plain.username, s.student_plain.password)
    await submitHomeworkUi(page, hw.id, `log case ${Date.now()}`, { token: studentToken })
    await processQueuedTasks(2)
    await waitForSummaryStatus(studentToken, hw.id, 'retry_scheduled')

    await login(page, s.teacher_own.username, s.teacher_own.password)
    await page.goto(`/homework/${hw.id}/submissions`)
    await page.getByTestId('homework-submission-log-' + s.student_plain.username).click()
    await expect(page.getByTestId('dialog-llm-log-body')).toContainText('log-fail')
    await expect(page.getByTestId('dialog-llm-log-body')).toContainText('routing')
    await configureMockLlm({ log_case: { steps: [{ kind: 'ok', score: 93, comment: 'log recovered' }], repeat_last: true } })
    await page.keyboard.press('Escape')
    await page.getByTestId('homework-submission-regrade-' + s.student_plain.username).click()
    await processQueuedTasks(2)
    await waitForReviewScore(studentToken, hw.id, 93)
  })
})
