const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario } = require('./fixtures.cjs')
const { login, obtainAccessToken, apiGetJson, apiPostJson, apiPutJson } = require('./future-advanced-coverage-helpers.cjs')

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

test.describe('E2E red-team selected-course cache poison sample', () => {
  test.describe.configure({ timeout: 120_000 })

  test.beforeEach(async ({}, testInfo) => {
    const data = await resetE2eScenario()
    if (!data) {
      testInfo.skip(true, 'Missing e2e seed; run globalSetup with E2E_DEV_SEED_TOKEN')
    }
  })

  test('poisoned selected_course cache cannot expand student notification badge to another class broadcast', async ({
    page
  }) => {
    const s = scenario()
    const studentTok = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const teacherTok = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)

    await apiPutJson(`/api/subjects/${s.course_required_id}`, teacherTok, {
      class_links: [
        { class_id: s.class_id_1, enrollment_mode: 'all_in_class' },
        { class_id: s.class_id_2, enrollment_mode: 'all_in_class' }
      ]
    })

    const before = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
    await apiPostJson('/api/notifications', teacherTok, {
      title: `E2E_REDTEAM_POISON_${s.suffix}_${Date.now()}`,
      content: 'selected-course-cache-poison',
      class_id: s.class_id_2,
      subject_id: null
    })
    const after = await apiGetJson(`/api/notifications/sync-status?subject_id=${s.course_required_id}`, studentTok)
    expect(after.total).toBe(before.total)
    expect(after.unread_count).toBe(before.unread_count)

    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.evaluate(
      ({ courseId, classId }) => {
        localStorage.setItem(
          'selected_course',
          JSON.stringify({
            id: courseId,
            name: 'redteam poisoned selected_course',
            class_id: classId,
            course_type: 'required'
          })
        )
      },
      { courseId: s.course_required_id, classId: s.class_id_2 }
    )
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.goto('/course-home', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await triggerHeaderPoll(page)

    await expect.poll(() => badgeValue(page), { timeout: 25000 }).toBe(Math.min(before.unread_count, 99))
    await expect
      .poll(
        () =>
          page.evaluate(() => {
            const parsed = JSON.parse(localStorage.getItem('selected_course') || 'null')
            return parsed?.id || null
          }),
        { timeout: 15000 }
      )
      .toBe(s.course_required_id)
  })
})
