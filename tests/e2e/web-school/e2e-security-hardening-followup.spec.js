/**
 * Small browser-backed security hardening slice.
 *
 * These cases intentionally use Playwright's browser/request environment to
 * prove API authorization still holds when a user bypasses visible UI controls.
 */
const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario } = require('./fixtures.cjs')
const { login, obtainAccessToken } = require('./future-advanced-coverage-helpers.cjs')

const scenario = () => loadE2eScenario()

function apiBase() {
  return (process.env.E2E_API_URL || 'http://127.0.0.1:8012').replace(/\/$/, '')
}

async function apiStatus(pathname, { method = 'GET', token, headers = {}, body } = {}) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method,
    headers: {
      ...(body == null ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers
    },
    body: body == null ? undefined : JSON.stringify(body)
  })
  return { status: res.status, text: await res.text() }
}

test.describe('security hardening follow-up E2E (14 cases)', () => {
  test.describe.configure({ timeout: 180_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e seed; run via scripts/playwright-external-runner.cjs')
    }
  })

  test('01 tampering stored role in browser does not grant admin API access', async ({ page }) => {
    const s = scenario()
    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.evaluate(() => {
      localStorage.setItem('user_role', 'admin')
      localStorage.setItem('role', 'admin')
      const raw = localStorage.getItem('user')
      if (raw) {
        try {
          const parsed = JSON.parse(raw)
          parsed.role = 'admin'
          localStorage.setItem('user', JSON.stringify(parsed))
        } catch {
          /* ignore non-JSON storage */
        }
      }
    })
    const token = await page.evaluate(() => localStorage.getItem('token') || localStorage.getItem('access_token'))
    expect(token).toBeTruthy()

    const res = await page.request.get(`${apiBase()}/api/users`, {
      headers: { Authorization: `Bearer ${token}` }
    })
    expect(res.status()).toBe(403)
  })

  test('02 student direct POST to admin course creation API is forbidden', async () => {
    const s = scenario()
    const token = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const { status } = await apiStatus('/api/subjects', {
      method: 'POST',
      token,
      body: {
        name: `E2E_forbidden_security_${Date.now()}`,
        class_id: s.class_id_1,
        teacher_id: s.teacher_user_id,
        course_type: 'required',
        status: 'active'
      }
    })
    expect(status).toBe(403)
  })

  test('03 seed token alone cannot call powerful E2E mock-LLM endpoint', async () => {
    const { status, text } = await apiStatus('/api/e2e/dev/mock-llm/configure', {
      method: 'POST',
      headers: { 'X-E2E-Seed-Token': process.env.E2E_DEV_SEED_TOKEN || 'test-playwright-seed' },
      body: { profiles: {} }
    })
    expect(status).toBe(403)
    expect(text).toContain('administrator Bearer')
  })

  test('04 old browser token is rejected after password change in another tab', async ({ browser }) => {
    const s = scenario()
    const ctxA = await browser.newContext()
    const ctxB = await browser.newContext()
    const pageA = await ctxA.newPage()
    const pageB = await ctxB.newPage()
    const newPassword = `E2eNew_${Date.now()}!a9`
    try {
      await login(pageA, s.student_drop.username, s.password_teacher_student)
      const oldToken = await pageA.evaluate(() => localStorage.getItem('token') || localStorage.getItem('access_token'))
      expect(oldToken).toBeTruthy()

      await login(pageB, s.student_drop.username, s.password_teacher_student)
      const change = await pageB.request.post(`${apiBase()}/api/auth/change-password`, {
        headers: { Authorization: `Bearer ${oldToken}`, 'Content-Type': 'application/json' },
        data: {
          current_password: s.password_teacher_student,
          new_password: newPassword,
          confirm_password: newPassword
        }
      })
      expect(change.status()).toBe(200)

      const stale = await pageA.request.get(`${apiBase()}/api/auth/me`, {
        headers: { Authorization: `Bearer ${oldToken}` }
      })
      expect(stale.status()).toBe(401)

      const freshToken = await obtainAccessToken(s.student_drop.username, newPassword)
      const restore = await apiStatus('/api/auth/change-password', {
        method: 'POST',
        token: freshToken,
        body: {
          current_password: newPassword,
          new_password: s.password_teacher_student,
          confirm_password: s.password_teacher_student
        }
      })
      expect(restore.status).toBe(200)
    } finally {
      await ctxA.close().catch(() => {})
      await ctxB.close().catch(() => {})
    }
  })

  test('05 class teacher cannot rebind visible required course to another class via direct API', async () => {
    const s = scenario()
    const token = await obtainAccessToken(s.class_teacher.username, s.password_teacher_student)
    const before = await apiStatus(`/api/subjects/${s.course_required_id}`, { token })
    expect(before.status).toBe(200)

    const rebinding = await apiStatus(`/api/subjects/${s.course_required_id}`, {
      method: 'PUT',
      token,
      body: { class_id: s.class_id_2 }
    })
    expect(rebinding.status).toBe(403)

    const after = await apiStatus(`/api/subjects/${s.course_required_id}`, { token })
    expect(after.status).toBe(200)
    const payload = JSON.parse(after.text)
    const ids = (payload.class_links || []).map(row => Number(row.class_id))
    expect(ids).toContain(Number(s.class_id_1))
    expect(ids).not.toContain(Number(s.class_id_2))
  })

  test('06 class teacher cannot hijack teacher-owned visible course by updating metadata', async () => {
    const s = scenario()
    const token = await obtainAccessToken(s.class_teacher.username, s.password_teacher_student)

    const before = await apiStatus(`/api/subjects/${s.course_required_id}`, { token })
    expect(before.status).toBe(200)
    const beforePayload = JSON.parse(before.text)
    expect(Number(beforePayload.teacher_id)).toBe(Number(s.teacher_user_id))

    const hijack = await apiStatus(`/api/subjects/${s.course_required_id}`, {
      method: 'PUT',
      token,
      body: { name: `E2E forbidden hijack ${Date.now()}` }
    })
    expect(hijack.status).toBe(403)

    const after = await apiStatus(`/api/subjects/${s.course_required_id}`, { token })
    expect(after.status).toBe(200)
    const afterPayload = JSON.parse(after.text)
    expect(Number(afterPayload.teacher_id)).toBe(Number(s.teacher_user_id))
  })

  test('07 class teacher cannot delete teacher-owned visible course via direct API', async () => {
    const s = scenario()
    const token = await obtainAccessToken(s.class_teacher.username, s.password_teacher_student)

    const before = await apiStatus(`/api/subjects/${s.course_required_id}`, { token })
    expect(before.status).toBe(200)

    const deletion = await apiStatus(`/api/subjects/${s.course_required_id}`, { method: 'DELETE', token })
    expect(deletion.status).toBe(403)

    const after = await apiStatus(`/api/subjects/${s.course_required_id}`, { token })
    expect(after.status).toBe(200)
  })

  test('08 class teacher cannot sync teacher-owned visible course roster via direct API', async () => {
    const s = scenario()
    const token = await obtainAccessToken(s.class_teacher.username, s.password_teacher_student)

    const before = await apiStatus(`/api/subjects/${s.course_required_id}`, { token })
    expect(before.status).toBe(200)

    const sync = await apiStatus(`/api/subjects/${s.course_required_id}/sync-enrollments`, {
      method: 'POST',
      token
    })
    expect(sync.status).toBe(403)
  })

  test('09 class teacher cannot alter teacher-owned visible course grading scheme via direct API', async () => {
    const s = scenario()
    const token = await obtainAccessToken(s.class_teacher.username, s.password_teacher_student)

    const before = await apiStatus(`/api/scores/grade-scheme/${s.course_required_id}`, { token })
    expect(before.status).toBe(200)

    const update = await apiStatus(`/api/scores/grade-scheme/${s.course_required_id}`, {
      method: 'PUT',
      token,
      body: { homework_weight: 5, extra_daily_weight: 5 }
    })
    expect(update.status).toBe(403)
  })

  test('10 class teacher cannot publish notification into teacher-owned visible course via direct API', async () => {
    const s = scenario()
    const token = await obtainAccessToken(s.class_teacher.username, s.password_teacher_student)

    const before = await apiStatus(`/api/subjects/${s.course_required_id}`, { token })
    expect(before.status).toBe(200)

    const notice = await apiStatus('/api/notifications', {
      method: 'POST',
      token,
      body: {
        title: `E2E forbidden notice ${Date.now()}`,
        content: 'should not publish',
        content_format: 'plain',
        priority: 'normal',
        class_id: s.class_id_1,
        subject_id: s.course_required_id
      }
    })
    expect(notice.status).toBe(403)
  })

  test('11 class teacher cannot delete teacher-owned visible discussion entry via direct API', async () => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const classTeacherToken = await obtainAccessToken(s.class_teacher.username, s.password_teacher_student)

    const created = await apiStatus('/api/discussions', {
      method: 'POST',
      token: teacherToken,
      body: {
        target_type: 'homework',
        target_id: s.homework_id,
        subject_id: s.course_required_id,
        class_id: s.class_id_1,
        body: `e2e discussion delete guard ${Date.now()}`,
        body_format: 'plain'
      }
    })
    expect(created.status).toBe(200)
    const entry = JSON.parse(created.text)

    const deletion = await apiStatus(`/api/discussions/${entry.id}`, {
      method: 'DELETE',
      token: classTeacherToken
    })
    expect(deletion.status).toBe(403)

    const list = await apiStatus(
      `/api/discussions?target_type=homework&target_id=${s.homework_id}&subject_id=${s.course_required_id}&class_id=${s.class_id_1}&page=1&page_size=20`,
      { token: teacherToken }
    )
    expect(list.status).toBe(200)
    expect(JSON.parse(list.text).data.some(row => Number(row.id) === Number(entry.id))).toBe(true)
  })

  test('12 stale selected_course cache cannot expose course LLM config to visible non-manager', async ({ page }) => {
    const s = scenario()
    await login(page, s.class_teacher.username, s.password_teacher_student)
    await page.evaluate(subjectId => {
      localStorage.setItem('selected_course', String(subjectId))
      localStorage.setItem('selectedCourse', JSON.stringify({ id: subjectId, name: 'tampered-visible-course' }))
    }, s.course_required_id)
    const token = await page.evaluate(() => localStorage.getItem('token') || localStorage.getItem('access_token'))
    expect(token).toBeTruthy()

    const cfg = await page.request.get(`${apiBase()}/api/llm-settings/courses/${s.course_required_id}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
    expect(cfg.status()).toBe(403)
  })

  test('13 parent portal API hides same-class elective homework for unenrolled student', async () => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    await apiStatus(`/api/subjects/${s.course_elective_id}/students/${s.student_plain.student_row_id}`, {
      method: 'DELETE',
      token: teacherToken
    })
    const hiddenTitle = `E2E hidden elective homework ${Date.now()}`
    const created = await apiStatus('/api/homeworks', {
      method: 'POST',
      token: teacherToken,
      body: {
        title: hiddenTitle,
        content: 'same class elective homework should stay hidden from parent code user',
        content_format: 'plain',
        class_id: s.class_id_1,
        subject_id: s.course_elective_id,
        due_date: null,
        max_score: 100,
        grade_precision: 'integer',
        auto_grading_enabled: false,
        allow_late_submission: true,
        late_submission_affects_score: false,
        max_submissions: null,
        llm_routing_spec: null
      }
    })
    expect(created.status).toBe(200)

    const parentHomeworks = await apiStatus(`/api/parent/homework/${s.parent_code}?page_size=100`)
    expect(parentHomeworks.status).toBe(200)
    const titles = JSON.parse(parentHomeworks.text).homeworks.map(row => row.title)
    expect(titles.some(title => title.includes('E2E_UI'))).toBe(true)
    expect(titles).not.toContain(hiddenTitle)
  })

  test('14 parent portal API hides same-class elective notification for unenrolled student', async () => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const hiddenTitle = `E2E hidden elective notice ${Date.now()}`
    const visibleTitle = `E2E visible class notice ${Date.now()}`
    const hidden = await apiStatus('/api/notifications', {
      method: 'POST',
      token: teacherToken,
      body: {
        title: hiddenTitle,
        content: 'same class elective notification should stay hidden from parent code user',
        content_format: 'plain',
        priority: 'normal',
        class_id: s.class_id_1,
        subject_id: s.course_elective_id
      }
    })
    expect(hidden.status).toBe(200)
    const visible = await apiStatus('/api/notifications', {
      method: 'POST',
      token: teacherToken,
      body: {
        title: visibleTitle,
        content: 'class-only notification remains visible to parent code user',
        content_format: 'plain',
        priority: 'normal',
        class_id: s.class_id_1
      }
    })
    expect(visible.status).toBe(200)

    const parentNotices = await apiStatus(`/api/parent/notifications/${s.parent_code}?page_size=100`)
    expect(parentNotices.status).toBe(200)
    const titles = JSON.parse(parentNotices.text).notifications.map(row => row.title)
    expect(titles).toContain(visibleTitle)
    expect(titles).not.toContain(hiddenTitle)
  })
})
