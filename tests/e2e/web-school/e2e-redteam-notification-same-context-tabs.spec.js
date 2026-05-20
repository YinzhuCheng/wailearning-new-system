const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario, enterSeededRequiredCourse } = require('./fixtures.cjs')
const { login, obtainAccessToken, apiGetJson, apiPostJson } = require('./future-advanced-coverage-helpers.cjs')

function scenario() {
  return loadE2eScenario()
}

async function triggerHeaderPoll(page) {
  await page.evaluate(() => {
    window.dispatchEvent(new Event('focus'))
  })
}

async function badgeValue(page) {
  const badge = page.locator('[data-testid="header-notification-badge"] .el-badge__content').first()
  if ((await badge.count()) === 0) {
    return 0
  }
  const text = `${await badge.innerText()}`.trim()
  return text === '99+' ? 99 : Number.parseInt(text, 10)
}

test.describe('E2E red-team same-context notification tabs sample', () => {
  test.describe.configure({ timeout: 120_000 })

  test.beforeEach(async ({}, testInfo) => {
    const data = await resetE2eScenario()
    if (!data) {
      testInfo.skip(true, 'Missing e2e seed; run globalSetup with E2E_DEV_SEED_TOKEN')
    }
  })

  test('same-storage second tab login does not break first tab notification auth or badge convergence', async ({
    browser
  }) => {
    const s = scenario()
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const ctx = await browser.newContext()
    const pageA = await ctx.newPage()
    const pageB = await ctx.newPage()

    try {
      await login(pageA, s.student_plain.username, s.password_teacher_student)
      await enterSeededRequiredCourse(pageA, s.suffix)
      const before = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)

      await login(pageB, s.student_plain.username, s.password_teacher_student)
      await enterSeededRequiredCourse(pageB, s.suffix)

      const meFromFirstTab = await pageA.evaluate(async () => {
        const token = localStorage.getItem('token')
        const res = await fetch('/api/auth/me', {
          headers: { Authorization: `Bearer ${token}` }
        })
        const body = await res.json().catch(() => null)
        return { status: res.status, role: body?.role || null }
      })
      expect(meFromFirstTab).toEqual({ status: 200, role: 'student' })

      await apiPostJson('/api/notifications', teacherTok, {
        title: `E2E_REDTEAM_SAME_CTX_${s.suffix}_${Date.now()}`,
        content: 'same-context-tab-redteam',
        class_id: s.class_id_1,
        subject_id: s.course_required_id
      })

      let after = null
      await expect
        .poll(
          async () => {
            after = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
            return after.unread_count
          },
          { timeout: 20000 }
        )
        .toBe(before.unread_count + 1)

      await triggerHeaderPoll(pageA)
      await triggerHeaderPoll(pageB)
      const expectedBadge = Math.min(Number(after?.unread_count || before.unread_count + 1), 99)

      await expect.poll(() => badgeValue(pageA), { timeout: 25000 }).toBe(expectedBadge)
      await expect.poll(() => badgeValue(pageB), { timeout: 25000 }).toBe(expectedBadge)
    } finally {
      await ctx.close().catch(() => {})
    }
  })
})
