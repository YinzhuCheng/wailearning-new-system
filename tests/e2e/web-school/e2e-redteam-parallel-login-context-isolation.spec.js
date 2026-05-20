const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario } = require('./fixtures.cjs')
const { login } = require('./future-advanced-coverage-helpers.cjs')

function scenario() {
  return loadE2eScenario()
}

test.describe('E2E red-team parallel login context isolation sample', () => {
  test.describe.configure({ timeout: 180_000 })

  test.beforeEach(async ({}, testInfo) => {
    const data = await resetE2eScenario()
    if (!data) {
      testInfo.skip(true, 'Missing e2e seed; run globalSetup with E2E_DEV_SEED_TOKEN')
    }
  })

  test('five isolated browser contexts can log in concurrently without role or token bleed', async ({ browser }) => {
    const s = scenario()
    const actors = [
      { username: s.admin.username, password: s.admin.password, role: 'admin' },
      { username: s.teacher_own.username, password: s.password_teacher_student, role: 'teacher' },
      { username: s.teacher_other.username, password: s.password_teacher_student, role: 'teacher' },
      { username: s.student_plain.username, password: s.password_teacher_student, role: 'student' },
      { username: s.student_b.username, password: s.password_teacher_student, role: 'student' }
    ]
    const contexts = []
    const pages = []

    try {
      for (let i = 0; i < actors.length; i += 1) {
        const ctx = await browser.newContext()
        contexts.push(ctx)
        pages.push(await ctx.newPage())
      }

      await Promise.all(actors.map((actor, index) => login(pages[index], actor.username, actor.password)))

      for (let index = 0; index < actors.length; index += 1) {
        const page = pages[index]
        const actor = actors[index]
        await expect(page).not.toHaveURL(/\/login/, { timeout: 20000 })
        await expect(page.locator('.layout-container, [data-testid="login-page"]').first()).toBeVisible({ timeout: 25000 })
        await expect
          .poll(
            () =>
              page.evaluate(() => {
                const token = localStorage.getItem('token')
                const user = JSON.parse(localStorage.getItem('user') || 'null')
                return { hasToken: Boolean(token), role: user?.role || null, username: user?.username || null }
              }),
            { timeout: 15000 }
          )
          .toEqual({ hasToken: true, role: actor.role, username: actor.username })
      }
    } finally {
      await Promise.all(contexts.map(ctx => ctx.close().catch(() => {})))
    }
  })
})
