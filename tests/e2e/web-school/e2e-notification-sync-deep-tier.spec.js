/**
 * Twenty-four deeper Playwright checks motivated by residual risks after `e2e-notification-header-sync-tier.spec.js`:
 *
 * - Admin **`notificationSyncParams === null`** uses global sync (must match list aggregates).
 * - Teacher/student **course context** vs **orphan localStorage** / **deep links** / **rapid switching**.
 * - **UI convergence lag** (badge vs API), **visibility-gated polling**, **viewport** stress.
 * - **Concurrent API writes** + **delete-under-load** (SQLite E2E harness).
 *
 * Run incrementally only this file:
 *   cd <REPO_ROOT>/apps/web/school && CI=1 E2E_PYTHON=<python> E2E_DEV_SEED_TOKEN=<seed> \
 *     npx playwright test e2e-notification-sync-deep-tier.spec.js --project=chromium
 */
const { expect, test } = require('@playwright/test')
const {
  login,
  obtainAccessToken,
  apiPostJson,
  apiGetJson,
  apiDelete,
  apiPutJson,
  clickCourseSwitcherOption
} = require('./future-advanced-coverage-helpers.cjs')
const { resetE2eScenario, enterSeededRequiredCourse } = require('./fixtures.cjs')

function scenario() {
  const { loadE2eScenario } = require('./fixtures.cjs')
  return loadE2eScenario()
}

function apiBase() {
  return (process.env.E2E_API_URL || 'http://127.0.0.1:8012').replace(/\/$/, '')
}

async function fetchStatus(method, pathname, { token, body } = {}) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body == null ? {} : { 'Content-Type': 'application/json' })
    },
    body: body == null ? undefined : JSON.stringify(body)
  })
  return res.status
}

async function triggerHeaderPoll(page) {
  await page.evaluate(() => {
    window.dispatchEvent(new Event('focus'))
  })
}

async function badgeContentLocator(page) {
  return page.locator('[data-testid="header-notification-badge"] .el-badge__content').first()
}

async function linkRequiredCourseToSecondClass(s, token) {
  await apiPutJson(`/api/subjects/${s.course_required_id}`, token, {
    class_links: [
      { class_id: s.class_id_1, enrollment_mode: 'all_in_class' },
      { class_id: s.class_id_2, enrollment_mode: 'all_in_class' }
    ]
  })
}

async function courseNameById(token, courseId) {
  const courses = await apiGetJson('/api/subjects', token)
  const row = Array.isArray(courses) ? courses.find(item => Number(item.id) === Number(courseId)) : null
  if (!row) {
    throw new Error(`course ${courseId} not visible`)
  }
  return row.name
}

test.describe('E2E notification sync deep tier (24 cases)', () => {
  test.describe.configure({ timeout: 120_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e seed; run globalSetup with E2E_DEV_SEED_TOKEN')
    }
  })

  test('01 admin global sync-status totals match notifications list footer counts', async () => {
    const s = scenario()
    const adminTok = await obtainAccessToken(s.admin.username, s.admin.password)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_ADM_G1_${s.suffix}_${Date.now()}`,
      content: 'g1',
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })

    const list = await apiGetJson('/api/notifications?page=1&page_size=20', adminTok)
    const sync = await apiGetJson('/api/notifications/sync-status', adminTok)
    expect(Number(sync.total)).toBe(Number(list.total))
    expect(Number(sync.unread_count)).toBe(Number(list.unread_count))
  })

  test('02 teacher header badge aligns with course-scoped sync after staff home entry', async ({ page }) => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    await login(page, s.teacher_own.username, s.password_teacher_student)
    await page.goto('/students', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(page.getByTestId('header-course-switch')).toBeVisible({ timeout: 20000 })

    const reqLabel = `E2E必修课_${s.suffix}`
    await clickCourseSwitcherOption(page, reqLabel)
    await page.waitForURL(/\/students/)

    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_TCH_HDR_${s.suffix}_${Date.now()}`,
      content: 'tch',
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })

    await triggerHeaderPoll(page)
    const sync = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, teacherTok)
    await expect
      .poll(
        async () => {
          const txt = await (await badgeContentLocator(page)).innerText().catch(() => '')
          const n = Number.parseInt(`${txt}`.trim(), 10)
          return Number.isFinite(n) && n === sync.unread_count
        },
        { timeout: 25_000 }
      )
      .toBe(true)
  })

  test('03 student notifications deep-link: badge converges after API-unread exists', async ({ page }) => {
    const s = scenario()
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_DL_${s.suffix}_${Date.now()}`,
      content: 'deep',
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })

    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.goto('/notifications', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(page).toHaveURL(/\/notifications/, { timeout: 20000 })

    const sync = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
    expect(sync.unread_count).toBeGreaterThanOrEqual(1)

    await triggerHeaderPoll(page)
    await expect
      .poll(async () => {
        const txt = await (await badgeContentLocator(page)).innerText().catch(() => '')
        const n = Number.parseInt(`${txt}`.trim(), 10)
        return n === sync.unread_count
      })
      .toBe(true)
  })

  test('04 corrupt selected_course localStorage is healed after entering seeded course', async ({ page }) => {
    const s = scenario()
    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.evaluate(() => {
      localStorage.setItem('selected_course', '{"id":999999,"name":"ghost"}')
    })
    await enterSeededRequiredCourse(page, s.suffix)
    const fixed = await page.evaluate(() => JSON.parse(localStorage.getItem('selected_course') || 'null'))
    expect(fixed).toBeTruthy()
    expect(String(fixed.id)).toBe(String(s.course_required_id))
  })

  test('05 rapid concurrent teacher publishes: student badge matches sync-status', async ({ page }) => {
    const s = scenario()
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)

    const ts = Date.now()
    await Promise.all([
      apiPostJson('/api/notifications', teacherTok, {
        title: `E2E_RC_A_${s.suffix}_${ts}`,
        content: 'a',
        class_id: s.class_id_1,
        subject_id: s.course_required_id
      }),
      apiPostJson('/api/notifications', teacherTok, {
        title: `E2E_RC_B_${s.suffix}_${ts}`,
        content: 'b',
        class_id: s.class_id_1,
        subject_id: s.course_required_id
      }),
      apiPostJson('/api/notifications', teacherTok, {
        title: `E2E_RC_C_${s.suffix}_${ts}`,
        content: 'c',
        class_id: s.class_id_1,
        subject_id: s.course_required_id
      })
    ])

    await triggerHeaderPoll(page)
    await expect
      .poll(async () => {
        const sync = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
        const txt = await (await badgeContentLocator(page)).innerText()
        const n = Number.parseInt(`${txt}`.trim(), 10)
        return n === sync.unread_count && sync.unread_count >= 3
      })
      .toBe(true)
  })

  test('06 teacher title PUT lowers unread student count when titles were unread-only signal', async ({
    page
  }) => {
    const s = scenario()
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)

    const row = await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_PUT_${s.suffix}_${Date.now()}`,
      content: 'orig',
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })

    await triggerHeaderPoll(page)
    await apiPutJson(`/api/notifications/${row.id}`, teacherTok, { title: `${row.title}_renamed` })

    await triggerHeaderPoll(page)
    const sync = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
    await expect
      .poll(async () => {
        const txt = await (await badgeContentLocator(page)).innerText().catch(() => '')
        const n = Number.parseInt(`${txt}`.trim(), 10)
        return n === sync.unread_count
      })
      .toBe(true)
  })

  test('07 mark-all-read then new publish: badge returns', async ({ page }) => {
    const s = scenario()
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)

    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_MAR_${s.suffix}_${Date.now()}`,
      content: 'mar',
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })
    await triggerHeaderPoll(page)

    const markUrl = new URL(`${apiBase()}/api/notifications/mark-all-read`)
    markUrl.searchParams.set('subject_id', String(s.course_required_id))
    const mar = await fetch(markUrl.toString(), {
      method: 'POST',
      headers: { Authorization: `Bearer ${studentTok}` }
    })
    expect(mar.status).toBe(200)

    await triggerHeaderPoll(page)
    await expect(page.locator('[data-testid="header-notification-badge"] .el-badge__content')).toHaveCount(0)

    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_AFTER_${s.suffix}_${Date.now()}`,
      content: 'after',
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })
    await triggerHeaderPoll(page)
    await expect(await badgeContentLocator(page)).toBeVisible({ timeout: 20000 })
  })

  test('08 cold reload on course-home picks up unread via onMounted poll (no manual focus)', async ({
    page
  }) => {
    const s = scenario()
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)

    const markUrl = new URL(`${apiBase()}/api/notifications/mark-all-read`)
    markUrl.searchParams.set('subject_id', String(s.course_required_id))
    await fetch(markUrl.toString(), { method: 'POST', headers: { Authorization: `Bearer ${studentTok}` } })

    await triggerHeaderPoll(page)
    await expect
      .poll(async () => {
        const sync = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
        const count = await page.locator('[data-testid="header-notification-badge"] .el-badge__content').count()
        return sync.unread_count === 0 && count === 0
      })
      .toBe(true)

    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_RELOAD_${s.suffix}_${Date.now()}`,
      content: 'reload-path',
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })

    await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 })

    const sync = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
    expect(sync.unread_count).toBeGreaterThanOrEqual(1)

    await expect
      .poll(
        async () => {
          const txt = await (await badgeContentLocator(page)).innerText().catch(() => '')
          const n = Number.parseInt(`${txt}`.trim(), 10)
          return n === sync.unread_count
        },
        { timeout: 25_000 }
      )
      .toBe(true)
  })

  test('09 mobile viewport: header badge still renders after unread publish', async ({ page }) => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    await page.setViewportSize({ width: 390, height: 844 })
    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)

    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_MOB_${s.suffix}_${Date.now()}`,
      content: 'mob',
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })

    await triggerHeaderPoll(page)
    await expect(await badgeContentLocator(page)).toBeVisible({ timeout: 20000 })
  })

  test('10 student GET sync-status with alien subject_id returns 403', async () => {
    const s = scenario()
    const stTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const status = await fetchStatus('GET', `/api/notifications/sync-status?subject_id=${s.course_orphan_id}`, {
      token: stTok
    })
    expect(status).toBe(403)
  })

  test('11 teacher-targeted notification does not inflate student scoped unread', async ({ page }) => {
    const s = scenario()
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    await linkRequiredCourseToSecondClass(s, teacherTok)

    const before = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)

    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_TGT_${s.suffix}_${Date.now()}`,
      content: 'self-target',
      class_id: s.class_id_1,
      subject_id: s.course_required_id,
      target_user_id: s.teacher_user_id
    })

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)

    await triggerHeaderPoll(page)
    const after = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
    expect(after.unread_count).toBe(before.unread_count)

    const txt = await page.evaluate(async () => {
      const el = document.querySelector('[data-testid="header-notification-badge"] .el-badge__content')
      return el ? el.textContent : ''
    })
    const n = Number.parseInt(`${txt}`.trim(), 10)
    expect(Number.isFinite(n) ? n : 0).toBe(after.unread_count)
  })

  test('12 other-teacher course notification is invisible in teacher_own scoped sync', async () => {
    const s = scenario()
    const ownTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const otherTok = await obtainAccessToken(s.teacher_other.username, s.password_teacher_student)

    await apiPostJson('/api/notifications', otherTok, {
      title: `E2E_OTH_${s.suffix}_${Date.now()}`,
      content: 'other',
      class_id: s.class_id_2,
      subject_id: s.course_other_teacher_id
    })

    const sync = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, ownTok)
    const list = await apiGetJson(
      `/api/notifications?subject_id=${s.course_required_id}&page=1&page_size=50`,
      ownTok
    )
    expect(sync.total).toBe(list.total)
    expect((list.data || []).every(row => !`${row.title || ''}`.includes(`E2E_OTH_${s.suffix}`))).toBe(true)
  })

  test('13 flip course switch twice: badge reflects last selected course unread', async ({ page }) => {
    const s = scenario()
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    await apiPostJson(`/api/subjects/${s.course_elective_id}/student-self-enroll`, studentTok, {}).catch(() => {})

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)

    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_FLIP_REQ_${s.suffix}_${Date.now()}`,
      content: 'r',
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })
    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_FLIP_ELC_${s.suffix}_${Date.now()}`,
      content: 'e',
      class_id: s.class_id_1,
      subject_id: s.course_elective_id
    })

    const flip = async courseLabel => {
      await clickCourseSwitcherOption(page, courseLabel)
      await page.waitForURL(/\/course-home|\/courses/)
      await triggerHeaderPoll(page)
    }

    await flip(`E2E选修课_${s.suffix}`)
    let sync = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_elective_id}`, studentTok)
    await expect
      .poll(async () => {
        const t = await (await badgeContentLocator(page)).innerText()
        return Number.parseInt(`${t}`.trim(), 10) === sync.unread_count
      })
      .toBe(true)

    await flip(`E2E必修课_${s.suffix}`)
    sync = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
    await expect
      .poll(async () => {
        const t = await (await badgeContentLocator(page)).innerText()
        return Number.parseInt(`${t}`.trim(), 10) === sync.unread_count
      })
      .toBe(true)
  })

  test('14 notifications page load does not 500 when teacher deletes row mid-flight', async ({ page }) => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    const row = await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_DELPG_${s.suffix}_${Date.now()}`,
      content: 'x',
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)

    const navigated = page.waitForURL(/\/notifications/, { timeout: 30000 })
    await page.goto('/notifications', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await navigated

    await apiDelete(`/api/notifications/${row.id}`, teacherTok)

    await expect(page.getByRole('heading', { name: /通知中心|閫氱煡/ })).toBeVisible({ timeout: 20000 })
    await triggerHeaderPoll(page)
    await expect(page.locator('body')).toBeVisible()
  })

  test('15 broadcast null-subject notice appears in student course-scoped sync-status', async ({ page }) => {
    const s = scenario()
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_BC_${s.suffix}_${Date.now()}`,
      content: 'broadcast',
      class_id: s.class_id_1,
      subject_id: null
    })

    const sync = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
    expect(sync.unread_count).toBeGreaterThanOrEqual(1)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)
    await triggerHeaderPoll(page)

    await expect
      .poll(async () => {
        const cur = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
        const t = await (await badgeContentLocator(page)).innerText().catch(() => '')
        const n = Number.parseInt(`${t}`.trim(), 10)
        return n === cur.unread_count
      })
      .toBe(true)
  })

  test('16 student header badge ignores other-class broadcast on required course scope', async ({ page }) => {
    const s = scenario()
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    await linkRequiredCourseToSecondClass(s, teacherTok)

    const before = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_FOREIGN_CLASS_${s.suffix}_${Date.now()}`,
      content: 'foreign-class-broadcast',
      class_id: s.class_id_2,
      subject_id: null
    })

    const after = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
    expect(after.unread_count).toBe(before.unread_count)
    expect(after.total).toBe(before.total)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)
    await triggerHeaderPoll(page)

    if (after.unread_count === 0) {
      await expect(page.locator('[data-testid="header-notification-badge"] .el-badge__content')).toHaveCount(0)
    } else {
      await expect
        .poll(async () => {
          const txt = await (await badgeContentLocator(page)).innerText().catch(() => '')
          return Number.parseInt(`${txt}`.trim(), 10)
        })
        .toBe(after.unread_count)
    }
  })

  test('17 student stale selected_course cache cannot make other-class broadcast appear in badge', async ({
    page
  }) => {
    const s = scenario()
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    await linkRequiredCourseToSecondClass(s, teacherTok)

    const before = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_STALE_FOREIGN_${s.suffix}_${Date.now()}`,
      content: 'stale-cache-foreign-class',
      class_id: s.class_id_2,
      subject_id: null
    })

    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.evaluate(courseId => {
      localStorage.setItem('selected_course', JSON.stringify({ id: courseId, name: 'stale required course' }))
    }, s.course_required_id)
    await page.goto('/course-home', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await triggerHeaderPoll(page)

    const after = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
    expect(after.total).toBe(before.total)
    expect(after.unread_count).toBe(before.unread_count)
    if (after.unread_count === 0) {
      await expect(page.locator('[data-testid="header-notification-badge"] .el-badge__content')).toHaveCount(0)
    } else {
      await expect
        .poll(async () => {
          const txt = await (await badgeContentLocator(page)).innerText().catch(() => '')
          return Number.parseInt(`${txt}`.trim(), 10)
        })
        .toBe(after.unread_count)
    }
  })

  test('18 teacher course badge still includes all class broadcasts linked to assigned course', async ({ page }) => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    await linkRequiredCourseToSecondClass(s, teacherTok)
    const requiredCourseName = await courseNameById(teacherTok, s.course_required_id)

    const before = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, teacherTok)
    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_TEACHER_ALL_LINKED_${s.suffix}_${Date.now()}`,
      content: 'teacher sees whole course broadcast scope',
      class_id: s.class_id_2,
      subject_id: null
    })
    const after = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, teacherTok)
    expect(after.unread_count).toBe(before.unread_count + 1)
    expect(after.total).toBe(before.total + 1)

    await login(page, s.teacher_own.username, s.password_teacher_student)
    await page.goto('/students', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await clickCourseSwitcherOption(page, requiredCourseName)
    await triggerHeaderPoll(page)

    await expect
      .poll(async () => {
        const txt = await (await badgeContentLocator(page)).innerText().catch(() => '')
        return Number.parseInt(`${txt}`.trim(), 10)
      })
      .toBe(after.unread_count)
  })

  test('19 teacher global broadcast attempt does not increase unrelated student header badge', async ({
    page
  }) => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const before = await apiGetJson('/api/notifications/sync-status', studentTok)

    const status = await fetchStatus('POST', '/api/notifications', {
      token: teacherTok,
      body: {
        title: `E2E_TEACHER_GLOBAL_DENY_${s.suffix}_${Date.now()}`,
        content: 'teacher global should be rejected',
        class_id: null,
        subject_id: null
      }
    })
    expect(status).toBe(403)

    const after = await apiGetJson('/api/notifications/sync-status', studentTok)
    expect(after.total).toBe(before.total)
    expect(after.unread_count).toBe(before.unread_count)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)
    await triggerHeaderPoll(page)
    if (after.unread_count === 0) {
      await expect(page.locator('[data-testid="header-notification-badge"] .el-badge__content')).toHaveCount(0)
    } else {
      await expect
        .poll(async () => {
          const txt = await (await badgeContentLocator(page)).innerText().catch(() => '')
          return Number.parseInt(`${txt}`.trim(), 10)
        })
        .toBe(after.unread_count)
    }
  })

  test('20 admin global broadcast reaches student header badge', async ({ page }) => {
    const s = scenario()
    const adminTok = await obtainAccessToken(s.admin.username, s.admin.password)
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const before = await apiGetJson('/api/notifications/sync-status', studentTok)

    await apiPostJson('/api/notifications', adminTok, {
      title: `E2E_ADMIN_GLOBAL_${s.suffix}_${Date.now()}`,
      content: 'admin global broadcast',
      class_id: null,
      subject_id: null
    })
    const after = await apiGetJson('/api/notifications/sync-status', studentTok)
    expect(after.total).toBe(before.total + 1)
    expect(after.unread_count).toBe(before.unread_count + 1)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)
    await triggerHeaderPoll(page)
    await expect
      .poll(async () => {
        const txt = await (await badgeContentLocator(page)).innerText().catch(() => '')
        return Number.parseInt(`${txt}`.trim(), 10)
      })
      .toBe(after.unread_count)
  })

  test('21 teacher cannot target another teacher user from course notification API', async ({ page }) => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const otherTok = await obtainAccessToken(s.teacher_other.username, s.password_teacher_student)
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const otherTeacher = await apiGetJson('/api/auth/me', otherTok)
    const before = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)

    const status = await fetchStatus('POST', '/api/notifications', {
      token: teacherTok,
      body: {
        title: `E2E_TARGET_USER_DENY_${s.suffix}_${Date.now()}`,
        content: 'teacher must not target another teacher',
        class_id: s.class_id_1,
        subject_id: s.course_required_id,
        target_user_id: otherTeacher.id
      }
    })
    expect(status).toBe(403)

    const after = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
    expect(after.total).toBe(before.total)
    expect(after.unread_count).toBe(before.unread_count)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)
    await triggerHeaderPoll(page)
    if (after.unread_count === 0) {
      await expect(page.locator('[data-testid="header-notification-badge"] .el-badge__content')).toHaveCount(0)
    } else {
      await expect
        .poll(async () => {
          const txt = await (await badgeContentLocator(page)).innerText().catch(() => '')
          return Number.parseInt(`${txt}`.trim(), 10)
        })
        .toBe(after.unread_count)
    }
  })

  test('22 teacher notification composer posts current course scope not global', async ({ page }) => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const title = `E2E_UI_SCOPED_${s.suffix}_${Date.now()}`
    let observedPayload = null

    await login(page, s.teacher_own.username, s.password_teacher_student)
    await page.goto('/students', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(page.getByTestId('header-course-switch')).toBeVisible({ timeout: 20000 })
    await clickCourseSwitcherOption(page, await courseNameById(teacherTok, s.course_required_id))
    await page.goto('/notifications', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(page).toHaveURL(/\/notifications$/, { timeout: 20000 })

    const responsePromise = page.waitForResponse(resp => {
      const req = resp.request()
      if (!resp.url().includes('/api/notifications') || req.method() !== 'POST') return false
      observedPayload = JSON.parse(req.postData() || '{}')
      return true
    })
    await page.getByRole('button', { name: /发布通知/ }).click()
    const dialog = page.locator('.el-dialog').filter({ hasText: '发布通知' }).last()
    await expect(dialog).toBeVisible({ timeout: 10000 })
    await dialog.getByLabel(/通知标题/).fill(title)
    await dialog.locator('textarea').first().fill('composer scope guard')
    await dialog.getByRole('button', { name: /保存/ }).click()
    const response = await responsePromise

    expect(response.status()).toBe(200)
    expect(Number(observedPayload.subject_id)).toBe(Number(s.course_required_id))
    expect(Number(observedPayload.class_id)).toBe(Number(s.class_id_1))

    const list = await apiGetJson(
      `/api/notifications?subject_id=${s.course_required_id}&page=1&page_size=100`,
      teacherTok
    )
    const row = (list.data || []).find(item => item.title === title)
    expect(row).toBeTruthy()
    expect(Number(row.subject_id)).toBe(Number(s.course_required_id))
    expect(Number(row.class_id)).toBe(Number(s.class_id_1))
  })

  test('23 explicit null target_student_id clearing updates course badge without changing foreign course sync', async ({
    page
  }) => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const otherTeacherTok = await obtainAccessToken(s.teacher_other.username, s.password_teacher_student)
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const before = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
    const otherBefore = await apiGetJson(
      `/api/notifications/sync-status?subject_id=${s.course_other_teacher_id}`,
      otherTeacherTok
    )

    const row = await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_CLEAR_TARGET_${s.suffix}_${Date.now()}`,
      content: 'targeted then cleared',
      class_id: s.class_id_1,
      subject_id: s.course_required_id,
      target_student_id: s.student_plain.student_row_id
    })

    await apiPutJson(`/api/notifications/${row.id}`, teacherTok, { target_student_id: null })
    const detail = await apiGetJson(`/api/notifications/${row.id}`, teacherTok)
    expect(detail.target_student_id).toBeFalsy()

    const after = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
    const otherAfter = await apiGetJson(
      `/api/notifications/sync-status?subject_id=${s.course_other_teacher_id}`,
      otherTeacherTok
    )
    expect(after.total).toBe(before.total + 1)
    expect(after.unread_count).toBe(before.unread_count + 1)
    expect(otherAfter.total).toBe(otherBefore.total)
    expect(otherAfter.unread_count).toBe(otherBefore.unread_count)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)
    await triggerHeaderPoll(page)
    await expect
      .poll(async () => {
        const txt = await (await badgeContentLocator(page)).innerText().catch(() => '')
        return Number.parseInt(`${txt}`.trim(), 10)
      })
      .toBe(after.unread_count)
  })

  test('24 switching target_student_id to target_user_id without explicit clear is rejected', async ({
    page
  }) => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const before = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
    const row = await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_SWITCH_TARGET_DENY_${s.suffix}_${Date.now()}`,
      content: 'must remain student-targeted',
      class_id: s.class_id_1,
      subject_id: s.course_required_id,
      target_student_id: s.student_plain.student_row_id
    })

    const status = await fetchStatus('PUT', `/api/notifications/${row.id}`, {
      token: teacherTok,
      body: { target_user_id: s.teacher_user_id }
    })
    expect(status).toBe(400)

    const detail = await apiGetJson(`/api/notifications/${row.id}`, teacherTok)
    expect(Number(detail.target_student_id)).toBe(Number(s.student_plain.student_row_id))
    expect(detail.target_user_id).toBeFalsy()
    const after = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
    expect(after.total).toBe(before.total + 1)
    expect(after.unread_count).toBe(before.unread_count + 1)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)
    await triggerHeaderPoll(page)
    await expect
      .poll(async () => {
        const txt = await (await badgeContentLocator(page)).innerText().catch(() => '')
        return Number.parseInt(`${txt}`.trim(), 10)
      })
      .toBe(after.unread_count)
  })
})
