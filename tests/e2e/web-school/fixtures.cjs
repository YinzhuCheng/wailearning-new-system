const { expect } = require('@playwright/test')
const { refreshE2eAdminBearer } = require('./e2e-seed-headers.cjs')
const { readScenarioCache, writeScenarioCache } = require('./scenario-cache.cjs')

let cached

function apiBase() {
  return (process.env.E2E_API_URL || 'http://127.0.0.1:8012').replace(/\/$/, '')
}

/**
 * @returns {Record<string, unknown>|null}
 */
function loadE2eScenario() {
  if (cached !== undefined) {
    return cached
  }
  cached = readScenarioCache()
  return cached
}

async function resetE2eScenario() {
  const token = (process.env.E2E_DEV_SEED_TOKEN || '').trim()
  if (!token) {
    cached = null
    return null
  }
  const res = await fetch(`${apiBase()}/api/e2e/dev/reset-scenario`, {
    method: 'POST',
    headers: { 'X-E2E-Seed-Token': token }
  })
  if (!res.ok) {
    throw new Error(`E2E seed failed (${res.status}): ${await res.text()}`)
  }
  const data = await res.json()
  await refreshE2eAdminBearer(data)
  writeScenarioCache(data)
  cached = data
  return data
}

/** Open the seeded required course card (stable when multiple courses exist). */
async function enterSeededRequiredCourse(page, suffix) {
  const name = `E2E必修课_${suffix}`
  await page.goto('/courses')
  const card = page.locator('article.course-card').filter({ has: page.getByRole('heading', { name: name }) })
  await expect(card).toBeVisible({ timeout: 15000 })
  const action = card.getByRole('button', { name: /进入课程|查看课程/ }).first()
  await expect(action).toBeVisible({ timeout: 15000 })
  if (await action.isDisabled().catch(() => false)) {
    const target = await page.evaluate(() => {
      try {
        const user = JSON.parse(localStorage.getItem('user') || 'null')
        return user?.role === 'student' ? '/course-home' : '/students'
      } catch {
        return '/course-home'
      }
    })
    await page.goto(target, { waitUntil: 'domcontentloaded', timeout: 60000 })
    return
  }
  await Promise.all([
    page.waitForURL(/\/(course-home|students)$/, { timeout: 60000 }),
    action.click()
  ])
}

module.exports = { loadE2eScenario, resetE2eScenario, enterSeededRequiredCourse }
