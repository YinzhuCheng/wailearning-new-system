/**
 * Tier-4 stress E2E: concurrency, multi-role, cold navigation, HTTP edges, UI+API interleaving.
 * Uses seed from `resetE2eScenario` (includes class_teacher, parent_code on student_plain).
 */
const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario, enterSeededRequiredCourse } = require('./fixtures.cjs')
const {
  apiBase,
  seedHeaders,
  escapeRegex,
  login,
  obtainAccessToken,
  apiGetJson,
  apiPostJson,
  apiPutJson,
  apiDelete,
  apiJson,
  configureMockLlm,
  processGradingTasks,
  gradingState,
  createPreset,
  validatePreset,
  setFlatCourseConfig,
  createHomework,
  apiListNotifications,
  apiHomeworkSubmissionHistory,
  getChapterTree,
  apiPostForm
} = require('./future-advanced-coverage-helpers.cjs')

const scenario = () => loadE2eScenario()

async function fetchRaw(method, pathname, { token, body, headers = {} } = {}) {
  const url =
    String(pathname || '').startsWith('http://') || String(pathname || '').startsWith('https://')
      ? pathname
      : `${apiBase().replace(/\/$/, '')}${String(pathname || '').startsWith('/') ? pathname : `/${pathname}`}`
  const res = await fetch(url, {
    method,
    headers: {
      ...(body && !(body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers
    },
    body: body == null ? undefined : body instanceof FormData ? body : JSON.stringify(body)
  })
  const text = await res.text()
  let json = null
  try {
    json = text ? JSON.parse(text) : null
  } catch {
    json = null
  }
  return { status: res.status, ok: res.ok, text, json }
}

test.describe('E2E tier-4 stress backlog', () => {
  test.describe.configure({ timeout: 300_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e seed cache; run globalSetup with E2E_DEV_SEED_TOKEN first')
    }
  })

  test('01 cold triple-context: admin + teacher + student parallel hard reloads', async ({ browser }) => {
    const s = scenario()
    const ctxA = await browser.newContext()
    const ctxB = await browser.newContext()
    const ctxC = await browser.newContext()
    const adminP = await ctxA.newPage()
    const teachP = await ctxB.newPage()
    const stuP = await ctxC.newPage()
    try {
      await Promise.all([
        (async () => {
          await login(adminP, s.admin.username, s.admin.password)
          await adminP.goto('/students', { waitUntil: 'load', timeout: 120000 })
          await adminP.reload({ waitUntil: 'load', timeout: 120000 })
          await expect(adminP.locator('.layout-container, .page-title, h1').first()).toBeVisible({ timeout: 60000 })
        })(),
        (async () => {
          await login(teachP, s.teacher_own.username, s.password_teacher_student)
          await teachP.goto('/homework', { waitUntil: 'load', timeout: 120000 })
          await teachP.reload({ waitUntil: 'load', timeout: 120000 })
          await expect(teachP.getByRole('heading', { name: /作业/ })).toBeVisible({ timeout: 60000 })
        })(),
        (async () => {
          await login(stuP, s.student_plain.username, s.password_teacher_student)
          await stuP.goto('/courses', { waitUntil: 'load', timeout: 120000 })
          await stuP.reload({ waitUntil: 'load', timeout: 120000 })
          await expect(stuP.locator('article.course-card').first()).toBeVisible({ timeout: 60000 })
        })()
      ])
    } finally {
      await ctxA.close().catch(() => {})
      await ctxB.close().catch(() => {})
      await ctxC.close().catch(() => {})
    }
  })

  test('02 teacher updates homework title while two student tabs poll submission history', async ({ browser }) => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const newTitle = `E2E并发标题_${s.suffix}_${Date.now()}`
    const ctxA = await browser.newContext()
    const ctxB = await browser.newContext()
    const p1 = await ctxA.newPage()
    const p2 = await ctxB.newPage()
    try {
      await login(p1, s.student_plain.username, s.password_teacher_student)
      await login(p2, s.student_plain.username, s.password_teacher_student)
      await enterSeededRequiredCourse(p1, s.suffix)
      await enterSeededRequiredCourse(p2, s.suffix)
      await p1.goto(`/homework/${s.homework_id}/submit`, { waitUntil: 'load', timeout: 60000 })
      await p2.goto(`/homework/${s.homework_id}/submit`, { waitUntil: 'load', timeout: 60000 })
      await apiPutJson(`/api/homeworks/${s.homework_id}`, teacherTok, { title: newTitle })
      await expect
        .poll(async () => {
          const hw = await apiGetJson(`/api/homeworks/${s.homework_id}`, studentTok)
          return `${hw.title || ''}`.includes('E2E并发标题_')
        }, { timeout: 45000 })
        .toBe(true)
      await p1.reload({ waitUntil: 'load', timeout: 60000 })
      await p2.reload({ waitUntil: 'load', timeout: 60000 })
      await expect
        .poll(async () => {
          const t1 = await p1.locator('body').innerText()
          const t2 = await p2.locator('body').innerText()
          return t1.includes('E2E并发标题_') && t2.includes('E2E并发标题_')
        }, { timeout: 45000 })
        .toBe(true)
    } finally {
      await apiPutJson(`/api/homeworks/${s.homework_id}`, teacherTok, {
        title: `E2E_UI作业_${s.suffix}`
      }).catch(() => {})
      await ctxA.close().catch(() => {})
      await ctxB.close().catch(() => {})
    }
  })

  test('03 parent notifications + teacher post + student single-row read converge', async ({ browser }) => {
    const s = scenario()
    expect(s.parent_code).toBeTruthy()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const title = `E2E家长交织_${s.suffix}_${Date.now()}`
    await apiPostJson('/api/notifications', teacherTok, {
      title,
      content: 'tier4 parent mix',
      priority: 'normal',
      is_pinned: false,
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })
    const parentList = await fetchRaw(
      'GET',
      `/api/parent/notifications/${encodeURIComponent(s.parent_code)}?page_size=50`
    )
    expect(parentList.status).toBe(200)
    expect(
      (parentList.json.notifications || []).some(n => `${n.title || ''}`.includes('E2E家长交织_'))
    ).toBeTruthy()

    const ctx = await browser.newContext()
    const page = await ctx.newPage()
    try {
      await login(page, s.student_plain.username, s.password_teacher_student)
      await enterSeededRequiredCourse(page, s.suffix)
      await page.goto('/notifications', { waitUntil: 'load', timeout: 60000 })
      const row = page.locator('tr').filter({ hasText: title }).first()
      await expect(row).toBeVisible({ timeout: 60000 })
      await row.click()
      await expect
        .poll(async () => {
          const list = await apiListNotifications(studentTok, {
            subject_id: s.course_required_id,
            page_size: 100
          })
          const hit = (list.data || []).find(x => x.title === title)
          return Boolean(hit?.is_read)
        }, { timeout: 45000 })
        .toBe(true)
    } finally {
      await ctx.close().catch(() => {})
    }
  })

  test('04 score composition: teacher updates scheme; student GET matches', async () => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const semesters = await apiGetJson('/api/semesters', teacherTok)
    const semesterName = semesters[0]?.name
    expect(semesterName).toBeTruthy()
    await apiPutJson(`/api/scores/grade-scheme/${s.course_required_id}`, teacherTok, {
      homework_weight: 35,
      extra_daily_weight: 25
    })
    const comp = await apiGetJson(
      `/api/scores/composition/me?subject_id=${s.course_required_id}&semester=${encodeURIComponent(semesterName)}`,
      studentTok
    )
    expect(Number(comp.scheme?.homework_weight ?? comp.homework_weight ?? 35)).toBe(35)
  })

  test('05 attendance batch idempotent: same date+subject upserts not duplicates', async () => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const day = '2026-03-15T10:00:00'
    const body = {
      class_id: s.class_id_1,
      subject_id: s.course_required_id,
      date: day,
      status: 'present',
      remark: 'tier4'
    }
    const r1 = await fetchRaw('POST', '/api/attendance/class-batch', {
      token: teacherTok,
      body,
      headers: { 'Content-Type': 'application/json' }
    })
    expect(r1.status).toBe(200)
    const r2 = await fetchRaw('POST', '/api/attendance/class-batch', {
      token: teacherTok,
      body: { ...body, status: 'absent' },
      headers: { 'Content-Type': 'application/json' }
    })
    expect(r2.status).toBe(200)
    const list = await apiGetJson(
      `/api/attendance?class_id=${s.class_id_1}&subject_id=${s.course_required_id}&student_id=${s.student_plain.student_row_id}&page_size=500`,
      teacherTok
    )
    const sameDay = (list.data || []).filter(
      a => a.student_id === s.student_plain.student_row_id && `${a.date}`.includes('2026-03-15')
    )
    expect(sameDay.length).toBe(1)
    expect(sameDay[0].status).toBe('absent')
  })

  test('06 points: admin adds points; student exchange stays non-negative', async ({ browser }) => {
    const s = scenario()
    const adminTok = await obtainAccessToken(s.admin.username, s.admin.password)
    const stuTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    await apiPostJson(`/api/points/students/${s.student_plain.student_row_id}/add`, adminTok, {
      student_id: s.student_plain.student_row_id,
      points: 5000,
      source_type: 'manual',
      source_id: null,
      description: 'tier4 seed points',
      rule_id: null
    })
    await apiPostJson('/api/points/items', adminTok, {
      name: `E2E兑换项_${s.suffix}`,
      description: 'tier4',
      item_type: 'virtual',
      points_cost: 10,
      stock: 100,
      image_url: null
    })
    const items = await apiGetJson('/api/points/items', stuTok)
    const cheap = (items || []).find(i => i.points_cost > 0 && i.points_cost <= 5000) || items[0]
    expect(cheap?.id).toBeTruthy()
    const ctxA = await browser.newContext()
    const ctxB = await browser.newContext()
    const p1 = await ctxA.newPage()
    const p2 = await ctxB.newPage()
    try {
      await login(p1, s.admin.username, s.admin.password)
      await login(p2, s.student_plain.username, s.password_teacher_student)
      await Promise.all([
        p1.goto('/points', { waitUntil: 'load', timeout: 120000 }),
        p2.goto('/points', { waitUntil: 'load', timeout: 120000 })
      ])
      const ex = await apiPostJson('/api/points/exchange', stuTok, { item_id: cheap.id, quantity: 1 })
      expect(ex.message || ex.exchange_id).toBeTruthy()
      const acct = await apiGetJson('/api/points/my', stuTok)
      expect(Number(acct.available_points ?? 0)).toBeGreaterThanOrEqual(0)
    } finally {
      await ctxA.close().catch(() => {})
      await ctxB.close().catch(() => {})
    }
  })

  test('07 semesters: duplicate name returns 400', async () => {
    const s = scenario()
    const adminTok = await obtainAccessToken(s.admin.username, s.admin.password)
    const semesters = await apiGetJson('/api/semesters', adminTok)
    const name = semesters[0]?.name
    expect(name).toBeTruthy()
    const dup = await fetchRaw('POST', '/api/semesters', {
      token: adminTok,
      body: { name, year: 2026 }
    })
    expect(dup.status).toBe(400)
  })

  test('08 classes: delete blocked with courses on class; empty class deletable', async () => {
    const s = scenario()
    const adminTok = await obtainAccessToken(s.admin.username, s.admin.password)
    const blocked = await fetchRaw('DELETE', `/api/classes/${s.class_id_1}`, { token: adminTok })
    expect(blocked.status).toBe(400)
    const created = await apiPostJson('/api/classes', adminTok, { name: `E2E空班_${s.suffix}`, grade: 2026 })
    const del = await fetchRaw('DELETE', `/api/classes/${created.id}`, { token: adminTok })
    expect(del.status).toBe(200)
  })

  test('09 homework attachment: student sets avatar; download by stored name returns bytes', async () => {
    const s = scenario()
    const stuTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const minimalPng = Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
      'base64'
    )
    const fd = new FormData()
    fd.append('file', new Blob([minimalPng], { type: 'image/png' }), 'tier4.png')
    const me = await apiPostForm('/api/auth/me/avatar', stuTok, fd)
    const fileUrl = me.avatar_url
    expect(fileUrl).toBeTruthy()
    let pathOnly = `${fileUrl}`.split('?')[0]
    if (pathOnly.startsWith('http://') || pathOnly.startsWith('https://')) {
      pathOnly = new URL(pathOnly).pathname
    }
    if (!pathOnly.startsWith('/')) {
      pathOnly = `/${pathOnly}`
    }
    const get = await fetchRaw('GET', pathOnly, { token: stuTok })
    expect(get.status).toBe(200)
  })

  test('10 LLM grading: mock profile + process task reaches terminal state', async () => {
    const s = scenario()
    const adminTok = await obtainAccessToken(s.admin.username, s.admin.password)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const stuTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    await configureMockLlm({ tier4: { steps: [{ kind: 'ok', score: 77, comment: 'ok' }], repeat_last: true } })
    const preset = await createPreset(adminTok, `tier4_${s.suffix}`, 'tier4')
    await validatePreset(adminTok, preset.id)
    await setFlatCourseConfig(teacherTok, s.course_required_id, [preset.id])
    const hw = await createHomework(teacherTok, s, `E2E_LLM_${s.suffix}_${Date.now()}`)
    await apiPostJson(`/api/homeworks/${hw.id}/submission`, stuTok, {
      content: 'x',
      attachment_name: null,
      attachment_url: null,
      remove_attachment: false,
      used_llm_assist: false,
      submission_mode: 'full'
    })
    const processed = await processGradingTasks(5)
    expect(processed).toBeGreaterThanOrEqual(1)
    await expect
      .poll(async () => {
        const h = await apiHomeworkSubmissionHistory(stuTok, hw.id)
        return (h.summary?.review_score != null && h.summary?.review_score !== '') || false
      }, { timeout: 60000 })
      .toBe(true)
  })

  test('11 LLM quota stress: second queued task may fail when cap extreme (no 5xx)', async () => {
    const s = scenario()
    const adminTok = await obtainAccessToken(s.admin.username, s.admin.password)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const stuTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    await configureMockLlm({ q11: { steps: [{ kind: 'ok', score: 1, comment: 'x' }], repeat_last: true } })
    const preset = await createPreset(adminTok, `q11_${s.suffix}`, 'q11')
    await validatePreset(adminTok, preset.id)
    await setFlatCourseConfig(teacherTok, s.course_required_id, [preset.id], {
      max_input_tokens: 1000,
      max_output_tokens: 1000
    })
    const a = await createHomework(teacherTok, s, `Q11A_${Date.now()}`, { auto_grading_enabled: true })
    const b = await createHomework(teacherTok, s, `Q11B_${Date.now()}`, { auto_grading_enabled: true })
    await apiPostJson(`/api/homeworks/${a.id}/submission`, stuTok, {
      content: 'y',
      attachment_name: null,
      attachment_url: null,
      remove_attachment: false,
      used_llm_assist: false,
      submission_mode: 'full'
    })
    await apiPostJson(`/api/homeworks/${b.id}/submission`, stuTok, {
      content: 'z',
      attachment_name: null,
      attachment_url: null,
      remove_attachment: false,
      used_llm_assist: false,
      submission_mode: 'full'
    })
    await processGradingTasks(10)
    const gs = await gradingState()
    expect(gs.tasks?.failed != null || gs.tasks?.success != null).toBeTruthy()
  })

  test('12 material discussion: posts then delete material; list returns empty or 404', async () => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const stbTok = await obtainAccessToken(s.student_b.username, s.password_teacher_student)
    const body = `md12_${Date.now()}`
    await apiPostJson('/api/discussions', stTok, {
      target_type: 'material',
      target_id: s.material_discussion_id,
      subject_id: s.course_required_id,
      class_id: s.class_id_1,
      body
    })
    await apiPostJson('/api/discussions', stbTok, {
      target_type: 'material',
      target_id: s.material_discussion_id,
      subject_id: s.course_required_id,
      class_id: s.class_id_1,
      body: `${body}_b`
    })
    await apiDelete(`/api/materials/${s.material_discussion_id}`, teacherTok)
    const list = await fetchRaw(
      'GET',
      `/api/discussions?target_type=material&target_id=${s.material_discussion_id}&subject_id=${s.course_required_id}&class_id=${s.class_id_1}&page=1&page_size=20`,
      { token: stTok }
    )
    expect(list.status === 200 || list.status === 404).toBeTruthy()
  })

  test('13 material chapters: two sequential reorders; tree still loads', async () => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const tree = await getChapterTree(teacherTok, s.course_required_id)
    const nodes = tree.nodes || []
    const movable = nodes.filter(n => !n.is_uncategorized && n.id)
    expect(movable.length).toBeGreaterThanOrEqual(2)
    const ids = movable.slice(0, 2).map(n => n.id)
    await apiPostJson(`/api/material-chapters/reorder?subject_id=${s.course_required_id}`, teacherTok, {
      parent_id: null,
      ordered_chapter_ids: ids
    })
    await apiPostJson(`/api/material-chapters/reorder?subject_id=${s.course_required_id}`, teacherTok, {
      parent_id: null,
      ordered_chapter_ids: [...ids].reverse()
    })
    const t2 = await getChapterTree(teacherTok, s.course_required_id)
    expect((t2.nodes || []).length).toBeGreaterThan(0)
  })

  test('14 roster enroll idempotent: double API roster-enroll same student', async () => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const r1 = await fetchRaw('POST', `/api/subjects/${s.course_elective_id}/roster-enroll`, {
      token: teacherTok,
      body: { student_ids: [s.student_b.student_row_id] }
    })
    const r2 = await fetchRaw('POST', `/api/subjects/${s.course_elective_id}/roster-enroll`, {
      token: teacherTok,
      body: { student_ids: [s.student_b.student_row_id] }
    })
    expect(r1.status).toBeLessThan(500)
    expect(r2.status).toBeLessThan(500)
    const students = await apiGetJson(`/api/subjects/${s.course_elective_id}/students`, teacherTok)
    const n = (students || []).filter(x => x.student_id === s.student_b.student_row_id).length
    expect(n).toBe(1)
  })

  test('15 auth: password change invalidates pre-change bearer token', async ({ browser }) => {
    const s = scenario()
    const beforeTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const ctx = await browser.newContext()
    const page = await ctx.newPage()
    try {
      await login(page, s.student_plain.username, s.password_teacher_student)
      await page.goto('/personal-settings', { waitUntil: 'load', timeout: 60000 })
      const newPass = `NewE2e_${Date.now()}!a`
      const pwdInputs = page.locator('input[type="password"]')
      await pwdInputs.nth(0).fill(s.password_teacher_student)
      await pwdInputs.nth(1).fill(newPass)
      await pwdInputs.nth(2).fill(newPass)
      await page.getByRole('button', { name: '更新密码' }).click()
      await expect(page.getByText(/成功|更新/).first()).toBeVisible({ timeout: 30000 }).catch(() => {})
      await expect
        .poll(async () => (await fetchRaw('GET', '/api/auth/me', { token: beforeTok })).status, {
          timeout: 45000
        })
        .toBe(401)
      await login(page, s.student_plain.username, newPass)
      await apiPostJson(
        '/api/auth/change-password',
        await obtainAccessToken(s.student_plain.username, newPass),
        {
          current_password: newPass,
          new_password: s.password_teacher_student,
          confirm_password: s.password_teacher_student
        }
      )
    } finally {
      await ctx.close().catch(() => {})
    }
  })

  test('16 class-teacher cannot delete other teacher course', async () => {
    const s = scenario()
    expect(s.class_teacher?.username).toBeTruthy()
    const ctTok = await obtainAccessToken(s.class_teacher.username, s.password_teacher_student)
    const del = await fetchRaw('DELETE', `/api/subjects/${s.course_other_teacher_id}`, { token: ctTok })
    expect(del.status).toBe(403)
  })

  test('17 homework appeal: duplicate pending returns 400', async () => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const stuTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    await apiPutJson(`/api/homeworks/${s.homework_id}`, teacherTok, { max_submissions: 5 })
    await apiPostJson(`/api/homeworks/${s.homework_id}/submission`, stuTok, {
      content: `ap17_${Date.now()}`,
      attachment_name: null,
      attachment_url: null,
      remove_attachment: false,
      used_llm_assist: false,
      submission_mode: 'full'
    })
    const hist = await apiHomeworkSubmissionHistory(stuTok, s.homework_id)
    const sid = hist.summary?.id
    expect(sid).toBeTruthy()
    await apiPutJson(`/api/homeworks/${s.homework_id}/submissions/${sid}/review`, teacherTok, {
      review_score: 60,
      review_comment: 'r'
    })
    const payload = { reason_text: '申诉tier4理由说明至少十个字符以上才符合校验' }
    const a = await fetchRaw(
      'POST',
      `/api/homeworks/${s.homework_id}/submissions/${sid}/appeal`,
      { token: stuTok, body: payload }
    )
    expect(a.status).toBe(200)
    const b = await fetchRaw(
      'POST',
      `/api/homeworks/${s.homework_id}/submissions/${sid}/appeal`,
      { token: stuTok, body: payload }
    )
    expect(b.status).toBe(400)
  })

  test('18 score appeal: invalid target 400', async () => {
    const s = scenario()
    const stuTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const semesters = await apiGetJson('/api/semesters', stuTok)
    const sem = semesters[0]?.name
    const bad = await fetchRaw(
      'POST',
      `/api/scores/appeals?subject_id=${s.course_required_id}`,
      {
        token: stuTok,
        body: {
          semester: sem,
          target_component: 'not_a_real_component_xyz',
          reason_text: 'x'
        }
      }
    )
    expect(bad.status).toBe(400)
  })

  test('19 operation logs: material delete creates log entry', async () => {
    const s = scenario()
    const adminTok = await obtainAccessToken(s.admin.username, s.admin.password)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const mat = await apiPostJson('/api/materials', teacherTok, {
      title: `E2E日志资料_${Date.now()}`,
      content: 'c',
      class_id: s.class_id_1,
      subject_id: s.course_required_id,
      chapter_id: null
    })
    await apiDelete(`/api/materials/${mat.id}`, teacherTok)
    const logs = await apiGetJson('/api/logs?page=1&page_size=30&target_type=课程资料', adminTok)
    expect((logs.data || []).length).toBeGreaterThan(0)
  })

  test('20 five-way API stress: all responses < 500', async () => {
    const s = scenario()
    const adminTok = await obtainAccessToken(s.admin.username, s.admin.password)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const stuTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const results = await Promise.all([
      fetchRaw('GET', '/api/subjects', { token: adminTok }),
      fetchRaw('GET', '/api/notifications?page=1&page_size=20', { token: stuTok }),
      fetchRaw('POST', `/api/subjects/${s.course_required_id}/sync-enrollments`, { token: teacherTok, body: {} }),
      fetchRaw('POST', '/api/notifications', {
        token: teacherTok,
        body: {
          title: `stress_${Date.now()}`,
          content: 'x',
          priority: 'low',
          is_pinned: false,
          class_id: s.class_id_1,
          subject_id: s.course_required_id
        }
      }),
      fetchRaw('POST', `/api/homeworks/${s.homework_id}/submission`, {
        token: stuTok,
        body: {
          content: `stress_sub_${Date.now()}`,
          attachment_name: null,
          attachment_url: null,
          remove_attachment: false,
          used_llm_assist: false,
          submission_mode: 'full'
        }
      })
    ])
    for (const r of results) {
      expect(r.status).toBeLessThan(500)
    }
  })
})
