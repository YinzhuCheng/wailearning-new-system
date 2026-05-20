const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario } = require('./fixtures.cjs')

function scenario() {
  return loadE2eScenario()
}

test.describe('E2E red-team auth login rollback sample', () => {
  test.describe.configure({ timeout: 90_000 })

  test.beforeEach(async ({}, testInfo) => {
    const data = await resetE2eScenario()
    if (!data) {
      testInfo.skip(true, 'Missing e2e seed; run globalSetup with E2E_DEV_SEED_TOKEN')
    }
  })

  test('auth bootstrap failure after successful login leaves no half-authenticated browser state', async ({ page }) => {
    const s = scenario()
    let interceptedMe = false

    await page.route('**/api/auth/me', async route => {
      if (!interceptedMe) {
        interceptedMe = true
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'redteam forced current-user bootstrap failure' })
        })
        return
      }
      await route.continue()
    })

    await page.goto('/login', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.getByTestId('login-username').fill(s.student_plain.username)
    await page.getByTestId('login-password').fill(s.password_teacher_student)
    await page.getByTestId('login-submit').click()

    await expect.poll(() => interceptedMe, { timeout: 15000 }).toBe(true)
    await expect(page).toHaveURL(/\/login/, { timeout: 15000 })
    await expect
      .poll(
        () =>
          page.evaluate(() => ({
            token: localStorage.getItem('token'),
            user: localStorage.getItem('user'),
            selectedCourse: localStorage.getItem('selected_course')
          })),
        { timeout: 15000 }
      )
      .toEqual({ token: null, user: null, selectedCourse: null })

    await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(page).toHaveURL(/\/login/, { timeout: 15000 })
    await expect(page.getByTestId('login-panel')).toBeVisible({ timeout: 15000 })
  })
})
