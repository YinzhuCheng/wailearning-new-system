const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario, enterSeededRequiredCourse } = require('./fixtures.cjs')
const { apiFindUserIdByUsername, apiGetJson, apiPostJson, login, obtainAccessToken } = require('./future-advanced-coverage-helpers.cjs')

const scenario = () => loadE2eScenario()

async function openRosterAs(page, s, account) {
  await login(page, account.username, account.password)
  await page.goto('/courses')
  await enterSeededRequiredCourse(page, s.suffix)
  await page.goto('/students', { waitUntil: 'domcontentloaded', timeout: 60000 })
  await expect(page.getByRole('heading', { name: /学生|花名册/ })).toBeVisible({ timeout: 20000 })
}

async function openTeacherRoster(page, s) {
  await openRosterAs(page, s, s.teacher_own)
}

async function rosterRowForStudent(page, student) {
  const row = page.locator('tr').filter({ hasText: student.username }).first()
  await expect(row).toBeVisible({ timeout: 30000 })
  return row
}

async function openStudentActionMenuIn(page, row) {
  await row.getByTestId('student-action-menu-button').click()
  await expect(page.locator('[data-testid="student-action-menu-recent-posts"]:visible')).toBeVisible({
    timeout: 10000
  })
}

async function clickVisibleStudentAction(page, testId) {
  const visibleMenu = page
    .locator('.el-popper')
    .filter({ has: page.locator(`[data-testid="${testId}"]`) })
    .filter({ visible: true })
    .last()
  await expect(visibleMenu).toBeVisible({ timeout: 10000 })
  const item = visibleMenu.locator(`[data-testid="${testId}"]`).last()
  await expect(item).toBeVisible({ timeout: 10000 })
  await page.waitForTimeout(100)
  await item.click({ force: true })
}

test.describe('E2E recent posts + student action shortcuts', () => {
  test.describe.configure({ timeout: 180_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e scenario; set E2E_DEV_SEED_TOKEN')
    }
  })

  test('teacher roster action opens a bound student recent-posts feed', async ({ page }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const studentUserId = await apiFindUserIdByUsername(adminToken, s.student_plain.username)

    await openTeacherRoster(page, s)
    const row = await rosterRowForStudent(page, s.student_plain)
    await openStudentActionMenuIn(page, row)
    await clickVisibleStudentAction(page, 'student-action-menu-recent-posts')

    await expect(page).toHaveURL(new RegExp(`/recent-posts/users/${studentUserId}$`), { timeout: 20000 })
    await expect(page.locator('.recent-posts-page')).toBeVisible({ timeout: 20000 })
    await expect(page.getByText(s.student_plain.username).first()).toBeVisible({ timeout: 20000 })
  })

  test('teacher roster action opens selected student homework status in the active course', async ({ page }) => {
    const s = scenario()
    await openTeacherRoster(page, s)
    const row = await rosterRowForStudent(page, s.student_plain)
    await openStudentActionMenuIn(page, row)
    await clickVisibleStudentAction(page, 'student-action-menu-homework-status')

    await expect(page).toHaveURL(new RegExp(`/homework/students\\?student_id=${s.student_plain.student_row_id}$`), {
      timeout: 20000
    })
    await expect(page.getByRole('heading', { name: '学生作业一览' })).toBeVisible({ timeout: 20000 })
    await expect(page.getByText(s.student_plain.username).first()).toBeVisible({ timeout: 20000 })
    await expect(page.locator('.student-hw-page')).toBeVisible({ timeout: 20000 })
  })

  test('student discussion avatar exposes the same recent-posts and homework-status actions', async ({ page }) => {
    const s = scenario()
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    await apiPostJson('/api/discussions', studentToken, {
      target_type: 'homework',
      target_id: s.homework_id,
      subject_id: s.course_required_id,
      class_id: s.class_id_1,
      body: `avatar-action-${s.suffix}-${Date.now()}`,
      body_format: 'plain',
      linked_targets: [],
      invoke_llm: false
    })

    await login(page, s.teacher_own.username, s.teacher_own.password)
    await page.goto('/courses')
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto(`/homework/${s.homework_id}/submissions`, { waitUntil: 'domcontentloaded', timeout: 60000 })

    const row = page.locator('.discussion-row').filter({ hasText: 'avatar-action-' }).last()
    await expect(row).toBeVisible({ timeout: 30000 })
    await row.getByTestId('discussion-author-student-action-trigger').click()
    await expect(page.locator('[data-testid="student-action-menu-recent-posts"]:visible')).toBeVisible({
      timeout: 10000
    })
    await expect(page.locator('[data-testid="student-action-menu-homework-status"]:visible')).toBeVisible({
      timeout: 10000
    })
    await clickVisibleStudentAction(page, 'student-action-menu-homework-status')

    await expect(page).toHaveURL(new RegExp(`/homework/students\\?student_id=${s.student_plain.student_row_id}$`), {
      timeout: 20000
    })
    await expect(page.getByRole('heading', { name: '学生作业一览' })).toBeVisible({ timeout: 20000 })
  })
})

test.describe('E2E recent posts + student action shortcut follow-ups', () => {
  test.describe.configure({ timeout: 180_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e scenario; set E2E_DEV_SEED_TOKEN')
    }
  })

  test('teacher roster shortcut remains stable after recent-posts route roundtrip and reload', async ({ page }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const studentUserId = await apiFindUserIdByUsername(adminToken, s.student_plain.username)

    await openTeacherRoster(page, s)
    let row = await rosterRowForStudent(page, s.student_plain)
    await openStudentActionMenuIn(page, row)
    await clickVisibleStudentAction(page, 'student-action-menu-recent-posts')
    await expect(page).toHaveURL(new RegExp(`/recent-posts/users/${studentUserId}$`), { timeout: 20000 })

    await page.goto('/students', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 })
    row = await rosterRowForStudent(page, s.student_plain)
    await openStudentActionMenuIn(page, row)
    await expect(page.locator('[data-testid="student-action-menu-homework-status"]:visible')).toBeVisible({
      timeout: 10000
    })
    await clickVisibleStudentAction(page, 'student-action-menu-homework-status')
    await expect(page).toHaveURL(new RegExp(`/homework/students\\?student_id=${s.student_plain.student_row_id}$`), {
      timeout: 20000
    })
  })

  test('admin global student shortcut exposes recent posts but not course-scoped homework status', async ({ page }) => {
    const s = scenario()

    await login(page, s.admin.username, s.admin.password)
    await page.goto(`/students?class_id=${s.class_id_1}`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    const row = await rosterRowForStudent(page, s.student_plain)
    await row.getByTestId('student-action-menu-button').click()

    await expect(page.locator('[data-testid="student-action-menu-recent-posts"]:visible')).toBeVisible({
      timeout: 10000
    })
    await expect(page.locator('[data-testid="student-action-menu-homework-status"]:visible')).toHaveCount(0)
  })

  test('admin student list keeps shortcut state after repeated student and user read pages', async ({ page }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const studentUserId = await apiFindUserIdByUsername(adminToken, s.student_plain.username)

    await login(page, s.admin.username, s.admin.password)
    await page.goto(`/students?class_id=${s.class_id_1}`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    let row = await rosterRowForStudent(page, s.student_plain)
    await row.getByTestId('student-action-menu-button').click()
    await expect(page.locator('[data-testid="student-action-menu-recent-posts"]:visible')).toBeVisible({
      timeout: 10000
    })
    await page.keyboard.press('Escape')

    for (let attempt = 0; attempt < 4; attempt += 1) {
      const [students, users] = await Promise.all([
        apiGetJson(`/api/students?class_id=${s.class_id_1}&page=1&page_size=1000`, adminToken),
        apiGetJson('/api/users', adminToken)
      ])
      expect(students.data.some(item => item.student_no === s.student_plain.username && item.bound_user_id === studentUserId)).toBe(true)
      expect(users.some(item => item.username === s.student_plain.username && item.student_id === s.student_plain.student_row_id)).toBe(true)
    }

    await page.goto(`/students?class_id=${s.class_id_1}`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    row = await rosterRowForStudent(page, s.student_plain)
    await row.getByTestId('student-action-menu-button').click()
    await clickVisibleStudentAction(page, 'student-action-menu-recent-posts')

    await expect(page).toHaveURL(new RegExp(`/recent-posts/users/${studentUserId}$`), { timeout: 20000 })
    await expect(page.locator('.recent-posts-page')).toBeVisible({ timeout: 20000 })
  })

  test('teacher can open homework status after rapid roster reads and recent-posts navigation', async ({ page }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const studentUserId = await apiFindUserIdByUsername(adminToken, s.student_plain.username)

    await openTeacherRoster(page, s)
    for (let attempt = 0; attempt < 3; attempt += 1) {
      await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 })
      const row = await rosterRowForStudent(page, s.student_plain)
      await openStudentActionMenuIn(page, row)
      await expect(page.locator('[data-testid="student-action-menu-homework-status"]:visible')).toBeVisible({
        timeout: 10000
      })
      await page.keyboard.press('Escape')
    }

    await page.goto(`/recent-posts/users/${studentUserId}`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(page).toHaveURL(new RegExp(`/recent-posts/users/${studentUserId}$`), { timeout: 20000 })

    await page.goto('/students', { waitUntil: 'domcontentloaded', timeout: 60000 })
    const row = await rosterRowForStudent(page, s.student_plain)
    await openStudentActionMenuIn(page, row)
    await clickVisibleStudentAction(page, 'student-action-menu-homework-status')

    await expect(page).toHaveURL(new RegExp(`/homework/students\\?student_id=${s.student_plain.student_row_id}$`), {
      timeout: 20000
    })
    await expect(page.locator('.student-hw-page')).toBeVisible({ timeout: 20000 })
  })
})
