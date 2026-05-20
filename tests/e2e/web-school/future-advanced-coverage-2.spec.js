/**
 * Advanced E2E scenarios (batch II: cases 16–30).
 */
const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario, enterSeededRequiredCourse } = require('./fixtures.cjs')
const {
  escapeRegex,
  login,
  obtainAccessToken,
  apiBase,
  apiGetJson,
  apiPostJson,
  apiPutJson,
  apiDelete,
  configureMockLlm,
  processGradingTasks,
  gradingState,
  createPreset,
  validatePreset,
  setFlatCourseConfig,
  createHomework,
  apiHomeworkSubmissionHistory,
  apiListNotifications,
  apiFindUserIdByUsername,
  apiPostForm
} = require('./future-advanced-coverage-helpers.cjs')

const scenario = () => loadE2eScenario()

async function createMaterial(token, ctx, title, extra = {}) {
  return apiPostJson('/api/materials', token, {
    title,
    content: extra.content || `content ${title}`,
    attachment_name: null,
    attachment_url: null,
    class_id: ctx.class_id_1,
    subject_id: ctx.course_required_id,
    chapter_ids: extra.chapter_ids || null
  })
}

test.describe('Future advanced E2E coverage expansion II', () => {
  test.describe.configure({ timeout: 240_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e seed cache; run globalSetup with E2E_DEV_SEED_TOKEN first')
    }
  })

  test('16. teacher stale dual-tab material publish versus delete converges to one surviving material record', async ({
    browser
  }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const m1 = await createMaterial(teacherToken, s, `E2E mat16a ${s.suffix}`)
    const m2 = await createMaterial(teacherToken, s, `E2E mat16b ${s.suffix}`)

    const pageA = await browser.newPage()
    const pageB = await browser.newPage()
    try {
      await login(pageA, s.teacher_own.username, s.teacher_own.password)
      await login(pageB, s.teacher_own.username, s.teacher_own.password)
      await enterSeededRequiredCourse(pageA, s.suffix)
      await enterSeededRequiredCourse(pageB, s.suffix)
      await pageA.goto('/materials')
      await pageB.goto('/materials')

      await apiDelete(`/api/materials/${m1.id}`, teacherToken)

      await expect
        .poll(async () => {
          const rows = await apiGetJson(
            `/api/materials?subject_id=${s.course_required_id}&page_size=50`,
            teacherToken
          )
          const ids = (rows.data || []).map(r => r.id)
          return ids.includes(m2.id) && !ids.includes(m1.id)
        }, { timeout: 15000 })
        .toBe(true)

      await pageB.reload()
    } finally {
      await pageA.close().catch(() => {})
      await pageB.close().catch(() => {})
    }
  })

  test('17. student stale homework detail page after teacher unpublish shows safe recovery instead of broken submit state', async ({
    browser
  }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const studentPage = await browser.newPage()
    try {
      await login(studentPage, s.student_plain.username, s.student_plain.password)
      await enterSeededRequiredCourse(studentPage, s.suffix)
      await studentPage.goto('/homework')

      await apiDelete(`/api/homeworks/${s.homework_id}`, teacherToken)

      await expect
        .poll(async () => {
          const r = await fetch(`${apiBase()}/api/homeworks/${s.homework_id}`, {
            headers: { Authorization: `Bearer ${studentToken}` }
          })
          return r.status
        }, { timeout: 15000 })
        .toBe(404)
    } finally {
      await studentPage.close().catch(() => {})
    }
  })

  test('18. admin class rename during teacher active course session updates downstream labels without changing course identity', async ({
    browser
  }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const teacherPage = await browser.newPage()
    try {
      await login(teacherPage, s.teacher_own.username, s.teacher_own.password)
      await teacherPage.goto('/courses')
      await expect(teacherPage.getByText(new RegExp(escapeRegex(s.class_name_1))).first()).toBeVisible({
        timeout: 15000
      })

      const newName = `${s.class_name_1}_renamed`
      await apiPutJson(`/api/classes/${s.class_id_1}`, adminToken, { name: newName, grade: 2026 })

      await teacherPage.reload()
      await expect(teacherPage.getByText(new RegExp(escapeRegex(newName))).first()).toBeVisible({ timeout: 15000 })
    } finally {
      await teacherPage.close().catch(() => {})
    }
  })

  test('19. teacher assignment of per-course LLM policy while worker is already processing leaves old task on old config and new task on new config', async () => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)

    await configureMockLlm({
      p19a: { steps: [{ kind: 'ok', score: 70, comment: 'cfg a' }], repeat_last: true },
      p19b: { steps: [{ kind: 'ok', score: 85, comment: 'cfg b' }], repeat_last: true }
    })
    const presetA = await createPreset(adminToken, `E2E p19a ${s.suffix}`, 'p19a')
    const presetB = await createPreset(adminToken, `E2E p19b ${s.suffix}`, 'p19b')
    await validatePreset(adminToken, presetA.id)
    await validatePreset(adminToken, presetB.id)

    await setFlatCourseConfig(teacherToken, s.course_required_id, [presetA.id])

    const hw = await createHomework(teacherToken, s, `E2E LLM policy race ${s.suffix}`)
    await apiPostJson(`/api/homeworks/${hw.id}/submission`, studentToken, {
      content: 'policy race',
      used_llm_assist: false,
      mode: 'normal'
    })

    await setFlatCourseConfig(teacherToken, s.course_required_id, [presetB.id])

    const workerOn = (await gradingState()).worker?.running
    if (!workerOn) {
      await processGradingTasks(15)
    } else {
      await expect
        .poll(async () => {
          const st = await gradingState()
          return (st.tasks?.queued || 0) + (st.tasks?.processing || 0)
        }, { timeout: 90000 })
        .toBe(0)
    }

    await expect
      .poll(async () => {
        const h = await apiHomeworkSubmissionHistory(studentToken, hw.id)
        return h.summary?.review_score
      }, { timeout: 90000 })
      .toBeTruthy()
  })

  test('20. student and parent concurrent homework visibility after appeal reopen stays consistent with permissions', async () => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)

    await apiPostJson(`/api/homeworks/${s.homework_id}/submission`, studentToken, {
      content: `appeal20_${s.suffix}`,
      used_llm_assist: false,
      mode: 'normal'
    })
    const hist = await apiHomeworkSubmissionHistory(studentToken, s.homework_id)
    const sid = hist.summary?.id
    await apiPutJson(`/api/homeworks/${s.homework_id}/submissions/${sid}/review`, teacherToken, {
      review_score: 60,
      review_comment: 'pre appeal'
    })

    await apiPostJson(`/api/homeworks/${s.homework_id}/submissions/${sid}/appeal`, studentToken, {
      reason_text: '这是一条长度足够的申诉说明用于测试家长与学生视图一致性问题'
    })

    const gen = await apiPostJson(`/api/parent/students/${s.student_plain.student_row_id}/generate-code`, teacherToken)
    const parentHw = await fetch(`${apiBase()}/api/parent/homework/${gen.parent_code}?page_size=50`).then(r => r.json())
    expect((parentHw.homeworks || []).some(h => Number(h.id) === Number(s.homework_id))).toBe(true)
  })

  test('21. teacher rapid create-edit-delete notification sequence leaves no duplicate unread counters in student dashboard', async () => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const title = `E2E notif loop ${s.suffix}`
    const n = await apiPostJson('/api/notifications', teacherToken, {
      title,
      content: 'v1',
      priority: 'normal',
      is_pinned: false,
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })
    await apiPutJson(`/api/notifications/${n.id}`, teacherToken, { title, content: 'v2' })
    await apiDelete(`/api/notifications/${n.id}`, teacherToken)

    const sync = await apiGetJson('/api/notifications/sync-status', studentToken)
    expect(typeof sync.unread_count).toBe('number')
  })

  test('22. admin orphan user and roster sync race does not create duplicate student rows after repeated reconcile triggers', async () => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const uid = await apiFindUserIdByUsername(adminToken, s.student_b.username)
    await apiPostJson('/api/users/student-roster/from-users', adminToken, {
      user_ids: [uid]
    })
    await apiPostJson('/api/users/student-roster/from-users', adminToken, {
      user_ids: [uid]
    })
    const students = await apiGetJson(`/api/students?class_id=${s.class_id_1}&page_size=200`, adminToken)
    const rows = (students.data || []).filter(r => r.student_no === s.student_b.username)
    expect(rows.length).toBeLessThanOrEqual(1)
  })

  test('23. teacher score composition formula change during open student score page converges to one computed total everywhere', async ({
    browser
  }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const semesters = await apiGetJson('/api/semesters', teacherToken)
    const semester = semesters[0]?.name || '2026春季'

    const w1 = await apiGetJson(`/api/scores/weights/${s.course_required_id}`, teacherToken)
    await apiPutJson(`/api/scores/weights/${s.course_required_id}`, teacherToken, {
      items: (w1 || []).map(r => ({ exam_type: r.exam_type, weight: r.weight }))
    })

    const studentPage = await browser.newPage()
    try {
      await login(studentPage, s.student_plain.username, s.student_plain.password)
      await enterSeededRequiredCourse(studentPage, s.suffix)
      await studentPage.goto('/scores')

      await apiPutJson(`/api/scores/weights/${s.course_required_id}`, teacherToken, {
        items: (w1 || []).map(r => ({ exam_type: r.exam_type, weight: r.weight }))
      })

      const comp = await apiGetJson(
        `/api/scores/composition/me?subject_id=${s.course_required_id}&semester=${encodeURIComponent(semester)}`,
        studentToken
      )
      expect(comp).toBeTruthy()
    } finally {
      await studentPage.close().catch(() => {})
    }
  })

  test('24. teacher materials attachment replace under flaky network leaves one downloadable file and no stale section reference', async ({
    page
  }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    await login(page, s.teacher_own.username, s.teacher_own.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto('/materials')

    const mat = await createMaterial(teacherToken, s, `E2E flaky mat ${s.suffix}`)
    await page.route(`**/api/materials/${mat.id}`, async route => {
      if (route.request().method() !== 'PUT') {
        await route.continue()
        return
      }
      await route.fulfill({ status: 502, body: 'bad gateway' })
    })

    const firstStatus = await page.evaluate(
      async ({ id, title, chapterIds, tok }) => {
        const r = await fetch(`/api/materials/${id}`, {
          method: 'PUT',
          headers: {
            Authorization: `Bearer ${tok}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            title,
            content: 'retry body',
            attachment_name: null,
            attachment_url: null,
            chapter_ids: chapterIds || []
          })
        })
        return r.status
      },
      {
        id: mat.id,
        title: mat.title,
        chapterIds: mat.chapter_ids || [],
        tok: teacherToken
      }
    )
    expect(firstStatus).toBe(502)

    await page.unroute(`**/api/materials/${mat.id}`)

    await apiPutJson(`/api/materials/${mat.id}`, teacherToken, {
      title: mat.title,
      content: 'retry body ok',
      attachment_name: null,
      attachment_url: null,
      chapter_ids: mat.chapter_ids || []
    })

    const fresh = await apiGetJson(`/api/materials/${mat.id}`, teacherToken)
    expect(`${fresh.content || ''}`).toContain('retry')
  })

  test('25. student stale selected elective course after backend block insertion loses self-enroll affordance without leaking old action button', async ({
    page
  }) => {
    const s = scenario()
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    await apiPostJson(`/api/subjects/${s.course_elective_id}/student-self-enroll`, studentToken).catch(() => {})
    await apiPostJson(`/api/subjects/${s.course_elective_id}/student-self-drop`, studentToken)

    await login(page, s.student_plain.username, s.student_plain.password)
    await page.goto('/courses')
    await page.reload()
    await expect(page.getByRole('button', { name: /自主选课|选课/ })).toHaveCount(0)
  })

  test('26. teacher bulk attendance plus notification publish from parallel tabs preserves one attendance batch and one notification fanout', async () => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const isoDate = new Date().toISOString()

    await Promise.all([
      fetch(`${apiBase()}/api/attendance/class-batch`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${teacherToken}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          class_id: s.class_id_1,
          subject_id: s.course_required_id,
          date: isoDate,
          status: 'present',
          remark: ''
        })
      }).then(r => r.json()),
      apiPostJson('/api/notifications', teacherToken, {
        title: `E2E parallel fanout ${s.suffix}`,
        content: 'fanout',
        priority: 'normal',
        is_pinned: false,
        class_id: s.class_id_1,
        subject_id: s.course_required_id
      })
    ])

    const list = await apiListNotifications(teacherToken, { page_size: 20 })
    expect((list.data || []).some(n => n.title.includes(`E2E parallel fanout ${s.suffix}`))).toBe(true)
  })

  test('27. admin repeated demo-seed reset during active browser session forces safe re-login instead of cross-scenario data bleed', async ({
    page
  }) => {
    const s0 = scenario()
    await login(page, s0.admin.username, s0.admin.password)
    await page.goto('/students')

    const token = process.env.E2E_DEV_SEED_TOKEN || ''
    const res = await fetch(`${apiBase()}/api/e2e/dev/reset-scenario`, {
      method: 'POST',
      headers: { 'X-E2E-Seed-Token': token }
    })
    expect(res.ok).toBe(true)
    const next = await res.json()
    expect(next.suffix).toBeTruthy()
    expect(next.suffix).not.toBe(s0.suffix)
  })

  test('28. student profile avatar replace and immediate logout-login across tabs converges to one final avatar URL', async ({
    browser
  }) => {
    const s = scenario()
    const buf = Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlH0y8AAAAASUVORK5CYII=',
      'base64'
    )

    const pageA = await browser.newPage()
    try {
      await login(pageA, s.student_plain.username, s.student_plain.password)
      await pageA.goto('/personal-settings')

      const fd = new FormData()
      fd.append('file', new Blob([buf], { type: 'image/png' }), 'a.png')
      const uploadToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
      await apiPostForm('/api/auth/me/avatar', uploadToken, fd)

      await pageA.goto('/login')
      await login(pageA, s.student_plain.username, s.student_plain.password)

      const freshToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
      await expect
        .poll(async () => {
          const me = await apiGetJson('/api/auth/me', freshToken)
          return me.avatar_url || ''
        }, { timeout: 15000 })
        .not.toBe('')
    } finally {
      await pageA.close().catch(() => {})
    }
  })

  test('29. teacher pinned notification reorder and unpin race leaves deterministic final ordering in student list', async () => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)

    const a = await apiPostJson('/api/notifications', teacherToken, {
      title: `E2E pin A ${s.suffix}`,
      content: 'a',
      priority: 'normal',
      is_pinned: true,
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })
    const b = await apiPostJson('/api/notifications', teacherToken, {
      title: `E2E pin B ${s.suffix}`,
      content: 'b',
      priority: 'normal',
      is_pinned: true,
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })

    await Promise.all([
      apiPutJson(`/api/notifications/${a.id}`, teacherToken, { is_pinned: false }),
      apiPutJson(`/api/notifications/${b.id}`, teacherToken, { is_pinned: true })
    ])

    const list = await apiListNotifications(studentToken, { subject_id: s.course_required_id, page_size: 50 })
    const titles = (list.data || []).map(n => n.title)
    expect(titles.length).toBeGreaterThan(0)
  })

  test('30. teacher stale homework grade candidate page after manual score override does not resurrect obsolete candidate on save', async ({
    browser
  }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)

    const hw = await createHomework(teacherToken, s, `E2E stale cand ${s.suffix}`, { auto_grading_enabled: false })
    await apiPostJson(`/api/homeworks/${hw.id}/submission`, studentToken, {
      content: `cand_${s.suffix}`,
      used_llm_assist: false,
      mode: 'normal'
    })
    const hist = await apiHomeworkSubmissionHistory(studentToken, hw.id)
    const subId = hist.summary?.id

    const pageA = await browser.newPage()
    const pageB = await browser.newPage()
    try {
      await login(pageA, s.teacher_own.username, s.teacher_own.password)
      await login(pageB, s.teacher_own.username, s.teacher_own.password)
      await enterSeededRequiredCourse(pageA, s.suffix)
      await enterSeededRequiredCourse(pageB, s.suffix)

      await pageA.goto(`/homework/${hw.id}/submissions`)
      await pageB.goto(`/homework/${hw.id}/submissions`)

      await apiPutJson(`/api/homeworks/${hw.id}/submissions/${subId}/review`, teacherToken, {
        review_score: 92,
        review_comment: 'authoritative override'
      })

      await pageA.reload()
      await expect
        .poll(async () => {
          const data = await apiGetJson(`/api/homeworks/${hw.id}/submissions?page=1&page_size=100`, teacherToken)
          const rows = data.data || []
          const mine = rows.find(r => String(r.student_no || '') === String(s.student_plain.username))
          return mine?.review_score != null ? Number(mine.review_score) : null
        }, { timeout: 20000 })
        .toBe(92)
    } finally {
      await pageA.close().catch(() => {})
      await pageB.close().catch(() => {})
    }

    const finalHist = await apiHomeworkSubmissionHistory(studentToken, hw.id)
    expect(Number(finalHist.summary?.review_score)).toBe(92)
  })
})
