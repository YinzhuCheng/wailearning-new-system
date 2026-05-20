const { defineConfig, devices } = require('@playwright/test')
const fs = require('fs')
const path = require('path')
const os = require('os')
const Module = require('module')

const E2E_API_PORT = process.env.E2E_API_PORT || '8012'
const E2E_UI_PORT = process.env.E2E_UI_PORT || '3012'
const apiBase = `http://127.0.0.1:${E2E_API_PORT}`

process.env.E2E_API_URL = process.env.E2E_API_URL || apiBase
process.env.E2E_DEV_SEED_TOKEN = process.env.E2E_DEV_SEED_TOKEN || 'test-playwright-seed'
process.env.PLAYWRIGHT_BASE_URL =
  process.env.PLAYWRIGHT_BASE_URL || `http://127.0.0.1:${E2E_UI_PORT}`
// Default dual gate for powerful /api/e2e/dev/* routes (mock LLM, grading pump); override with E2E_DEV_REQUIRE_ADMIN_JWT=0.
process.env.E2E_DEV_REQUIRE_ADMIN_JWT =
  process.env.E2E_DEV_REQUIRE_ADMIN_JWT !== undefined
    ? process.env.E2E_DEV_REQUIRE_ADMIN_JWT
    : 'true'

const repoRoot = path.resolve(__dirname, '..', '..', '..')
const schoolRoot = __dirname
const schoolNodeModules = path.join(schoolRoot, 'node_modules')
const viteBin = path.join(schoolNodeModules, 'vite', 'bin', 'vite.js')

process.env.NODE_PATH = [schoolNodeModules, process.env.NODE_PATH].filter(Boolean).join(path.delimiter)
Module._initPaths()
const isWindows = process.platform === 'win32'
const sqliteFile = isWindows
  ? path.join(os.tmpdir(), `playwright_e2e_${E2E_API_PORT}.sqlite`)
  : `/tmp/playwright_e2e_${E2E_API_PORT}.sqlite`
const sqliteUrl = isWindows
  ? `sqlite:///${sqliteFile.replace(/\\/g, '/')}`
  : `sqlite:////tmp/playwright_e2e_${E2E_API_PORT}.sqlite`
const secretKey = 'playwright-e2e-secret-key-minimum-32-chars-xx'
const useRealWorker = !['0', 'false', 'no', 'off'].includes(
  String(process.env.E2E_USE_REAL_WORKER || 'true').trim().toLowerCase()
)
const useExternalServers = ['1', 'true', 'yes', 'on'].includes(
  String(process.env.PLAYWRIGHT_USE_EXTERNAL_SERVERS || 'false').trim().toLowerCase()
)

const dualJwt = ['1', 'true', 'yes', 'on'].includes(
  String(process.env.E2E_DEV_REQUIRE_ADMIN_JWT || '').trim().toLowerCase()
)

const apiEnv = {
  DEBUG: 'false',
  E2E_DEV_SEED_ENABLED: 'true',
  E2E_DEV_SEED_TOKEN: process.env.E2E_DEV_SEED_TOKEN,
  E2E_DEV_REQUIRE_ADMIN_JWT: dualJwt ? 'true' : 'false',
  INIT_DEFAULT_DATA: 'false',
  DATABASE_URL: sqliteUrl,
  SECRET_KEY: secretKey,
  ENABLE_LLM_GRADING_WORKER: useRealWorker ? 'true' : 'false',
  LLM_GRADING_WORKER_LEADER: useRealWorker ? 'true' : 'false',
  LLM_GRADING_WORKER_POLL_SECONDS: '1'
}

function quoteWindowsArg(value) {
  return `"${String(value).replace(/"/g, '\\"')}"`
}

function buildApiCommand() {
  if (isWindows) {
    const pythonExe = process.env.E2E_PYTHON || path.join(repoRoot, '.venv', 'Scripts', 'python.exe')
    return `${quoteWindowsArg(pythonExe)} -m uvicorn apps.backend.courseeval_backend.main:app --host 127.0.0.1 --port ${E2E_API_PORT}`
  }
  const defaultVenvPython = path.join(repoRoot, '.venv', 'bin', 'python')
  const pythonExe =
    process.env.E2E_PYTHON || (fs.existsSync(defaultVenvPython) ? defaultVenvPython : 'python3')
  const apiEnvString = Object.entries(apiEnv)
    .map(([key, value]) => `${key}=${JSON.stringify(String(value))}`)
    .join(' ')
  return `bash -lc 'cd "${repoRoot}" && exec env ${apiEnvString} "${pythonExe}" -m uvicorn apps.backend.courseeval_backend.main:app --host 127.0.0.1 --port ${E2E_API_PORT}'`
}

function buildUiCommand() {
  if (isWindows) {
    return `node ${quoteWindowsArg(viteBin)} --host 127.0.0.1 --port ${E2E_UI_PORT}`
  }
  return `bash -lc 'cd "${schoolRoot}" && exec env VITE_PROXY_TARGET=${apiBase} node "${viteBin}" --host 127.0.0.1 --port ${E2E_UI_PORT}'`
}

function buildApiServerConfig() {
  return {
    command: buildApiCommand(),
    cwd: repoRoot,
    env: apiEnv,
    url: `${apiBase}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000
  }
}

function buildUiServerConfig() {
  return {
    command: buildUiCommand(),
    cwd: schoolRoot,
    env: {
      DEBUG: 'false',
      VITE_PROXY_TARGET: apiBase
    },
    url: `http://127.0.0.1:${E2E_UI_PORT}/`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000
  }
}

/**
 * @see {import('@playwright/test').PlaywrightTestConfig}
 */
module.exports = defineConfig({
  testDir: '../../../tests/e2e/web-school',
  timeout: 60_000,
  globalSetup: '../../../tests/e2e/web-school/global-setup.cjs',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure'
  },
  webServer: useExternalServers ? undefined : [buildApiServerConfig(), buildUiServerConfig()],
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }]
})
