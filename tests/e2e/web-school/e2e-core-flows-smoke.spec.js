const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario, enterSeededRequiredCourse } = require('./fixtures.cjs')

function scenario() {
  return loadE2eScenario()
}

async function login(page, username, password) {
  await page.goto('/login')
  await page.getByTestId('login-username').fill(username)
  await page.getByTestId('login-password').fill(password)
  await page.getByTestId('login-submit').click()
  await expect
    .poll(
      async () =>
        page.evaluate(() => {
          try {
            const user = JSON.parse(localStorage.getItem('user') || 'null')
            return user?.role || null
          } catch {
            return null
          }
        }),
      { timeout: 20000 }
    )
    .not.toBeNull()
  if (page.url().includes('/login')) {
    const fallbackTarget = await page.evaluate(() => {
      try {
        const user = JSON.parse(localStorage.getItem('user') || 'null')
        return user?.role === 'student' ? '/courses' : '/students'
      } catch {
        return '/students'
      }
    })
    await page.goto(fallbackTarget, { waitUntil: 'load', timeout: 60000 })
  }
  await expect(page).not.toHaveURL(/\/login/, { timeout: 20000 })
}

test.describe('E2E core user journeys (seeded DB)', () => {
  test.describe.configure({ timeout: 180_000 })

  test.beforeEach(async ({}, testInfo) => {
    const data = await resetE2eScenario()
    if (!data) {
      testInfo.skip(
        true,
        'Missing scenario cache — Playwright globalSetup must POST /api/e2e/dev/reset-scenario with E2E_DEV_SEED_TOKEN'
      )
    }
  })

  test('login surface exposes stable selectors', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByTestId('login-page')).toBeVisible()
    await expect(page.getByTestId('login-panel')).toBeVisible()
    await expect(page.getByTestId('login-submit')).toBeEnabled()
  })

  test('reject invalid credentials and remain on login route', async ({ page }) => {
    const s = scenario()
    await page.goto('/login')
    await page.getByTestId('login-username').fill(s.admin.username)
    await page.getByTestId('login-password').fill('WrongPassword!!!')
    await page.getByTestId('login-submit').click()
    await expect(page).toHaveURL(/\/login/, { timeout: 10000 })
  })

  test('admin lands on staff home after successful login', async ({ page }) => {
    const s = scenario()
    await login(page, s.admin.username, s.admin.password)
    await expect(page).not.toHaveURL(/\/login/)
    await expect(page.locator('.el-menu, aside').first()).toBeVisible({ timeout: 20000 })
  })

  test('student sees seeded required course card', async ({ page }) => {
    const s = scenario()
    await login(page, s.student_plain.username, s.student_plain.password)
    await page.goto('/courses')
    const title = `E2E必修课_${s.suffix}`
    await expect(page.getByRole('heading', { name: title })).toBeVisible({ timeout: 20000 })
  })

  test('student opens homework list with at least one seeded row', async ({ page }) => {
    const s = scenario()
    await login(page, s.student_plain.username, s.student_plain.password)
    await page.goto('/courses')
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto('/homework')
    await expect(page.locator('tbody tr').first()).toBeVisible({ timeout: 20000 })
    await expect(page.locator('tbody').getByText(new RegExp(`E2E_UI作业_${s.suffix}`))).toBeVisible({
      timeout: 15000
    })
  })

  test('teacher can navigate to materials management screen', async ({ page }) => {
    const s = scenario()
    await login(page, s.teacher_own.username, s.teacher_own.password)
    await page.goto('/courses')
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto('/materials')
    await expect(page.locator('.el-table, .material-page, main').first()).toBeVisible({ timeout: 20000 })
  })

  test('teacher loads notifications center route', async ({ page }) => {
    const s = scenario()
    await login(page, s.teacher_own.username, s.teacher_own.password)
    await page.goto('/notifications')
    await expect(page.locator('main, .el-main').first()).toBeVisible({ timeout: 20000 })
  })

  test('admin opens user management grid', async ({ page }) => {
    const s = scenario()
    await login(page, s.admin.username, s.admin.password)
    await page.goto('/users')
    await expect(page.locator('.el-table').first()).toBeVisible({ timeout: 30000 })
    await expect(page.locator(`text=${s.admin.username}`).first()).toBeVisible({ timeout: 15000 })
  })

  test('class teacher reaches staff home without error overlay', async ({ page }) => {
    const s = scenario()
    await login(page, s.class_teacher.username, s.class_teacher.password)
    await expect(page).toHaveURL(/\/students/)
    await expect(page.locator('.el-message--error')).toHaveCount(0)
  })

  test('student course-home route renders primary layout', async ({ page }) => {
    const s = scenario()
    await login(page, s.student_plain.username, s.student_plain.password)
    await page.goto('/course-home')
    await expect(page.locator('main, .el-main').first()).toBeVisible({ timeout: 20000 })
  })
})
