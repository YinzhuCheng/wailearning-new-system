/**
 * Structured discussion link cards: picker, draft cards, saved cards, and mobile adaptation.
 */
const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario } = require('./fixtures.cjs')
const { apiJson, login, obtainAccessToken } = require('./future-advanced-coverage-helpers.cjs')

const scenario = () => loadE2eScenario()

async function openDiscussionComposer(page) {
  const discussion = page.locator('.discussion-card').first()
  await expect(discussion).toBeVisible({ timeout: 20000 })
  const composerToggle = discussion.locator('.discussion-composer-head .el-button').first()
  await composerToggle.click()
  await expect(discussion.locator('.discussion-composer-body')).toBeVisible({ timeout: 15000 })
  return discussion
}

async function attachFirstVisibleLink(page) {
  await page.getByTestId('discussion-link-picker-open').click()
  const results = page.getByTestId('discussion-link-picker-results')
  await expect(results).toBeVisible({ timeout: 15000 })
  const row = results.locator('.discussion-link-picker__row').first()
  await expect(row).toBeVisible({ timeout: 15000 })
  await row.getByTestId('discussion-link-picker-add').click()
}

async function createLinkedCommentFixture(s) {
  const token = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
  const base = {
    target_type: 'homework',
    target_id: s.homework_id,
    subject_id: s.course_required_id,
    class_id: s.class_id_1
  }
  const target = await apiJson('/api/discussions', {
    method: 'POST',
    token,
    body: {
      ...base,
      body: `e2e-comment-link-target-${Date.now()}`,
      body_format: 'plain'
    }
  })
  const linked = await apiJson('/api/discussions', {
    method: 'POST',
    token,
    body: {
      ...base,
      body: `e2e-course-and-comment-card-${Date.now()}`,
      body_format: 'plain',
      linked_targets: [
        { target_type: 'course', target_id: s.course_required_id },
        { target_type: 'discussion_entry', target_id: target.id }
      ]
    }
  })
  return { target, linked }
}

async function screenshot(page, testInfo, name) {
  const output = testInfo.outputPath(`${name}.png`)
  await page.screenshot({ path: output, fullPage: true })
  await testInfo.attach(name, { path: output, contentType: 'image/png' })
  return output
}

test.describe('E2E discussion structured link cards', () => {
  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e scenario; set E2E_DEV_SEED_TOKEN')
    }
  })

  test('desktop and mobile screenshots for picker, draft card, and saved card', async ({ page }, testInfo) => {
    const s = scenario()
    await page.setViewportSize({ width: 1366, height: 900 })
    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.goto(`/homework/${s.homework_id}/submit`, { waitUntil: 'load', timeout: 60000 })

    const discussion = await openDiscussionComposer(page)
    await page.getByTestId('discussion-link-picker-open').click()
    await expect(page.getByTestId('discussion-link-picker-results').locator('.discussion-link-picker__row').first()).toBeVisible({
      timeout: 15000
    })
    await screenshot(page, testInfo, 'discussion-link-picker-desktop')

    await page.getByTestId('discussion-link-picker-results').locator('.discussion-link-picker__row').first().getByTestId('discussion-link-picker-add').click()
    await expect(discussion.getByTestId('discussion-linked-target-card')).toBeVisible({ timeout: 10000 })
    await discussion.locator('.discussion-input textarea').fill(`linked-card-ui-${Date.now()}`)
    await screenshot(page, testInfo, 'discussion-link-draft-desktop')

    await discussion.getByTestId('discussion-submit').click()
    const savedRow = page.locator('.discussion-row').filter({ has: page.getByTestId('discussion-linked-target-card') }).last()
    await expect(savedRow).toBeVisible({ timeout: 20000 })
    await screenshot(page, testInfo, 'discussion-link-saved-desktop')

    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto(`/homework/${s.homework_id}/submit`, { waitUntil: 'load', timeout: 60000 })
    await expect(page.getByTestId('discussion-linked-target-card').first()).toBeVisible({ timeout: 20000 })
    await screenshot(page, testInfo, 'discussion-link-saved-mobile')

    const mobileDiscussion = await openDiscussionComposer(page)
    await attachFirstVisibleLink(page)
    await expect(mobileDiscussion.locator('.discussion-composer-body').getByTestId('discussion-linked-target-card')).toBeVisible({
      timeout: 10000
    })
    await screenshot(page, testInfo, 'discussion-link-draft-mobile')
  })

  test('course and comment cards deep-link to visible targets with highlight screenshots', async ({ page }, testInfo) => {
    const s = scenario()
    const fixture = await createLinkedCommentFixture(s)
    await page.setViewportSize({ width: 1366, height: 900 })
    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.goto(`/homework/${s.homework_id}/submit`, { waitUntil: 'load', timeout: 60000 })

    const linkedRow = page.locator('.discussion-row').filter({ hasText: 'e2e-course-and-comment-card' }).last()
    await expect(linkedRow).toBeVisible({ timeout: 20000 })
    const cards = linkedRow.getByTestId('discussion-linked-target-card')
    await expect(cards).toHaveCount(2, { timeout: 10000 })
    await screenshot(page, testInfo, 'discussion-link-course-comment-saved-desktop')

    await cards.nth(0).click()
    await expect(page).toHaveURL(/\/course-home/)
    await expect(page.locator('.student-course-home')).toBeVisible({ timeout: 20000 })
    await screenshot(page, testInfo, 'discussion-link-course-opened-desktop')

    await page.goto(`/homework/${s.homework_id}/submit`, { waitUntil: 'load', timeout: 60000 })
    const rowAgain = page.locator('.discussion-row').filter({ hasText: 'e2e-course-and-comment-card' }).last()
    await expect(rowAgain).toBeVisible({ timeout: 20000 })
    await rowAgain.getByTestId('discussion-linked-target-card').nth(1).click()
    await expect(page).toHaveURL(new RegExp(`/homework/${s.homework_id}/submit.*discussion_entry=${fixture.target.id}`))
    const highlighted = page.locator(`[data-discussion-entry-id="${fixture.target.id}"]`)
    await expect(highlighted).toBeVisible({ timeout: 20000 })
    await expect(highlighted).toHaveClass(/discussion-row--highlighted/, { timeout: 5000 })
    await screenshot(page, testInfo, 'discussion-link-comment-highlight-desktop')

    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto(`/homework/${s.homework_id}/submit?discussion_entry=${fixture.target.id}&discussion_page=1`, {
      waitUntil: 'load',
      timeout: 60000
    })
    await expect(page.locator(`[data-discussion-entry-id="${fixture.target.id}"]`)).toBeVisible({ timeout: 20000 })
    await screenshot(page, testInfo, 'discussion-link-comment-highlight-mobile')
  })
})
