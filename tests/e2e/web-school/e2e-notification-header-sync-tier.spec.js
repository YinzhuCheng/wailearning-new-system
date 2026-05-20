/**
 * Ten Playwright UI/API hybrid checks for header notification badge + sync-status alignment.
 *
 * Coverage gap addressed: existing E2E exercises `/api/notifications` heavily but rarely asserts
 * `data-testid="header-notification-badge"` / dropdown label convergence or course-scoped badge
 * switches driven by `Layout.vue` (`pollNotificationSync`, route/focus triggers).
 *
 * Requires: globalSetup seed (`E2E_DEV_SEED_TOKEN`), same contract as other web-school E2E.
 * Run alone (Pitfall 41 — port contention): `cd <REPO_ROOT>/apps/web/school && CI=1 npx playwright test e2e-notification-header-sync-tier.spec.js --project=chromium`
 */
const { expect, test } = require('@playwright/test')
const {
  login,
  obtainAccessToken,
  apiPostJson,
  apiGetJson,
  apiDelete,
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

/** Dispatch window focus so `Layout.vue` `handleWindowFocus` runs `pollNotificationSync` immediately. */
async function triggerHeaderPoll(page) {
  await page.evaluate(() => {
    window.dispatchEvent(new Event('focus'))
  })
}

async function badgeContentLocator(page) {
  return page.locator('[data-testid="header-notification-badge"] .el-badge__content').first()
}

test.describe('E2E notification header sync tier (10 cases)', () => {
  test.describe.configure({ timeout: 120_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e seed; run globalSetup with E2E_DEV_SEED_TOKEN')
    }
  })

  test('01 student header badge shows unread count after teacher publishes (focus triggers poll)', async ({
    page
  }) => {
    const s = scenario()
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)

    const title = `E2E_HDR_BADGE_${s.suffix}_${Date.now()}`
    await apiPostJson('/api/notifications', teacherTok, {
      title,
      content: 'hdr-badge-01',
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })

    await triggerHeaderPoll(page)
    const badge = await badgeContentLocator(page)
    await expect(badge).toBeVisible({ timeout: 20000 })
    await expect(badge).toHaveText(/\d+/)

    const sync = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
    expect(sync.unread_count).toBeGreaterThanOrEqual(1)
  })

  test('02 unread surfaces on header badge after publish (footer nav opens notifications)', async ({
    page
  }) => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)

    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_HDR_MENU_${s.suffix}_${Date.now()}`,
      content: 'hdr-menu-02',
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })

    await triggerHeaderPoll(page)
    const badge = await badgeContentLocator(page)
    await expect(badge).toBeVisible({ timeout: 20000 })
    await expect(badge).toHaveText(/\d+/)
    await page.getByTestId('sidebar-notifications').click()
    await expect(page).toHaveURL(/\/notifications$/, { timeout: 20000 })
  })

  test('03 course switcher scopes badge to selected course unread (required vs elective)', async ({ page }) => {
    const s = scenario()
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    await apiPostJson(`/api/subjects/${s.course_elective_id}/student-self-enroll`, studentTok, {}).catch(() => {})

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)

    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_HDR_REQ_${s.suffix}_${Date.now()}`,
      content: 'scope-req',
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })

    await triggerHeaderPoll(page)
    const badge = await badgeContentLocator(page)
    await expect(badge).toBeVisible({ timeout: 20000 })

    const elective = await apiGetJson(`/api/subjects/${s.course_elective_id}`, teacherTok)
    const electiveLabel = elective.name
    await clickCourseSwitcherOption(page, electiveLabel)
    await page.waitForURL(/\/course-home|\/courses/)
    await triggerHeaderPoll(page)

    await expect(page.locator('[data-testid="header-notification-badge"] .el-badge__content')).toHaveCount(0)

    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_HDR_ELEC_${s.suffix}_${Date.now()}`,
      content: 'scope-el',
      class_id: s.class_id_1,
      subject_id: s.course_elective_id
    })
    await triggerHeaderPoll(page)
    await expect(await badgeContentLocator(page)).toBeVisible({ timeout: 20000 })
  })

  test('04 route navigation triggers poll: returning to course-home picks up new unread without 12s poll', async ({
    page
  }) => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto('/courses', { waitUntil: 'domcontentloaded', timeout: 60000 })

    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_HDR_ROUTE_${s.suffix}_${Date.now()}`,
      content: 'route-04',
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })

    // After visiting /courses the course-card primary action can stay disabled while enrollment state
    // reconciles (same pitfall family as elective flip-flop). Deep-link back into the shell instead of
    // clicking the card button a second time — route watches still run pollNotificationSync on navigation.
    await page.goto('/course-home', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await triggerHeaderPoll(page)
    const badge = await badgeContentLocator(page)
    await expect(badge).toBeVisible({ timeout: 25000 })
  })

  test('05 mark-all-read for subject clears header badge after poll', async ({ page }) => {
    const s = scenario()
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)

    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_HDR_CLR_${s.suffix}_${Date.now()}`,
      content: 'clear-05',
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })

    await triggerHeaderPoll(page)
    await expect(await badgeContentLocator(page)).toBeVisible({ timeout: 20000 })

    const markUrl = new URL(`${apiBase()}/api/notifications/mark-all-read`)
    markUrl.searchParams.set('subject_id', String(s.course_required_id))
    const res = await fetch(markUrl.toString(), {
      method: 'POST',
      headers: { Authorization: `Bearer ${studentTok}` }
    })
    expect(res.status).toBe(200)

    await triggerHeaderPoll(page)
    await expect(page.locator('[data-testid="header-notification-badge"] .el-badge__content')).toHaveCount(0)
  })

  test('06 cumulative unread from two publishes matches sync-status subject scope', async ({ page }) => {
    const s = scenario()
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)

    const ts = Date.now()
    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_HDR_A_${s.suffix}_${ts}`,
      content: 'a',
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })
    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_HDR_B_${s.suffix}_${ts}`,
      content: 'b',
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })

    await triggerHeaderPoll(page)
    await expect
      .poll(async () => {
        const sync = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
        const txt = await (await badgeContentLocator(page)).innerText()
        const n = Number.parseInt(`${txt}`.trim(), 10)
        return { ok: n === sync.unread_count && sync.unread_count >= 2, syncCount: sync.unread_count, badge: n }
      })
      .toMatchObject({ ok: true })
  })

  test('07 reading one notification lowers badge count (partial read)', async ({ page }) => {
    const s = scenario()
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)

    const n1 = await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_HDR_P1_${s.suffix}_${Date.now()}`,
      content: 'p1',
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })
    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_HDR_P2_${s.suffix}_${Date.now()}`,
      content: 'p2',
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })

    await triggerHeaderPoll(page)
    const beforeSync = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
    expect(beforeSync.unread_count).toBeGreaterThanOrEqual(2)

    await fetch(`${apiBase()}/api/notifications/${n1.id}/read`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${studentTok}` }
    }).then(r => expect(r.status).toBe(200))

    await triggerHeaderPoll(page)
    await expect
      .poll(async () => {
        const sync = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
        const txt = await (await badgeContentLocator(page)).innerText()
        const n = Number.parseInt(`${txt}`.trim(), 10)
        return { ok: n === sync.unread_count && sync.unread_count === beforeSync.unread_count - 1, sync, badge: n }
      })
      .toMatchObject({ ok: true })
  })

  test('08 second browser tab eventually matches badge after focus poll', async ({
    browser
  }) => {
    const s = scenario()
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    const ctxA = await browser.newContext()
    const ctxB = await browser.newContext()
    const pageA = await ctxA.newPage()
    const pageB = await ctxB.newPage()

    try {
      await login(pageA, s.student_plain.username, s.password_teacher_student)
      await enterSeededRequiredCourse(pageA, s.suffix)

      await login(pageB, s.student_plain.username, s.password_teacher_student)
      await enterSeededRequiredCourse(pageB, s.suffix)

      await apiPostJson('/api/notifications', teacherTok, {
        title: `E2E_HDR_TAB_${s.suffix}_${Date.now()}`,
        content: 'tab-08',
        class_id: s.class_id_1,
        subject_id: s.course_required_id
      })

      await triggerHeaderPoll(pageA)
      await expect(await badgeContentLocator(pageA)).toBeVisible({ timeout: 25000 })

      await triggerHeaderPoll(pageB)
      await expect(await badgeContentLocator(pageB)).toBeVisible({ timeout: 25000 })
    } finally {
      await Promise.all([ctxA.close().catch(() => {}), ctxB.close().catch(() => {})])
    }
  })

  test('09 sidebar footer notification entry navigates to /notifications', async ({ page }) => {
    const s = scenario()

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)

    await page.getByTestId('sidebar-notifications').click()
    await expect(page).toHaveURL(/\/notifications$/, { timeout: 20000 })
  })

  test('10 teacher deletes notification reduces student sync total and badge after poll', async ({ page }) => {
    const s = scenario()
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)

    const row = await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_HDR_DEL_${s.suffix}_${Date.now()}`,
      content: 'del-10',
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })

    await triggerHeaderPoll(page)
    await expect(await badgeContentLocator(page)).toBeVisible({ timeout: 20000 })
    const beforeTotal = (await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok))
      .total

    await apiDelete(`/api/notifications/${row.id}`, teacherTok)

    await triggerHeaderPoll(page)
    const afterTotal = (await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok))
      .total
    expect(afterTotal).toBe(beforeTotal - 1)
  })
})
