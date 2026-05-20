/**
 * Shared headers for Playwright E2E calls to /api/e2e/dev/* when dual gate is enabled:
 * X-E2E-Seed-Token + optional admin Bearer (E2E_DEV_REQUIRE_ADMIN_JWT).
 *
 * After each reset-scenario the seeded admin username changes; call refreshE2eAdminBearer
 * whenever scenario.json is refreshed (global-setup + fixtures resetE2eScenario).
 */
function apiBase() {
  return (process.env.E2E_API_URL || 'http://127.0.0.1:8012').replace(/\/$/, '')
}

function adminJwtRequired() {
  const v = String(process.env.E2E_DEV_REQUIRE_ADMIN_JWT || '').trim().toLowerCase()
  return v === '1' || v === 'true' || v === 'yes' || v === 'on'
}

function seedHeaders() {
  const h = { 'X-E2E-Seed-Token': process.env.E2E_DEV_SEED_TOKEN || 'test-playwright-seed' }
  const t = String(process.env.E2E_DEV_ADMIN_BEARER || '').trim()
  if (t) {
    h.Authorization = t.startsWith('Bearer ') ? t : `Bearer ${t}`
  }
  return h
}

/**
 * Login as the seeded scenario admin and store raw JWT in E2E_DEV_ADMIN_BEARER for seedHeaders().
 */
async function refreshE2eAdminBearer(scenario) {
  if (!adminJwtRequired()) {
    return
  }
  const adm = scenario && scenario.admin
  const pw = scenario && scenario.password_admin
  if (!adm || !adm.username || !pw) {
    throw new Error('refreshE2eAdminBearer: scenario missing admin.username or password_admin')
  }
  const body = new URLSearchParams()
  body.set('username', adm.username)
  body.set('password', pw)
  const lr = await fetch(`${apiBase()}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body
  })
  if (!lr.ok) {
    throw new Error(`E2E admin login failed (${lr.status}): ${await lr.text()}`)
  }
  const data = await lr.json()
  process.env.E2E_DEV_ADMIN_BEARER = data.access_token
}

module.exports = { apiBase, adminJwtRequired, seedHeaders, refreshE2eAdminBearer }
