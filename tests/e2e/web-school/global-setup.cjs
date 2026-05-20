const { refreshE2eAdminBearer } = require('./e2e-seed-headers.cjs')
const { writeScenarioCache } = require('./scenario-cache.cjs')

/**
 * @param {import('@playwright/test').FullConfig} _config
 */
module.exports = async function globalSetup(_config) {
  const token = (process.env.E2E_DEV_SEED_TOKEN || '').trim()
  const base = (process.env.E2E_API_URL || 'http://127.0.0.1:8012').replace(/\/$/, '')
  if (!token) {
    return
  }

  const res = await fetch(`${base}/api/e2e/dev/reset-scenario`, {
    method: 'POST',
    headers: { 'X-E2E-Seed-Token': token }
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`E2E seed failed (${res.status}): ${text}`)
  }

  const data = await res.json()
  await refreshE2eAdminBearer(data)
  writeScenarioCache(data)
}
