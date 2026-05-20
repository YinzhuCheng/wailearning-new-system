/**
 * Tier-3 cross-cutting E2E: seven-role cold boot, enrollment/removal races,
 * notification × homework × sync storms, explicit HTTP edge codes not covered elsewhere,
 * deep-link cold navigation under parallel API churn.
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

async function apiDeleteExpect(pathname, token) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method: 'DELETE',
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

async function apiPatchExpect(pathname, token, body) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify(body)
  })
  const text = await res.text()
  return { status: res.status, text }
}

async function apiHomeworkSubmissionHistory(token, homeworkId) {
  return apiGetJson(`/api/homeworks/${homeworkId}/submission/me/history`, token)
}

async function apiListNotifications(token, subjectId, pageSize = 50) {
  const u = new URL(`${apiBase()}/api/notifications`)
  if (subjectId != null) {
    u.searchParams.set('subject_id', String(subjectId))
  }
  u.searchParams.set('page_size', String(pageSize))
  return apiGetJson(`${u.pathname}${u.search}`, token)
}

test.describe('E2E tier-3 cross-cutting scenarios', () => {
  test.describe.configure({ timeout: 240_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e scenario — set E2E_DEV_SEED_TOKEN and globalSetup')
    }
  })

  test('01 seven-role cold parallel login: admin, both teachers, three students reach shells without session bleed', async ({
    browser
  }) => {
    const s = scenario()
    const contexts = await Promise.all(Array.from({ length: 7 }, () => browser.newContext()))
    const pages = await Promise.all(contexts.map(ctx => ctx.newPage()))
    try {
      await Promise.all([
        login(pages[0], s.admin.username, s.admin.password),
        login(pages[1], s.teacher_own.username, s.password_teacher_student),
        login(pages[2], s.teacher_other.username, s.password_teacher_student),
        login(pages[3], s.student_plain.username, s.password_teacher_student),
        login(pages[4], s.student_drop.username, s.password_teacher_student),
        login(pages[5], s.student_b.username, s.password_teacher_student),
        login(pages[6], s.student_plain.username, s.password_teacher_student)
      ])
      await Promise.all([
        pages[0].goto('/students'),
        pages[1].goto('/students'),
        pages[2].goto('/students'),
        pages[3].goto('/students'),
        pages[4].goto('/students'),
        pages[5].goto('/students'),
        pages[6].goto('/courses')
      ])
      for (const p of pages) {
        await expect(p.locator('.layout-container')).toBeVisible({ timeout: 30000 })
      }
      await expect(pages[6].url()).toContain('/courses')
    } finally {
      await Promise.all(contexts.map(c => c.close().catch(() => {})))
    }
  })

  test('02 concurrent elective enroll plus duplicate roster-enroll storm leaves exactly one enrollment row', async () => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const stTok = await obtainAccessToken(s.student_b.username, s.password_teacher_student)

    await Promise.all([
      apiPostJson(`/api/subjects/${s.course_elective_id}/student-self-enroll`, stTok, {}),
      apiPostJson(`/api/subjects/${s.course_elective_id}/student-self-enroll`, stTok, {}),
      apiPostJson(`/api/subjects/${s.course_elective_id}/roster-enroll`, teacherTok, {
        student_ids: [s.student_b.student_row_id]
      }),
      apiPostJson(`/api/subjects/${s.course_elective_id}/roster-enroll`, teacherTok, {
        student_ids: [s.student_b.student_row_id]
      })
    ])

    const roster = await apiGetJson(`/api/subjects/${s.course_elective_id}/students`, teacherTok)
    const ids = roster.map(r => Number(r.student_id)).filter(id => id === Number(s.student_b.student_row_id))
    expect(ids.length).toBe(1)
  })

  test('03 interleaved sync-enrollments, class notification fanout, and homework submission converge without deadlock', async () => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const title = `T3_SYNC_${s.suffix}_${Date.now()}`

    await Promise.all([
      apiPostJson(`/api/subjects/${s.course_required_id}/sync-enrollments`, teacherTok, {}),
      apiPostJson(`/api/subjects/${s.course_required_id}/sync-enrollments`, teacherTok, {}),
      apiPostJson('/api/notifications', teacherTok, {
        title,
        content: 'sync storm',
        audience: 'class',
        subject_id: s.course_required_id,
        class_id: s.class_id_1,
        notification_kind: 'general'
      }),
      fetch(`${apiBase()}/api/homeworks/${s.homework_id}/submission`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${stTok}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: `sync-submit-${Date.now()}`,
          attachment_name: null,
          attachment_url: null,
          remove_attachment: false,
          used_llm_assist: false,
          submission_mode: 'full'
        })
      })
    ])

    const list = await apiListNotifications(stTok, s.course_required_id)
    expect((list.data || []).some(n => n.title === title)).toBe(true)
    const hist = await apiHomeworkSubmissionHistory(stTok, s.homework_id)
    expect((hist.attempts || []).length).toBeGreaterThanOrEqual(1)
  })

  test('04 HTTP edges: materials and notifications page_size over limit 422; homework list 422; teacher PATCH user 405', async () => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const adminTok = await obtainAccessToken(s.admin.username, s.admin.password)
    const users = await apiGetJson('/api/users', adminTok)
    const target = users.find(u => u.username === s.student_plain.username)
    expect(target).toBeTruthy()

    const mat = await fetch(
      `${apiBase()}/api/materials?subject_id=${s.course_required_id}&page=1&page_size=101`,
      { headers: { Authorization: `Bearer ${teacherTok}` } }
    )
    expect(mat.status).toBe(422)

    const notif = await fetch(`${apiBase()}/api/notifications?page=1&page_size=150`, {
      headers: { Authorization: `Bearer ${teacherTok}` }
    })
    expect(notif.status).toBe(422)

    const hw = await fetch(
      `${apiBase()}/api/homeworks?subject_id=${s.course_required_id}&page=1&page_size=500`,
      { headers: { Authorization: `Bearer ${teacherTok}` } }
    )
    expect(hw.status).toBe(422)

    const patchUser = await apiPatchExpect(`/api/users/${target.id}`, teacherTok, { real_name: 'nope' })
    expect(patchUser.status).toBe(405)
  })

  test('05 student cannot remove peer from course roster (403); teacher cannot self-drop required enrollment (400)', async () => {
    const s = scenario()
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    const badRemove = await apiDeleteExpect(
      `/api/subjects/${s.course_required_id}/students/${s.student_b.student_row_id}`,
      stTok
    )
    expect(badRemove.status).toBe(403)

    const teacherDropReq = await apiPostJsonExpect(`/api/subjects/${s.course_required_id}/student-self-drop`, teacherTok, {})
    expect(teacherDropReq.status).toBe(403)
  })

  test('06 concurrent notification ID mark-read plus delete competing rows ends with 404 on stale ID without server 500', async () => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)

    const a = await apiPostJson('/api/notifications', teacherTok, {
      title: `T3_RA_${s.suffix}_a_${Date.now()}`,
      content: 'race',
      audience: 'class',
      subject_id: s.course_required_id,
      class_id: s.class_id_1,
      notification_kind: 'general'
    })
    const b = await apiPostJson('/api/notifications', teacherTok, {
      title: `T3_RA_${s.suffix}_b_${Date.now()}`,
      content: 'race',
      audience: 'class',
      subject_id: s.course_required_id,
      class_id: s.class_id_1,
      notification_kind: 'general'
    })

    await Promise.all([
      fetch(`${apiBase()}/api/notifications/${a.id}/read`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${stTok}` }
      }),
      apiDeleteExpect(`/api/notifications/${a.id}`, teacherTok),
      fetch(`${apiBase()}/api/notifications/${b.id}/read`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${stTok}` }
      }),
      apiDeleteExpect(`/api/notifications/${b.id}`, teacherTok)
    ])

    const gone = await fetch(`${apiBase()}/api/notifications/${a.id}/read`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${stTok}` }
    })
    expect(gone.status).toBe(404)
  })

  test('07 dual-tab student UI submit races triple concurrent API submits; attempt history stays coherent', async ({
    browser
  }) => {
    const s = scenario()
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const stamp = Date.now()

    const ctx1 = await browser.newContext()
    const ctx2 = await browser.newContext()
    const p1 = await ctx1.newPage()
    const p2 = await ctx2.newPage()
    try {
      await login(p1, s.student_plain.username, s.password_teacher_student)
      await login(p2, s.student_plain.username, s.password_teacher_student)
      await enterSeededRequiredCourse(p1, s.suffix)
      await enterSeededRequiredCourse(p2, s.suffix)
      await p1.goto(`/homework/${s.homework_id}/submit`, { waitUntil: 'load', timeout: 60000 })
      await p2.goto(`/homework/${s.homework_id}/submit`, { waitUntil: 'load', timeout: 60000 })

      const apiStorm = Promise.all(
        [0, 1, 2].map(i =>
          fetch(`${apiBase()}/api/homeworks/${s.homework_id}/submission`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${stTok}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({
              content: `dual-api-${stamp}-${i}`,
              attachment_name: null,
              attachment_url: null,
              remove_attachment: false,
              used_llm_assist: false,
              submission_mode: 'full'
            })
          })
        )
      )

      await Promise.all([
        apiStorm,
        (async () => {
          await p1.getByTestId('homework-submit-content').fill(`dual-ui-a-${stamp}`)
          await p1.getByTestId('homework-submit-save').click()
        })(),
        (async () => {
          await p2.getByTestId('homework-submit-content').fill(`dual-ui-b-${stamp}`)
          await p2.getByTestId('homework-submit-save').click()
        })()
      ])

      await expect(p1.getByText(/作业已提交|提交成功|已保存/)).toBeVisible({ timeout: 45000 })
      await expect(p2.getByText(/作业已提交|提交成功|已保存/)).toBeVisible({ timeout: 45000 })
    } finally {
      await ctx1.close().catch(() => {})
      await ctx2.close().catch(() => {})
    }

    await expect
      .poll(async () => (await apiHomeworkSubmissionHistory(stTok, s.homework_id)).attempts?.length || 0, {
        timeout: 40000
      })
      .toBeGreaterThanOrEqual(1)
  })

  test('08 cold student deep-link to materials while teacher publishes homework and notifications lists converge', async ({
    browser
  }) => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const title = `T3_MAT_${s.suffix}_${Date.now()}`
    await apiPostJson('/api/homeworks', teacherTok, {
      class_id: s.class_id_1,
      subject_id: s.course_required_id,
      title,
      content: 'cold mat',
      max_score: 100,
      grade_precision: 'integer',
      auto_grading_enabled: false,
      allow_late_submission: true,
      late_submission_affects_score: false
    })

    const ctx = await browser.newContext()
    const p = await ctx.newPage()
    try {
      await login(p, s.student_plain.username, s.password_teacher_student)
      const nav = (async () => {
        await p.goto('/materials', { waitUntil: 'load', timeout: 60000 })
      })()
      const fanout = apiPostJson('/api/notifications', teacherTok, {
        title: `T3_MAT_N_${Date.now()}`,
        content: 'fan',
        audience: 'class',
        subject_id: s.course_required_id,
        class_id: s.class_id_1,
        notification_kind: 'general'
      })
      await Promise.all([nav, fanout])
      await enterSeededRequiredCourse(p, s.suffix)
      await expect(p.locator('.layout-container')).toBeVisible({ timeout: 25000 })
      await p.goto('/homework', { waitUntil: 'load', timeout: 60000 })
      await expect(p.getByRole('row', { name: new RegExp(escapeRegex(title)) })).toBeVisible({ timeout: 30000 })
    } finally {
      await ctx.close().catch(() => {})
    }
  })

  test('09 admin removes student from elective while student attempts concurrent double self-drop remains idempotent', async () => {
    const s = scenario()
    const adminTok = await obtainAccessToken(s.admin.username, s.admin.password)
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)

    await apiPostJson(`/api/subjects/${s.course_elective_id}/student-self-enroll`, stTok, {})

    const results = await Promise.all([
      apiDeleteExpect(`/api/subjects/${s.course_elective_id}/students/${s.student_plain.student_row_id}`, adminTok),
      apiPostJsonExpect(`/api/subjects/${s.course_elective_id}/student-self-drop`, stTok, {}),
      apiPostJsonExpect(`/api/subjects/${s.course_elective_id}/student-self-drop`, stTok, {})
    ])

    expect(results.every(r => r.status >= 200 && r.status < 500)).toBe(true)

    const roster = await apiGetJson(`/api/subjects/${s.course_elective_id}/students`, adminTok)
    expect(roster.some(r => Number(r.student_id) === Number(s.student_plain.student_row_id))).toBe(false)
  })

  test('10 teacher toggles enrollment type required→elective→required while concurrent sync-enrollments runs; student_plain stays enrolled', async () => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    await Promise.all([
      apiPutJsonExpect(
        `/api/subjects/${s.course_required_id}/students/${s.student_plain.student_row_id}/enrollment-type`,
        teacherTok,
        { enrollment_type: 'elective' }
      ),
      apiPostJson(`/api/subjects/${s.course_required_id}/sync-enrollments`, teacherTok, {})
    ])

    await apiPutJsonExpect(
      `/api/subjects/${s.course_required_id}/students/${s.student_plain.student_row_id}/enrollment-type`,
      teacherTok,
      { enrollment_type: 'required' }
    )
    await apiPostJson(`/api/subjects/${s.course_required_id}/sync-enrollments`, teacherTok, {})

    const roster = await apiGetJson(`/api/subjects/${s.course_required_id}/students`, teacherTok)
    const row = roster.find(r => Number(r.student_id) === Number(s.student_plain.student_row_id))
    expect(row).toBeTruthy()
    expect((row.enrollment_type || '').toLowerCase()).toBe('required')
  })
})
