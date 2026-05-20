/**
 * E2E: discussion LLM assistant, long-body preview/collapse, course cover images.
 * Multi-role, concurrency, mock LLM reconfiguration, cold navigation, error paths.
 * Requires globalSetup + E2E_DEV_SEED_TOKEN (same as other e2e specs).
 */
const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario, enterSeededRequiredCourse } = require('./fixtures.cjs')
const { login } = require('./future-advanced-coverage-helpers.cjs')
const { seedHeaders } = require('./e2e-seed-headers.cjs')

const scenario = () => loadE2eScenario()

/** 1×1 transparent PNG */
const ONE_PX_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64'
)

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
  return { status: res.status, json: text ? JSON.parse(text) : null }
}

async function apiPatchSubject(token, subjectId, payload) {
  const res = await fetch(`${apiBase()}/api/subjects/${subjectId}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`
    },
    body: JSON.stringify(payload)
  })
  const text = await res.text()
  return { status: res.status, json: text ? JSON.parse(text) : null }
}

async function apiUploadFile(token, buffer, filename = 'e2e.png', contentType = 'image/png') {
  const blob = new Blob([buffer], { type: contentType })
  const form = new FormData()
  form.append('file', blob, filename)
  const res = await fetch(`${apiBase()}/api/files/upload`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form
  })
  const text = await res.text()
  return { status: res.status, json: text ? JSON.parse(text) : null }
}

async function configureDiscussMock(profile, cfg) {
  const headers = { 'Content-Type': 'application/json', ...seedHeaders() }
  const res = await fetch(`${apiBase()}/api/e2e/dev/mock-llm/configure`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ profiles: { [profile]: cfg } })
  })
  if (!res.ok) {
    throw new Error(`mock-llm configure failed ${res.status}: ${await res.text()}`)
  }
  return res.json()
}

function escapeRegex(text) {
  return `${text || ''}`.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

async function expandDiscussionComposer(scope) {
  if (await scope.getByTestId('discussion-llm-toggle').isVisible().catch(() => false)) {
    return
  }
  const section = scope.locator('.discussion-composer-section').first()
  await expect(section).toBeVisible({ timeout: 15000 })
  const toggle = section.getByRole('button', { name: '写回复' })
  if (await toggle.isVisible({ timeout: 15000 }).catch(() => false)) {
    await toggle.click()
  }
  await expect(section.locator('.discussion-composer-body')).toBeVisible({ timeout: 15000 })
}

async function findDiscussionRowAcrossPages(page, text) {
  const row = page.locator('.discussion-row').filter({ hasText: text })
  for (let i = 0; i < 4; i++) {
    if (await row.first().isVisible().catch(() => false)) {
      return row.first()
    }
    const next = page.locator('.discussion-list-section .el-pagination').getByRole('button', { name: '下一页' })
    if (!(await next.isEnabled().catch(() => false))) {
      break
    }
    await next.click()
  }
  await expect(row.first()).toBeVisible({ timeout: 20000 })
  return row.first()
}

test.describe('E2E discussion LLM + long preview + course cover (tier-3)', () => {
  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e scenario — set E2E_DEV_SEED_TOKEN and globalSetup')
    }
    if (!s.discussion_llm_profile) {
      testInfo.skip(true, 'Seeded scenario missing discussion_llm_profile')
    }
  })

  test('01 cold navigation: long API-seeded body shows ellipsis; click expands and 收起 collapses', async ({
    page
  }) => {
    const s = scenario()
    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const body = ['L1-cold', 'L2-cold', 'L3-cold', 'L4-cold-hidden'].join('\n')
    const r = await apiPostDiscussion(teTok, {
      target_type: 'homework',
      target_id: s.homework_id,
      subject_id: s.course_required_id,
      class_id: s.class_id_1,
      body
    })
    expect(r.status).toBe(200)

    await login(page, s.teacher_own.username, s.password_teacher_student)
    await page.goto(`/homework/${s.homework_id}/submissions`, { waitUntil: 'load', timeout: 60000 })
    const row = page.locator('.discussion-row').filter({ hasText: 'L1-cold' })
    await expect(row).toBeVisible({ timeout: 20000 })
    await expect(row.locator('.discussion-row__text')).toContainText('...', { timeout: 10000 })
    await expect(row.locator('.discussion-row__text')).not.toContainText('L4-cold-hidden')
    await row.locator('.discussion-row__body').click()
    await expect(row.locator('.discussion-row__text')).toContainText('L4-cold-hidden', { timeout: 10000 })
    await row.getByRole('button', { name: '收起' }).click()
    await expect(row.locator('.discussion-row__text')).toContainText('...')
  })

  test('02 exactly three logical lines: no ellipsis (boundary)', async ({ page }) => {
    const s = scenario()
    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const body = ['b1', 'b2', 'b3'].join('\n')
    await apiPostDiscussion(teTok, {
      target_type: 'homework',
      target_id: s.homework_id,
      subject_id: s.course_required_id,
      class_id: s.class_id_1,
      body
    })
    await login(page, s.teacher_own.username, s.password_teacher_student)
    await page.goto(`/homework/${s.homework_id}/submissions`, { waitUntil: 'load', timeout: 60000 })
    const row = page.locator('.discussion-row').filter({ hasText: 'b1' })
    await expect(row).toBeVisible({ timeout: 20000 })
    await expect(row.locator('.discussion-row__text')).not.toContainText('...')
  })

  test('03 markdown image consumes one line slot: two text lines + image = full width; extra line truncates', async ({
    page
  }) => {
    const s = scenario()
    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const body = `img-line-a\nimg-line-b\n![](https://example.invalid/e2e.png)\nimg-line-d-trunc`
    await apiPostDiscussion(teTok, {
      target_type: 'homework',
      target_id: s.homework_id,
      subject_id: s.course_required_id,
      class_id: s.class_id_1,
      body
    })
    await login(page, s.teacher_own.username, s.password_teacher_student)
    await page.goto(`/homework/${s.homework_id}/submissions`, { waitUntil: 'load', timeout: 60000 })
    const row = page.locator('.discussion-row').filter({ hasText: 'img-line-a' })
    await expect(row.locator('.discussion-row__text')).toContainText('...')
    await expect(row.locator('.discussion-row__text')).not.toContainText('img-line-d-trunc')
  })

  test('04 HTML img tag counts as one logical line', async ({ page }) => {
    const s = scenario()
    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const body = `h1\nh2\n<img src="https://example.invalid/x.png" alt="x" />\nh4-trunc`
    await apiPostDiscussion(teTok, {
      target_type: 'homework',
      target_id: s.homework_id,
      subject_id: s.course_required_id,
      class_id: s.class_id_1,
      body
    })
    await login(page, s.teacher_own.username, s.password_teacher_student)
    await page.goto(`/homework/${s.homework_id}/submissions`, { waitUntil: 'load', timeout: 60000 })
    const row = page.locator('.discussion-row').filter({ hasText: 'h1' })
    await expect(row.locator('.discussion-row__text')).toContainText('...')
    await expect(row.locator('.discussion-row__text')).not.toContainText('h4-trunc')
  })

  test('05 concurrent invoke_llm and teacher plain post converge (API)', async () => {
    const s = scenario()
    await configureDiscussMock(s.discussion_llm_profile, {
      steps: [{ kind: 'ok', text: '【E2E并发助教】', usage: { prompt_tokens: 5, completion_tokens: 5, total_tokens: 10 } }],
      repeat_last: true
    })
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const base = {
      target_type: 'homework',
      target_id: s.homework_id,
      subject_id: s.course_required_id,
      class_id: s.class_id_1
    }
    const stamp = Date.now()
    const [r1, r2] = await Promise.all([
      apiPostDiscussion(stTok, { ...base, body: `@LLM\nconc-llm-${stamp}`, invoke_llm: true }),
      apiPostDiscussion(teTok, { ...base, body: `conc-plain-${stamp}` })
    ])
    expect([r1.status, r2.status].every(x => x === 200)).toBe(true)
    await expect
      .poll(
        async () => {
          const list = await apiListDiscussions(teTok, { ...base, page: 1, page_size: 50 })
          const bodies = (list.json?.data || []).map(x => x.body)
          return (
            bodies.some(b => String(b).includes(`conc-plain-${stamp}`)) &&
            bodies.some(b => String(b).includes('【E2E并发助教】'))
          )
        },
        { timeout: 45000, intervals: [500, 1000, 1500] }
      )
      .toBe(true)
  })

  test('06 teacher invoke_llm accepted (200)', async () => {
    const s = scenario()
    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const r = await apiPostDiscussion(teTok, {
      target_type: 'homework',
      target_id: s.homework_id,
      subject_id: s.course_required_id,
      class_id: s.class_id_1,
      body: '@LLM\nx',
      invoke_llm: true
    })
    expect(r.status).toBe(200)
    expect(r.json?.llm_invocation).toBe(true)
  })

  test('07 student UI: empty @LLM tail blocks submit (toast)', async ({ page }) => {
    const s = scenario()
    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.goto(`/homework/${s.homework_id}/submit`, { waitUntil: 'load', timeout: 60000 })
    await expandDiscussionComposer(page)
    await page.getByTestId('discussion-llm-toggle').click()
    await page.locator('.discussion-input textarea').fill('@LLM\n')
    await page.getByTestId('discussion-submit').click()
    await expect(page.locator('.el-message--warning').filter({ hasText: '@LLM' })).toBeVisible({
      timeout: 10000
    })
  })

  test('08 mock LLM failure keeps student row visible while no assistant reply is emitted yet', async ({ page }) => {
    const s = scenario()
    await configureDiscussMock(s.discussion_llm_profile, {
      steps: [{ kind: 'http_error', status_code: 503, body: { error: 'e2e-down' } }],
      repeat_last: true
    })
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const stamp = Date.now()
    const r = await apiPostDiscussion(stTok, {
      target_type: 'homework',
      target_id: s.homework_id,
      subject_id: s.course_required_id,
      class_id: s.class_id_1,
      body: `@LLM\nfail-${stamp}`,
      invoke_llm: true
    })
    expect(r.status).toBe(200)
    await expect
      .poll(async () => {
        const list = await apiListDiscussions(stTok, {
          target_type: 'homework',
          target_id: s.homework_id,
          subject_id: s.course_required_id,
          class_id: s.class_id_1,
          page: 1,
          page_size: 20,
        })
        return {
          hasAssistant: list.json?.data?.some?.(row => row.message_kind === 'llm_assistant') || false,
          hasUserRow: list.json?.data?.some?.(row => `${row.body || ''}`.includes(`fail-${stamp}`)) || false,
        }
      }, { timeout: 45000 })
      .toMatchObject({
        hasAssistant: false,
        hasUserRow: true,
      })
    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.goto(`/homework/${s.homework_id}/submit`, { waitUntil: 'load', timeout: 60000 })
    await expect(page.locator('.discussion-row').filter({ hasText: `fail-${stamp}` }).first()).toBeVisible({
      timeout: 15000,
    })
    await expect(page.locator('.discussion-row--assistant')).toHaveCount(0)
  })

  test('09 slow mock: UI poll eventually shows success assistant (sleep_then_ok)', async ({ page }) => {
    const s = scenario()
    await configureDiscussMock(s.discussion_llm_profile, {
      steps: [{ kind: 'sleep_then_ok', sleep_seconds: 2.5, text: '【E2E慢助教】', usage: { prompt_tokens: 8, completion_tokens: 4, total_tokens: 12 } }],
      repeat_last: true
    })
    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.goto(`/homework/${s.homework_id}/submit`, { waitUntil: 'load', timeout: 60000 })
    await expandDiscussionComposer(page)
    await page.getByTestId('discussion-llm-toggle').click()
    await page.locator('.discussion-input textarea').fill('')
    await page.locator('.discussion-input textarea').fill(`@LLM\nslow-ui-${Date.now()}`)
    await page.getByTestId('discussion-submit').click()
    await expect(page.locator('.discussion-row').filter({ hasText: '【E2E慢助教】' })).toBeVisible({
      timeout: 120000
    })
  })

  test('10 pagination clears expanded state for long body', async ({ page }) => {
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
      const r = await apiPostDiscussion(teTok, { ...base, body: `pg-long-${stamp}-${i}\nL2\nL3\nL4` })
      expect(r.status).toBe(200)
    }
    await login(page, s.teacher_own.username, s.password_teacher_student)
    await page.goto(`/homework/${s.homework_id}/submissions`, { waitUntil: 'load', timeout: 60000 })
    const longRow = await findDiscussionRowAcrossPages(page, `pg-long-${stamp}-10`)
    await expect(longRow.locator('.discussion-row__text')).toContainText('...')
    await longRow.locator('.discussion-row__body').click()
    await expect(longRow.locator('.discussion-row__text')).toContainText('L4', { timeout: 10000 })
    const pager = page.locator('.discussion-list-section .el-pagination')
    const prev = pager.getByRole('button', { name: '上一页' })
    const next = pager.getByRole('button', { name: '下一页' })
    if (await prev.isEnabled().catch(() => false)) {
      await prev.click()
      await next.click()
    } else {
      await next.click()
      await prev.click()
    }
    const longRow2 = page.locator('.discussion-row').filter({ hasText: `pg-long-${stamp}-10` }).first()
    await expect(longRow2.locator('.discussion-row__text')).toContainText('...')
  })

  test('11 material dialog: LLM bar visible for student; teacher post interleaved via API', async ({ page }) => {
    const s = scenario()
    await configureDiscussMock(s.discussion_llm_profile, {
      steps: [{ kind: 'ok', text: '【资料助教】', usage: { prompt_tokens: 3, completion_tokens: 3, total_tokens: 6 } }],
      repeat_last: true
    })
    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const base = {
      target_type: 'material',
      target_id: s.material_discussion_id,
      subject_id: s.course_required_id,
      class_id: s.class_id_1
    }
    const stamp = Date.now()
    await apiPostDiscussion(teTok, { ...base, body: `mat-plain-${stamp}` })
    await apiPostDiscussion(stTok, { ...base, body: `@LLM\nmat-llm-${stamp}`, invoke_llm: true })

    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.goto('/courses')
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto(`/materials/read/${s.material_discussion_id}`, { waitUntil: 'load', timeout: 60000 })
    await expect(page.getByRole('heading', { name: `E2E讨论资料_${s.suffix}` }).first()).toBeVisible({
      timeout: 20000,
    })
    const discussionScope = page.locator('.material-read-discussion')
    await expect(discussionScope.locator('.discussion-card')).toBeVisible({ timeout: 15000 })
    await expect(discussionScope.locator('.discussion-row__body').filter({ hasText: `mat-plain-${stamp}` })).toBeVisible({
      timeout: 45000
    })
    await expect(discussionScope.locator('.discussion-row__body').filter({ hasText: '【资料助教】' })).toBeVisible({
      timeout: 45000
    })
  })

  test('12 API cover_image_url then student catalog thumb + materials banner', async ({ page }) => {
    const s = scenario()
    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const up = await apiUploadFile(teTok, ONE_PX_PNG)
    expect(up.status).toBe(200)
    const url = up.json?.attachment_url
    expect(url).toBeTruthy()
    const patch = await apiPatchSubject(teTok, s.course_required_id, { cover_image_url: url })
    expect(patch.status).toBe(200)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.goto('/courses', { waitUntil: 'load', timeout: 60000 })
    await expect(page.getByTestId('course-catalog-cover-thumb').first()).toBeVisible({ timeout: 15000 })

    const namePat = new RegExp(`E2E必修课_${escapeRegex(s.suffix)}`)
    const card = page.locator('article.course-card').filter({ has: page.getByRole('heading', { name: namePat }) })
    await expect(card.getByTestId('course-card-cover')).toBeVisible({ timeout: 15000 })
    await card.getByRole('button', { name: /进入课程|查看课程/ }).click()
    await page.goto(`/materials/read/${s.material_discussion_id}`, { waitUntil: 'load', timeout: 60000 })
    await expect(page.getByRole('heading', { name: `E2E讨论资料_${s.suffix}` })).toBeVisible({ timeout: 15000 })
  })

  test('13 teacher removes cover via API; banner and catalog thumb disappear after reload', async ({ page }) => {
    const s = scenario()
    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const up = await apiUploadFile(teTok, ONE_PX_PNG)
    expect(up.status).toBe(200)
    await apiPatchSubject(teTok, s.course_required_id, { cover_image_url: up.json.attachment_url })
    const rm = await apiPatchSubject(teTok, s.course_required_id, { remove_cover_image: true })
    expect(rm.status).toBe(200)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.goto('/courses', { waitUntil: 'load', timeout: 60000 })
    await expect(page.getByTestId('course-catalog-cover-thumb')).toHaveCount(0)
  })

  test('14 teacher UI: pick tiny PNG in edit dialog uploads cover (stable id)', async ({ page }) => {
    const s = scenario()
    await login(page, s.teacher_own.username, s.password_teacher_student)
    await page.goto('/subjects', { waitUntil: 'load', timeout: 60000 })
    const row = page.getByRole('row', { name: new RegExp(`E2E必修课_${escapeRegex(s.suffix)}`) })
    await expect(row).toBeVisible({ timeout: 20000 })
    await row.getByRole('button', { name: '编辑' }).click()
    await page.getByTestId('subjects-course-cover-pick').click()
    const input = page.locator('.cover-file-input')
    await input.setInputFiles({
      name: 'e2e-cover-ui.png',
      mimeType: 'image/png',
      buffer: ONE_PX_PNG
    })
    await expect(page.getByRole('button', { name: '移除封面' })).toBeVisible({ timeout: 20000 })
  })

  test('15 @other stripped in draft while LLM mode on (no dead submit)', async ({ page }) => {
    const s = scenario()
    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.goto(`/homework/${s.homework_id}/submit`, { waitUntil: 'load', timeout: 60000 })
    await expandDiscussionComposer(page)
    await page.getByTestId('discussion-llm-toggle').click()
    await page.locator('.discussion-input textarea').fill('@LLM\n@ta hello')
    await expect(page.locator('.el-message--warning').filter({ hasText: '不支持 @' })).toBeVisible({
      timeout: 10000
    })
    const ta = await page.locator('.discussion-input textarea').inputValue()
    expect(ta).not.toMatch(/@ta\b/i)
  })
})
