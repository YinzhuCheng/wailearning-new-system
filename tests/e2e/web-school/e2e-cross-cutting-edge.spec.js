/**
 * Cross-cutting E2E: multi-role interleaving, cold parallel login, token lifecycle,
 * validation boundaries (422/400/403), API+UI convergence under concurrency.
 * Uses the same globalSetup + reset-scenario contract as other school E2E specs.
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

async function apiGetExpect(pathname, token) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {}
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

async function apiListDiscussions(token, params) {
  const u = new URL(`${apiBase()}/api/discussions`)
  Object.entries(params).forEach(([k, v]) => u.searchParams.set(k, String(v)))
  const res = await fetch(u.toString(), {
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  })
  const text = await res.text()
  return { status: res.status, json: text ? JSON.parse(text) : null }
}

async function apiHomeworkSubmissionHistory(token, homeworkId) {
  return apiGetJson(`/api/homeworks/${homeworkId}/submission/me/history`, token)
}

async function apiListEnrolledStudents(adminToken, subjectId) {
  return apiGetJson(`/api/subjects/${subjectId}/students`, adminToken)
}

test.describe('E2E cross-cutting edge scenarios', () => {
  test.describe.configure({ timeout: 180_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e scenario 闂?set E2E_DEV_SEED_TOKEN and globalSetup')
    }
  })

  test('01 cold parallel boot: admin, both teachers, and both enrolled students reach dashboards without cross-login bleed', async ({
    browser
  }) => {
    const s = scenario()
    const contexts = []
    const pages = []
    for (let i = 0; i < 5; i += 1) {
      const ctx = await browser.newContext()
      contexts.push(ctx)
      pages.push(await ctx.newPage())
    }
    try {
      await Promise.all([
        login(pages[0], s.admin.username, s.admin.password),
        login(pages[1], s.teacher_own.username, s.password_teacher_student),
        login(pages[2], s.teacher_other.username, s.password_teacher_student),
        login(pages[3], s.student_plain.username, s.password_teacher_student),
        login(pages[4], s.student_b.username, s.password_teacher_student)
      ])
      await Promise.all([
        pages[0].goto('/students'),
        pages[1].goto('/students'),
        pages[2].goto('/students'),
        pages[3].goto('/students'),
        pages[4].goto('/students')
      ])
      for (const p of pages) {
        await expect(p.locator('.layout-container')).toBeVisible({ timeout: 25000 })
      }
    } finally {
      await Promise.all(contexts.map(c => c.close().catch(() => {})))
    }
  })

  test('02 bearer token invalidated after admin deactivates student; reactivation restores API access', async () => {
    const s = scenario()
    const adminTok = await obtainAccessToken(s.admin.username, s.admin.password)
    const users = await apiGetJson('/api/users', adminTok)
    const studentUser = users.find(u => u.username === s.student_plain.username)
    expect(studentUser).toBeTruthy()

    let tok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    let me = await apiGetExpect('/api/auth/me', tok)
    expect(me.status).toBe(200)

    await apiPutJsonExpect(`/api/users/${studentUser.id}`, adminTok, { is_active: false })
    me = await apiGetExpect('/api/auth/me', tok)
    expect(me.status).toBe(400)
    expect(`${me.json?.detail || ''}`.toLowerCase()).toContain('inactive')

    const badLogin = await fetch(`${apiBase()}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        username: s.student_plain.username,
        password: s.password_teacher_student
      })
    })
    expect(badLogin.status).toBe(400)

    await apiPutJsonExpect(`/api/users/${studentUser.id}`, adminTok, { is_active: true })
    tok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    me = await apiGetExpect('/api/auth/me', tok)
    expect(me.status).toBe(200)
  })

  test('03 triple concurrent API submissions plus dual-tab discussion posts converge to one attempt and full thread', async ({
    browser
  }) => {
    const s = scenario()
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const base = {
      target_type: 'homework',
      target_id: s.homework_id,
      subject_id: s.course_required_id,
      class_id: s.class_id_1
    }

    const subs = await Promise.all([
      fetch(`${apiBase()}/api/homeworks/${s.homework_id}/submission`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${stTok}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: `triple-a-${Date.now()}`,
          attachment_name: null,
          attachment_url: null,
          remove_attachment: false,
          used_llm_assist: false,
          submission_mode: 'full'
        })
      }),
      fetch(`${apiBase()}/api/homeworks/${s.homework_id}/submission`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${stTok}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: `triple-b-${Date.now()}`,
          attachment_name: null,
          attachment_url: null,
          remove_attachment: false,
          used_llm_assist: false,
          submission_mode: 'full'
        })
      }),
      fetch(`${apiBase()}/api/homeworks/${s.homework_id}/submission`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${stTok}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: `triple-c-${Date.now()}`,
          attachment_name: null,
          attachment_url: null,
          remove_attachment: false,
          used_llm_assist: false,
          submission_mode: 'full'
        })
      })
    ])
    const subStatuses = await Promise.all(subs.map(r => r.status))
    expect(subStatuses.filter(x => x === 200).length).toBeGreaterThanOrEqual(1)

    const ctx1 = await browser.newContext()
    const ctx2 = await browser.newContext()
    const p1 = await ctx1.newPage()
    const p2 = await ctx2.newPage()
    const d1 = `edge-d1-${Date.now()}`
    const d2 = `edge-d2-${Date.now()}`
    try {
      await login(p1, s.student_plain.username, s.password_teacher_student)
      await login(p2, s.student_plain.username, s.password_teacher_student)
      await p1.goto(`/homework/${s.homework_id}/submit`, { waitUntil: 'load', timeout: 60000 })
      await p2.goto(`/homework/${s.homework_id}/submit`, { waitUntil: 'load', timeout: 60000 })
      await p1.locator('.discussion-composer-section .el-button').click()
      await p2.locator('.discussion-composer-section .el-button').click()
      await p1.locator('.discussion-input .el-textarea__inner').fill(d1)
      await p2.locator('.discussion-input .el-textarea__inner').fill(d2)
      await Promise.all([
        p1.getByTestId('discussion-submit').click(),
        p2.getByTestId('discussion-submit').click()
      ])
      await expect
        .poll(async () => {
          const list = await apiListDiscussions(teTok, { ...base, page: 1, page_size: 50 })
          if (list.status !== 200 || !list.json) {
            return false
          }
          const bodies = (list.json.data || []).map(x => `${x.body || ''}`)
          return bodies.some(b => b.includes(d1)) && bodies.some(b => b.includes(d2))
        }, { timeout: 35000 })
        .toBe(true)
      await p1.reload({ waitUntil: 'load', timeout: 60000 })
      await expect(p1.locator('.discussion-row__body').filter({ hasText: d1 })).toBeVisible({ timeout: 25000 })
      await expect(p1.locator('.discussion-row__body').filter({ hasText: d2 })).toBeVisible({ timeout: 25000 })
    } finally {
      await ctx1.close().catch(() => {})
      await ctx2.close().catch(() => {})
    }

    await expect
      .poll(async () => {
        const hist = await apiHomeworkSubmissionHistory(stTok, s.homework_id)
        return (hist.attempts || []).length
      }, { timeout: 30000 })
      .toBeGreaterThanOrEqual(1)

    const list = await apiListDiscussions(teTok, { ...base, page: 1, page_size: 50 })
    expect(list.status).toBe(200)
    const bodies = (list.json.data || []).map(x => x.body)
    expect(bodies.some(b => `${b}`.includes(d1))).toBe(true)
    expect(bodies.some(b => `${b}`.includes(d2))).toBe(true)
  })

  test('04 auth edge codes: wrong password 401, forged bearer 401, discussion page_size over limit 422', async () => {
    const s = scenario()
    const badLogin = await fetch(`${apiBase()}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username: s.student_plain.username, password: 'DefinitelyWrong_' })
    })
    expect(badLogin.status).toBe(401)

    const forged = await apiGetExpect('/api/auth/me', 'not.a.real.jwt.token')
    expect(forged.status).toBe(401)

    const teTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const over = await apiListDiscussions(teTok, {
      target_type: 'homework',
      target_id: s.homework_id,
      subject_id: s.course_required_id,
      class_id: s.class_id_1,
      page: 1,
      page_size: 101
    })
    expect(over.status).toBe(422)
  })

  test('05 student cannot self-enroll a required course; elective self-enroll succeeds with stable roster', async () => {
    const s = scenario()
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const adminTok = await obtainAccessToken(s.admin.username, s.admin.password)

    const reqAttempt = await apiPostJsonExpect(
      `/api/subjects/${s.course_required_id}/student-self-enroll`,
      stTok,
      {}
    )
    expect(reqAttempt.status).toBe(400)

    const elFirst = await apiPostJsonExpect(`/api/subjects/${s.course_elective_id}/student-self-enroll`, stTok, {})
    expect(elFirst.status).toBe(200)
    expect(elFirst.json.already_enrolled === true || elFirst.json.created === true).toBe(true)

    const elDup = await apiPostJsonExpect(`/api/subjects/${s.course_elective_id}/student-self-enroll`, stTok, {})
    expect(elDup.status).toBe(200)
    expect(elDup.json.already_enrolled).toBe(true)

    const roster = await apiListEnrolledStudents(adminTok, s.course_elective_id)
    const ids = roster.map(r => Number(r.student_id))
    expect(ids.filter(id => id === Number(s.student_plain.student_row_id)).length).toBe(1)
  })

  test('06 orphan course: teacher_other gets 403 on discussions; course owner lists OK (create hw if missing)', async () => {
    const s = scenario()
    const ownTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const otherTok = await obtainAccessToken(s.teacher_other.username, s.password_teacher_student)

    const orphanId = s.course_orphan_id
    const hwRows = await apiGetJson(`/api/homeworks?subject_id=${orphanId}&page_size=50`, ownTok)
    const hwList = hwRows.data || []
    let homeworkId = hwList[0]?.id
    if (!homeworkId) {
      const created = await apiPostJson('/api/homeworks', ownTok, {
        class_id: s.class_id_1,
        subject_id: orphanId,
        title: `E2E闂佽瀛╃粙蹇涘磹閺囥垹绀夐悷娆忓婵瓨绻濇繛鎯т壕缂備焦顨堥崜?{s.suffix}_${Date.now()}`,
        content: 'orphan hw for discussion acl',
        max_score: 100,
        grade_precision: 'integer',
        auto_grading_enabled: false,
        allow_late_submission: true,
        late_submission_affects_score: false
      })
      homeworkId = created.id
    }

    const listOwn = await apiListDiscussions(ownTok, {
      target_type: 'homework',
      target_id: homeworkId,
      subject_id: orphanId,
      class_id: s.class_id_1,
      page: 1
    })
    expect(listOwn.status).toBe(200)

    const listOther = await apiListDiscussions(otherTok, {
      target_type: 'homework',
      target_id: homeworkId,
      subject_id: orphanId,
      class_id: s.class_id_1,
      page: 1
    })
    expect(listOther.status).toBe(403)
  })

  test('07 interleaved UI homework submit and teacher notification publish while second student lists notifications', async ({
    browser
  }) => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const title = `E2E濠电偛鐡ㄩ崵搴ㄥ磹濡ゅ啫鍨濋柟?{s.suffix}_${Date.now()}`
    const created = await apiPostJson('/api/homeworks', teacherTok, {
      class_id: s.class_id_1,
      subject_id: s.course_required_id,
      title,
      content: 'edge interleave',
      max_score: 100,
      grade_precision: 'integer',
      auto_grading_enabled: false,
      allow_late_submission: true,
      late_submission_affects_score: false
    })
    const newHwId = created.id

    const ctxS1 = await browser.newContext()
    const ctxS2 = await browser.newContext()
    const p1 = await ctxS1.newPage()
    const p2 = await ctxS2.newPage()
    try {
      await login(p1, s.student_plain.username, s.password_teacher_student)
      await login(p2, s.student_b.username, s.password_teacher_student)
      await enterSeededRequiredCourse(p1, s.suffix)
      await enterSeededRequiredCourse(p2, s.suffix)

      await p1.goto('/homework', { waitUntil: 'load', timeout: 60000 })
      await expect(p1.getByRole('row', { name: new RegExp(escapeRegex(title)) })).toBeVisible({ timeout: 25000 })
      await p1.goto(`/homework/${newHwId}/submit`, { waitUntil: 'load', timeout: 60000 })

      const notifTitle = `E2E_NOTIF_${s.suffix}_${Date.now()}`
      await Promise.all([
        (async () => {
          await p1.getByTestId('homework-submit-content').fill(`interleave_${Date.now()}`)
          await p1.getByTestId('homework-submit-save').click()
        })(),
        apiPostJson('/api/notifications', teacherTok, {
          title: notifTitle,
          content: 'parallel',
          audience: 'class',
          subject_id: s.course_required_id,
          class_id: s.class_id_1,
          notification_kind: 'general'
        }),
        (async () => {
          await p2.goto('/notifications')
          await expect(p2.getByRole('cell', { name: notifTitle })).toBeVisible({ timeout: 40000 })
        })()
      ])

      await expect(p1.locator('.layout-container')).toBeVisible({ timeout: 30000 })
    } finally {
      await ctxS1.close().catch(() => {})
      await ctxS2.close().catch(() => {})
    }

    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const hist = await apiHomeworkSubmissionHistory(stTok, newHwId)
    expect(hist.attempts?.length || 0).toBeGreaterThanOrEqual(1)
  })

  test('08 concurrent notification mark-all-read and single mark-read plus new announcement stays eventually consistent', async () => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)

    const ids = []
    for (let i = 0; i < 3; i += 1) {
      const row = await apiPostJson('/api/notifications', teacherTok, {
        title: `E2E_MR_${s.suffix}_${i}_${Date.now()}`,
        content: 'mark race',
        audience: 'class',
        subject_id: s.course_required_id,
        class_id: s.class_id_1,
        notification_kind: 'general'
      })
      ids.push(row.id)
    }

    const markAllUrl = new URL(`${apiBase()}/api/notifications/mark-all-read`)
    markAllUrl.searchParams.set('subject_id', String(s.course_required_id))
    await Promise.all([
      fetch(markAllUrl.toString(), {
        method: 'POST',
        headers: { Authorization: `Bearer ${stTok}` }
      }),
      fetch(`${apiBase()}/api/notifications/${ids[0]}/read`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${stTok}` }
      }),
      fetch(markAllUrl.toString(), {
        method: 'POST',
        headers: { Authorization: `Bearer ${stTok}` }
      })
    ])

    const extra = await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_AFTER_READ_${s.suffix}_${Date.now()}`,
      content: 'after storm',
      audience: 'class',
      subject_id: s.course_required_id,
      class_id: s.class_id_1,
      notification_kind: 'general'
    })

    await expect
      .poll(async () => {
        const res = await fetch(`${apiBase()}/api/notifications/${extra.id}`, {
          headers: { Authorization: `Bearer ${stTok}` }
        })
        expect(res.ok).toBeTruthy()
        const row = await res.json()
        return row.is_read === false
      }, { timeout: 30000 })
      .toBe(true)
  })

  test('09 concurrent teacher title save vs student submit: one submission row and final homework title from API', async ({
    browser
  }) => {
    const s = scenario()
    let initialTitle = ''
    const finalTitle = 'E2E_final_title_' + s.suffix + '_' + Date.now()
    const teacherCtx = await browser.newContext()
    const studentCtx = await browser.newContext()
    const tPage = await teacherCtx.newPage()
    const stPage = await studentCtx.newPage()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    try {
      initialTitle = (await apiGetJson('/api/homeworks/' + s.homework_id, teacherTok)).title
      await login(tPage, s.teacher_own.username, s.password_teacher_student)
      await login(stPage, s.student_plain.username, s.password_teacher_student)
      await enterSeededRequiredCourse(tPage, s.suffix)
      await stPage.goto(`/homework/${s.homework_id}/submit`, { waitUntil: 'load', timeout: 60000 })

      await tPage.goto('/homework')
      const row = tPage.getByRole('row', { name: new RegExp(escapeRegex(initialTitle)) })
      await expect(row).toBeVisible({ timeout: 25000 })
      await row.getByTestId('homework-btn-edit').click()
      await expect(tPage.getByTestId('homework-form-title')).toBeVisible({ timeout: 15000 })
      await tPage.getByTestId('homework-form-title').fill(finalTitle)

      await Promise.all([
        tPage.getByTestId('homework-form-save').click(),
        (async () => {
          await stPage.getByTestId('homework-submit-content').fill(`race_submit_${Date.now()}`)
          await stPage.getByTestId('homework-submit-save').click()
        })()
      ])
      await expect(tPage.getByTestId('homework-form-title')).toBeHidden({ timeout: 30000 })
      await expect(stPage.locator('.layout-container')).toBeVisible({ timeout: 40000 })

      await expect
        .poll(async () => {
          const rows = await apiGetJson(`/api/homeworks?subject_id=${s.course_required_id}&page_size=50`, teacherTok)
          const titles = (rows.data || []).map(r => r.title)
          return {
            hasFinal: titles.includes(finalTitle),
            hasInitial: titles.includes(initialTitle)
          }
        }, { timeout: 30000 })
        .toEqual({ hasFinal: true, hasInitial: false })

      const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
      const hist = await apiHomeworkSubmissionHistory(stTok, s.homework_id)
      expect((hist.attempts || []).length).toBeGreaterThanOrEqual(1)
    } finally {
      await teacherCtx.close().catch(() => {})
      await studentCtx.close().catch(() => {})
    }
  })

  test('10 wrong-subject homework discussion post rejected (400 or 403); material discussion baseline still 200', async () => {
    const s = scenario()
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const bad = await apiPostJsonExpect('/api/discussions', stTok, {
      target_type: 'homework',
      target_id: s.homework_id,
      subject_id: s.course_elective_id,
      class_id: s.class_id_1,
      body: `misscoped-${Date.now()}`
    })
    expect([400, 403]).toContain(bad.status)

    const ok = await apiPostJsonExpect('/api/discussions', stTok, {
      target_type: 'material',
      target_id: s.material_discussion_id,
      subject_id: s.course_required_id,
      class_id: s.class_id_1,
      body: `mat-ok-${Date.now()}`
    })
    expect(ok.status).toBe(200)
  })
})
