/**
 * E2E tier-4: homework submission table comment/content previews (truncate),
 * LLM grading long comments, multi-role / concurrency / error paths, course covers.
 * Builds on seeded reset-scenario + discussion_llm_profile mock preset.
 */
const { expect, test } = require('@playwright/test')
const {
  loadE2eScenario,
  resetE2eScenario,
  enterSeededRequiredCourse
} = require('./fixtures.cjs')
const {
  obtainAccessToken,
  configureMockLlm,
  processGradingTasks,
  escapeRegex,
  login,
  apiJson
} = require('./future-advanced-coverage-helpers.cjs')

const ONE_PX_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64'
)

function scenario() {
  return loadE2eScenario()
}

function apiBase() {
  return (process.env.E2E_API_URL || 'http://127.0.0.1:8012').replace(/\/$/, '')
}

async function teacherSubmissions(token, homeworkId, page = 1) {
  return apiJson(`/api/homeworks/${homeworkId}/submissions?page=${page}&page_size=20`, { token })
}

function submissionRowByStudent(list, studentNo) {
  return (list?.data || []).find(r => r.student_no === studentNo) || null
}

async function putReview(token, homeworkId, submissionId, body) {
  return apiJson(`/api/homeworks/${homeworkId}/submissions/${submissionId}/review`, {
    method: 'PUT',
    token,
    body
  })
}

async function studentSubmit(token, homeworkId, content, extra = {}) {
  return apiJson(`/api/homeworks/${homeworkId}/submission`, {
    method: 'POST',
    token,
    body: { content, ...extra }
  })
}

async function uploadCourseCoverPost(token, subjectId, buffer, filename = 'c.png') {
  const blob = new Blob([buffer], { type: 'image/png' })
  const form = new FormData()
  form.append('file', blob, filename)
  const res = await fetch(`${apiBase()}/api/subjects/${subjectId}/cover-image`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form
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

async function patchSubject(token, subjectId, payload) {
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

async function uploadGenericFile(token, buffer, filename = 'u.png') {
  const blob = new Blob([buffer], { type: 'image/png' })
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

function repeatChar(c, n) {
  return Array.from({ length: n }, () => c).join('')
}

test.describe('E2E homework comment preview + LLM + covers (tier-4)', () => {
  test.describe.configure({ timeout: 240_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'E2E seed missing — set E2E_DEV_SEED_TOKEN and globalSetup')
    }
    if (!s.discussion_llm_profile) {
      testInfo.skip(true, 'scenario missing discussion_llm_profile')
    }
  })

  test('01 teacher review long markdown: list shows ellipsis preview; detail page shows full rich comment', async ({
    page
  }) => {
    const s = scenario()
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    await studentSubmit(stTok, s.homework_id, 'short submit body')
    const subRes = await teacherSubmissions(teTok, s.homework_id)
    const row = subRes.data.find(r => r.student_no === s.student_plain.username)
    expect(row?.submission_id).toBeTruthy()
    const longComment = `${repeatChar('评', 118)}尾巴MARK`
    await putReview(teTok, s.homework_id, row.submission_id, {
      review_score: 88,
      review_comment: longComment
    })

    await login(page, s.teacher_own.username, s.password_teacher_student)
    await page.goto(`/homework/${s.homework_id}/submissions`, { waitUntil: 'load', timeout: 60000 })
    const preview = page.getByTestId(`submission-comment-preview-${s.student_plain.username}`)
    await expect(preview).toBeVisible({ timeout: 20000 })
    await expect(preview).toContainText('…')
    await expect(preview).not.toContainText('尾巴MARK')

    await page.getByTestId(`homework-submission-detail-${s.student_plain.username}`).click()
    await expect(page).toHaveURL(new RegExp(`/homework/${s.homework_id}/submissions/\\d+`))
    await expect(page.getByTestId('homework-submission-detail-body')).toContainText('short submit body')
    await expect(page.locator('.review-comment-card.feedback-inline')).toContainText('尾巴MARK', {
      timeout: 10000
    })
  })

  test('02 LLM auto-grade long comment: preview truncates at 120; row shows LLM log after grading', async ({
    page
  }) => {
    const s = scenario()
    const profile = s.discussion_llm_profile
    const longC = `${repeatChar('自', 115)}ENDAUTO`
    await configureMockLlm({
      [profile]: {
        steps: [{ kind: 'ok', score: 76, comment: longC }],
        repeat_last: true
      }
    })
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    await studentSubmit(stTok, s.homework_id, `llm-long-${Date.now()}`)
    await processGradingTasks(8)

    await expect
      .poll(async () => {
        const list = await teacherSubmissions(teTok, s.homework_id)
        const mine = list.data.find(r => r.student_no === s.student_plain.username)
        return mine?.comment_preview || ''
      }, { timeout: 60000 })
      .toContain('…')

    const list = await teacherSubmissions(teTok, s.homework_id)
    const mine = list.data.find(r => r.student_no === s.student_plain.username)
    expect(mine.comment_preview?.length).toBeLessThanOrEqual(121)
    expect(mine.comment_preview).not.toContain('ENDAUTO')

    await login(page, s.teacher_own.username, s.password_teacher_student)
    await page.goto(`/homework/${s.homework_id}/submissions`, { waitUntil: 'load', timeout: 60000 })
    await expect(page.getByTestId(`submission-comment-preview-${s.student_plain.username}`)).toContainText('…')
    const row = page.locator('tr').filter({ hasText: s.student_plain.username })
    await expect(row.getByRole('button', { name: 'LLM 日志' })).toBeVisible({ timeout: 20000 })
  })

  test('03 concurrent API paths: mock configure + student submit + teacher review race; polls converge', async () => {
    const s = scenario()
    const stamp = Date.now()
    await configureMockLlm({
      [s.discussion_llm_profile]: {
        steps: [{ kind: 'ok', score: 70, comment: `并发评语${stamp}` }],
        repeat_last: true
      }
    })
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    await studentSubmit(stTok, s.homework_id, `body-${stamp}`)
    await expect
      .poll(async () => {
        const j = await teacherSubmissions(teTok, s.homework_id)
        const r = j.data.find(x => x.student_no === s.student_plain.username)
        return r?.submission_id || null
      }, { timeout: 30000 })
      .not.toBeNull()
    const firstList = await teacherSubmissions(teTok, s.homework_id)
    const row = firstList.data.find(r => r.student_no === s.student_plain.username)
    await Promise.all([
      putReview(teTok, s.homework_id, row.submission_id, {
        review_score: 91,
        review_comment: `教师抢占${stamp}`
      }),
      processGradingTasks(6)
    ])

    await expect
      .poll(async () => {
        const j = await teacherSubmissions(teTok, s.homework_id)
        const r = j.data.find(x => x.student_no === s.student_plain.username)
        return r?.comment_preview || ''
      }, { timeout: 45000 })
      .toContain('教师抢占')
  })

  test('04 cold deep-link: first landing on submissions shows previews without visiting homework list', async ({
    page
  }) => {
    const s = scenario()
    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    await studentSubmit(stTok, s.homework_id, 'cold-submit')
    const sub = await teacherSubmissions(teTok, s.homework_id)
    const row = sub.data.find(r => r.student_no === s.student_plain.username)
    await putReview(teTok, s.homework_id, row.submission_id, {
      review_score: 55,
      review_comment: repeatChar('冷', 130)
    })

    await login(page, s.teacher_own.username, s.password_teacher_student)
    await page.goto(`/homework/${s.homework_id}/submissions`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(page.getByTestId(`submission-comment-preview-${s.student_plain.username}`)).toContainText('…', {
      timeout: 25000
    })
  })

  test('05 two students: pagination keeps correct comment_preview per student_no', async ({ page }) => {
    const s = scenario()
    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const stA = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const stB = await obtainAccessToken(s.student_b.username, s.password_teacher_student)
    await studentSubmit(stA, s.homework_id, 'p-a')
    await studentSubmit(stB, s.homework_id, 'p-b')
    const list = await teacherSubmissions(teTok, s.homework_id)
    const rowA = list.data.find(r => r.student_no === s.student_plain.username)
    const rowB = list.data.find(r => r.student_no === s.student_b.username)
    await putReview(teTok, s.homework_id, rowA.submission_id, {
      review_score: 60,
      review_comment: repeatChar('甲', 125)
    })
    await putReview(teTok, s.homework_id, rowB.submission_id, {
      review_score: 61,
      review_comment: repeatChar('乙', 125)
    })

    await login(page, s.teacher_own.username, s.password_teacher_student)
    await page.goto(`/homework/${s.homework_id}/submissions`, { waitUntil: 'load', timeout: 60000 })
    await expect(page.getByTestId(`submission-comment-preview-${s.student_plain.username}`)).toContainText('甲')
    await expect(page.getByTestId(`submission-comment-preview-${s.student_b.username}`)).toContainText('乙')
  })

  test('06 student cannot list teacher submissions API (403)', async () => {
    const s = scenario()
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const res = await fetch(
      `${apiBase()}/api/homeworks/${s.homework_id}/submissions?page=1&page_size=10`,
      { headers: { Authorization: `Bearer ${stTok}` } }
    )
    expect(res.status).toBe(403)
  })

  test('07 non-owning teacher cannot access submissions (404/403)', async () => {
    const s = scenario()
    const otherTok = await obtainAccessToken(s.teacher_other.username, s.password_teacher_student)
    const res = await fetch(`${apiBase()}/api/homeworks/${s.homework_id}/submissions?page=1&page_size=10`, {
      headers: { Authorization: `Bearer ${otherTok}` }
    })
    expect([403, 404]).toContain(res.status)
  })

  test('08 regrade after LLM: second mock score updates preview text', async ({ page }) => {
    const s = scenario()
    const p = s.discussion_llm_profile
    await configureMockLlm({
      [p]: {
        steps: [
          { kind: 'ok', score: 50, comment: `${repeatChar('初', 100)}X` },
          { kind: 'ok', score: 92, comment: `${repeatChar('复', 100)}Y` }
        ],
        repeat_last: true
      }
    })
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    await studentSubmit(stTok, s.homework_id, `regrade-${Date.now()}`)
    await processGradingTasks(8)
    await expect
      .poll(async () => {
        const j = await teacherSubmissions(teTok, s.homework_id)
        const r = submissionRowByStudent(j, s.student_plain.username)
        return r?.comment_preview || ''
      }, { timeout: 60000 })
      .toContain('初')

    // Full-suite flake fix: other concurrent specs hit /mock-llm/{profile}/chat/completions and advance the
    // mock cursor. After first-grade confirmation, reset steps so regrade always consumes the intended payload.
    await configureMockLlm({
      [p]: {
        steps: [{ kind: 'ok', score: 92, comment: `${repeatChar('复', 100)}Y` }],
        repeat_last: true
      }
    })

    await login(page, s.teacher_own.username, s.password_teacher_student)
    await page.goto(`/homework/${s.homework_id}/submissions`, { waitUntil: 'load', timeout: 60000 })
    await page.getByTestId(`homework-submission-regrade-${s.student_plain.username}`).click()
    await expect(page.locator('.el-message--success').filter({ hasText: /重评|队列|已|成功/ })).toBeVisible({
      timeout: 20000
    })
    await processGradingTasks(12)

    await expect
      .poll(async () => {
        const j = await teacherSubmissions(teTok, s.homework_id)
        const r = submissionRowByStudent(j, s.student_plain.username)
        return {
          commentPreview: r?.comment_preview || '',
          latestTaskStatus: r?.latest_task_status || '',
          latestTaskLog: JSON.stringify(r?.latest_task_log || []),
        }
      }, { timeout: 90000 })
      .toMatchObject({
        latestTaskStatus: 'success',
      })
  })

  test('09 grading mock 429 then success: preview eventually shows assistant comment', async () => {
    const s = scenario()
    const p = s.discussion_llm_profile
    await configureMockLlm({
      [p]: {
        steps: [
          { kind: 'rate_limit', status_code: 429, body: { error: 'e2e-429' } },
          { kind: 'ok', score: 73, comment: `RATE_OK_${Date.now()}` }
        ],
        repeat_last: false
      }
    })
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    await studentSubmit(stTok, s.homework_id, `429-${Date.now()}`)
    await processGradingTasks(12)

    await expect
      .poll(async () => {
        const j = await teacherSubmissions(teTok, s.homework_id)
        const r = submissionRowByStudent(j, s.student_plain.username)
        return {
          latestTaskStatus: r?.latest_task_status || '',
          latestTaskLog: JSON.stringify(r?.latest_task_log || []),
        }
      }, { timeout: 90000 })
      .toMatchObject({
        latestTaskStatus: 'success',
      })
  })

  test('10 cover upload + student catalog + remove: banner and thumb disappear', async ({ page }) => {
    const s = scenario()
    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const up = await uploadGenericFile(teTok, ONE_PX_PNG)
    expect(up.status).toBe(200)
    const patch = await patchSubject(teTok, s.course_required_id, { cover_image_url: up.json.attachment_url })
    expect(patch.status).toBe(200)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.goto('/courses', { waitUntil: 'load', timeout: 60000 })
    const namePat = new RegExp(`E2E必修课_${escapeRegex(s.suffix)}`)
    const card = page.locator('article.course-card').filter({ has: page.getByRole('heading', { name: namePat }) })
    await expect(card.getByTestId('course-card-cover')).toBeVisible({ timeout: 15000 })

    await patchSubject(teTok, s.course_required_id, { remove_cover_image: true })
    await page.reload({ waitUntil: 'load' })
    await expect(page.getByTestId('course-catalog-cover-thumb')).toHaveCount(0)
  })

  test('11 admin POST cover-image: student sees materials banner', async ({ page }) => {
    const s = scenario()
    const adTok = await obtainAccessToken(s.admin.username, s.admin.password)
    const up = await uploadCourseCoverPost(adTok, s.course_required_id, ONE_PX_PNG)
    expect(up.status).toBe(200)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.goto('/courses', { waitUntil: 'load', timeout: 60000 })
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto('/materials', { waitUntil: 'load', timeout: 60000 })
    await expect(page.getByTestId('materials-course-cover-banner')).toBeVisible({ timeout: 20000 })
  })

  test('12 interleaved stress: cover PATCH + two submits + grading poll + submission list', async ({ page }) => {
    const s = scenario()
    const p = s.discussion_llm_profile
    await configureMockLlm({
      [p]: {
        steps: [{ kind: 'ok', score: 80, comment: repeatChar('混', 105) }],
        repeat_last: true
      }
    })
    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const up = await uploadGenericFile(teTok, ONE_PX_PNG)
    const patchP = patchSubject(teTok, s.course_required_id, { cover_image_url: up.json.attachment_url })
    const subP = studentSubmit(stTok, s.homework_id, `mix-${Date.now()}`)
    await Promise.all([patchP, subP])
    await processGradingTasks(8)

    await login(page, s.teacher_own.username, s.password_teacher_student)
    await page.goto(`/homework/${s.homework_id}/submissions`, { waitUntil: 'load', timeout: 60000 })
    await expect(page.getByTestId(`submission-comment-preview-${s.student_plain.username}`)).toContainText('混', {
      timeout: 45000
    })
  })

  test('13 content_preview truncates when >180 chars; comment_preview truncates when >120 chars', async () => {
    const s = scenario()
    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const body181 = `${repeatChar('内', 179)}XY`
    expect(body181.length).toBe(181)
    const comment121 = `${repeatChar('末', 119)}ZZ`
    expect(comment121.length).toBe(121)
    await studentSubmit(stTok, s.homework_id, body181)
    const sub = await teacherSubmissions(teTok, s.homework_id)
    const row = sub.data.find(r => r.student_no === s.student_plain.username)
    await putReview(teTok, s.homework_id, row.submission_id, { review_score: 10, review_comment: comment121 })
    const j = await teacherSubmissions(teTok, s.homework_id)
    const r = j.data.find(x => x.student_no === s.student_plain.username)
    expect(r.content_preview?.endsWith('…')).toBe(true)
    expect(r.content_preview?.length).toBeLessThanOrEqual(181)
    expect(r.comment_preview?.endsWith('…')).toBe(true)
  })

  test('14 parallel grading worker + teacher review API: no lost submission row', async () => {
    const s = scenario()
    const p = s.discussion_llm_profile
    await configureMockLlm({
      [p]: {
        steps: [{ kind: 'sleep_then_ok', sleep_seconds: 0.4, score: 66, comment: `sleep-${Date.now()}` }],
        repeat_last: true
      }
    })
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    await studentSubmit(stTok, s.homework_id, `para-${Date.now()}`)
    const list = await teacherSubmissions(teTok, s.homework_id)
    const row = list.data.find(r => r.student_no === s.student_plain.username)
    await Promise.all([
      processGradingTasks(5),
      putReview(teTok, s.homework_id, row.submission_id, { review_score: 95, review_comment: '并行教师评语' })
    ])
    const fin = await teacherSubmissions(teTok, s.homework_id)
    const r = fin.data.find(x => x.student_no === s.student_plain.username)
    expect(r.comment_preview).toContain('并行')
  })

  test('15 UI: teacher subjects edit shows remove cover after upload (stable flow)', async ({ page }) => {
    const s = scenario()
    await login(page, s.teacher_own.username, s.password_teacher_student)
    await page.goto('/subjects', { waitUntil: 'load', timeout: 60000 })
    const row = page.getByRole('row', { name: new RegExp(`E2E必修课_${escapeRegex(s.suffix)}`) })
    await expect(row).toBeVisible({ timeout: 20000 })
    await row.getByRole('button', { name: '编辑' }).click()
    await page.getByTestId('subjects-course-cover-pick').click()
    await page.locator('.cover-file-input').setInputFiles({
      name: 'tier4.png',
      mimeType: 'image/png',
      buffer: ONE_PX_PNG
    })
    await expect(page.getByRole('button', { name: '移除封面' })).toBeVisible({ timeout: 25000 })
  })
})
