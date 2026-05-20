/**
 * Maintained responsive layout guard rails for the school SPA.
 *
 * These checks preserve previously observed responsive-layout guard rails as
 * narrow Playwright assertions. They intentionally avoid screenshot comparison; the invariant is
 * physical layout containment at the mobile breakpoint plus preservation of the
 * desktop course-catalog table.
 */
const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario } = require('./fixtures.cjs')
const { login } = require('./future-advanced-coverage-helpers.cjs')

const scenario = () => loadE2eScenario()
const sidebarStateKey = 'courseeval-school-sidebar-state'

async function expectNoPageHorizontalOverflow(page) {
  await expect
    .poll(
      async () =>
        page.evaluate(() => {
          const root = document.documentElement
          const body = document.body
          const scrollWidth = Math.max(root.scrollWidth, body ? body.scrollWidth : 0)
          return scrollWidth <= window.innerWidth + 1
        }),
      { timeout: 30000 }
    )
    .toBeTruthy()
}

async function expectLocatorBoxesWithinViewport(page, locator, { maxItems = 24 } = {}) {
  const viewport = page.viewportSize()
  expect(viewport).toBeTruthy()
  const count = await locator.count()
  expect(count).toBeGreaterThan(0)
  const n = Math.min(count, maxItems)
  for (let index = 0; index < n; index += 1) {
    const box = await locator.nth(index).boundingBox()
    expect(box, `expected visible bounding box for item ${index}`).toBeTruthy()
    expect(box.x, `item ${index} should not overflow left`).toBeGreaterThanOrEqual(-1)
    expect(box.x + box.width, `item ${index} should not overflow right`).toBeLessThanOrEqual(viewport.width + 1)
  }
}

async function clearSidebarState(page) {
  await page.addInitScript(key => {
    window.localStorage.removeItem(key)
  }, sidebarStateKey)
}

test.describe('responsive layout regression guard rails', () => {
  test.describe.configure({ timeout: 120_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e seed; run globalSetup with E2E_DEV_SEED_TOKEN')
    }
  })

  test('mobile student courses page has no sidebar-driven horizontal overflow', async ({ page }) => {
    const s = scenario()
    await page.setViewportSize({ width: 390, height: 844 })
    await clearSidebarState(page)
    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.goto('/courses', { waitUntil: 'domcontentloaded', timeout: 60000 })

    await expect(page.locator('.layout-container')).toBeVisible({ timeout: 30000 })
    await expect(page.locator('.mobile-menu-btn')).toBeVisible({ timeout: 30000 })
    await expect(page.locator('.elective-catalog-card')).toBeVisible({ timeout: 60000 })
    await expect(page.locator('article.course-card').first()).toBeVisible({ timeout: 60000 })

    const sidebarBox = await page.locator('.sidebar').boundingBox()
    expect(sidebarBox, 'sidebar box should exist even when collapsed').toBeTruthy()
    expect(sidebarBox.width, 'collapsed mobile sidebar should render only a tiny transformed edge').toBeLessThanOrEqual(8)
    const contentBox = await page.locator('.layout-container > .el-container').boundingBox()
    expect(contentBox, 'main layout container should be measurable').toBeTruthy()
    expect(contentBox.x, 'collapsed mobile sidebar must not push content to the right').toBeLessThanOrEqual(1)

    await expectNoPageHorizontalOverflow(page)
  })

  test('mobile course cards and catalog cards stay inside a 390px viewport', async ({ page }) => {
    const s = scenario()
    await page.setViewportSize({ width: 390, height: 844 })
    await clearSidebarState(page)
    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.goto('/courses', { waitUntil: 'domcontentloaded', timeout: 60000 })

    await expect(page.locator('.catalog-mobile-list')).toBeVisible({ timeout: 60000 })
    await expect(page.locator('.catalog-mobile-item').first()).toBeVisible({ timeout: 60000 })
    await expect(page.locator('.elective-catalog-card .el-table')).toBeHidden({ timeout: 30000 })

    await expectLocatorBoxesWithinViewport(page, page.locator('article.course-card'), { maxItems: 12 })
    await expectLocatorBoxesWithinViewport(page, page.locator('.catalog-mobile-item'), { maxItems: 24 })
    await expectNoPageHorizontalOverflow(page)
  })

  test('desktop student courses page keeps the catalog table as the primary catalog surface', async ({ page }) => {
    const s = scenario()
    await page.setViewportSize({ width: 1280, height: 900 })
    await clearSidebarState(page)
    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.goto('/courses', { waitUntil: 'domcontentloaded', timeout: 60000 })

    await expect(page.locator('.elective-catalog-card')).toBeVisible({ timeout: 60000 })
    await expect(page.locator('.elective-catalog-card .el-table')).toBeVisible({ timeout: 60000 })
    await expect(page.locator('.catalog-mobile-list')).toBeHidden({ timeout: 30000 })
    await expect(page.locator('article.course-card').first()).toBeVisible({ timeout: 60000 })
  })

  test('desktop sidebar edge handle hides and restores the navigation rail', async ({ page }) => {
    const s = scenario()
    await page.setViewportSize({ width: 1280, height: 900 })
    await clearSidebarState(page)
    await login(page, s.admin.username, s.admin.password)
    await page.goto('/students', { waitUntil: 'domcontentloaded', timeout: 60000 })

    const sidebar = page.locator('.sidebar')
    const mainContainer = page.locator('.layout-container > .el-container')
    const handle = page.getByTestId('sidebar-edge-handle')
    await expect(sidebar).toBeVisible({ timeout: 30000 })
    await expect(handle).toBeVisible({ timeout: 30000 })

    const expandedSidebarBox = await sidebar.boundingBox()
    const expandedMainBox = await mainContainer.boundingBox()
    expect(expandedSidebarBox.width).toBeGreaterThan(200)
    expect(expandedMainBox.x).toBeGreaterThan(200)

    await handle.click()
    await expect
      .poll(async () => {
        const sidebarBox = await sidebar.boundingBox()
        const mainBox = await mainContainer.boundingBox()
        return sidebarBox.width <= 1 && mainBox.x <= 1
      }, { timeout: 10000 })
      .toBeTruthy()

    await handle.click()
    await expect
      .poll(async () => {
        const sidebarBox = await sidebar.boundingBox()
        const mainBox = await mainContainer.boundingBox()
        return sidebarBox.width > 200 && mainBox.x > 200
      }, { timeout: 10000 })
      .toBeTruthy()
  })

  test('mobile table-heavy admin and teacher pages contain wide data surfaces inside the page', async ({ page }) => {
    const s = scenario()
    await page.setViewportSize({ width: 390, height: 844 })
    await clearSidebarState(page)

    await login(page, s.admin.username, s.admin.password)
    for (const routePath of ['/students', '/users', '/subjects']) {
      await page.goto(routePath, { waitUntil: 'domcontentloaded', timeout: 60000 })
      await expect(page.locator('.layout-container')).toBeVisible({ timeout: 30000 })
      await expect(page.locator('.el-card').first()).toBeVisible({ timeout: 60000 })
      await expectNoPageHorizontalOverflow(page)
    }

    await login(page, s.teacher_own.username, s.password_teacher_student)
    for (const routePath of ['/scores', '/attendance']) {
      await page.goto(routePath, { waitUntil: 'domcontentloaded', timeout: 60000 })
      await expect(page.locator('.layout-container')).toBeVisible({ timeout: 30000 })
      await expect(page.locator('.el-card').first()).toBeVisible({ timeout: 60000 })
      await expectNoPageHorizontalOverflow(page)
    }
  })
})
