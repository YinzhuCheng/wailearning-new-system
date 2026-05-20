/**
 * Focused guard rails for the course-materials chapter outline.
 *
 * The materials tree is the first maintained multi-level outline surface in the
 * school SPA. These tests verify that users can collapse and expand the outline
 * without losing the selected chapter path.
 */
const { expect, test } = require('@playwright/test')
const { enterSeededRequiredCourse, loadE2eScenario, resetE2eScenario } = require('./fixtures.cjs')
const { apiPostJson, login, obtainAccessToken } = require('./future-advanced-coverage-helpers.cjs')

const scenario = () => loadE2eScenario()

async function createChapter(token, subjectId, title, parentId = null) {
  return apiPostJson(`/api/material-chapters?subject_id=${subjectId}`, token, {
    title,
    parent_id: parentId
  })
}

test.describe('materials outline expand/collapse guard rails', () => {
  test.describe.configure({ timeout: 120_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e seed; run globalSetup with E2E_DEV_SEED_TOKEN')
    }
  })

  test('teacher can collapse and expand all material chapters while keeping current path reachable', async ({ page }) => {
    const s = scenario()
    const token = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const suffix = `${s.suffix}_${Date.now()}`
    const parentTitle = `E2E outline parent ${suffix}`
    const childTitle = `E2E outline child ${suffix}`
    const parent = await createChapter(token, s.course_required_id, parentTitle)
    await createChapter(token, s.course_required_id, childTitle, parent.id)

    await page.setViewportSize({ width: 1280, height: 900 })
    await login(page, s.teacher_own.username, s.password_teacher_student)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto('/materials', { waitUntil: 'domcontentloaded', timeout: 60000 })

    await expect(page.locator('.chapter-tree')).toBeVisible({ timeout: 60000 })
    const chapterTree = page.locator('.chapter-tree')
    const parentNode = chapterTree.getByText(parentTitle, { exact: true })
    const childNode = chapterTree.getByText(childTitle, { exact: true })

    await expect(parentNode).toBeVisible({ timeout: 60000 })

    await page.getByTestId('materials-expand-all-chapters').click()
    await expect(childNode).toBeVisible({ timeout: 30000 })

    await page.getByTestId('materials-collapse-all-chapters').click()
    await expect(parentNode).toBeVisible({ timeout: 30000 })
    await expect(childNode).toBeHidden({ timeout: 30000 })

    await page.getByTestId('materials-expand-all-chapters').click()
    await expect(childNode).toBeVisible({ timeout: 30000 })

    await page.getByTestId(`materials-chapter-toggle-${parent.id}`).click()
    await expect(childNode).toBeHidden({ timeout: 30000 })

    await page.getByTestId(`materials-chapter-toggle-${parent.id}`).click()
    await expect(childNode).toBeVisible({ timeout: 30000 })

    await childNode.click()
    await expect(page.getByTestId('materials-current-chapter')).toContainText(childTitle, { timeout: 30000 })

    await page.getByTestId('materials-expand-all-chapters').click()
    await expect(childNode).toBeVisible({ timeout: 30000 })

    await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(page.locator('.chapter-tree').getByText(childTitle, { exact: true })).toBeVisible({ timeout: 60000 })
  })
})
