#!/usr/bin/env node

const { spawn, spawnSync } = require('child_process')
const fs = require('fs')
const http = require('http')
const net = require('net')
const os = require('os')
const path = require('path')

const schoolRoot = path.resolve(__dirname, '..')
const repoRoot = path.resolve(schoolRoot, '..', '..', '..')
const parentRoot = path.resolve(repoRoot, 'apps', 'web', 'parent')
const isWindows = process.platform === 'win32'

const requestedApiPort = process.env.E2E_API_PORT || '8012'
const requestedUiPort = process.env.E2E_UI_PORT || '3012'
const requestedParentUiPort = process.env.E2E_PARENT_UI_PORT || '3014'

const pythonExe =
  process.env.E2E_PYTHON ||
  (isWindows
    ? path.join(repoRoot, '.venv', 'Scripts', 'python.exe')
    : path.join(repoRoot, '.venv', 'bin', 'python'))
const viteBin = path.join(schoolRoot, 'node_modules', 'vite', 'bin', 'vite.js')
const parentViteBin = path.join(parentRoot, 'node_modules', 'vite', 'bin', 'vite.js')
const playwrightCli = path.join(schoolRoot, 'node_modules', '@playwright', 'test', 'cli.js')

const useRealWorker = !['0', 'false', 'no', 'off'].includes(
  String(process.env.E2E_USE_REAL_WORKER || 'true').trim().toLowerCase()
)

const children = []
let cleanupStarted = false

function hasCliOption(args, optionName) {
  return args.some((arg, index) => arg === optionName || (index > 0 && args[index - 1] === optionName))
}

function buildHttpBase(port) {
  return `http://127.0.0.1:${port}`
}

async function chooseOpenPort(startPort) {
  let candidate = Number(startPort)
  if (!Number.isFinite(candidate) || candidate <= 0) {
    throw new Error(`invalid start port: ${startPort}`)
  }
  for (let i = 0; i < 50; i += 1) {
    const port = candidate + i
    const ok = await new Promise((resolve) => {
      const server = net.createServer()
      server.unref()
      server.once('error', () => resolve(false))
      server.listen(port, '127.0.0.1', () => {
        server.close(() => resolve(true))
      })
    })
    if (ok) return String(port)
  }
  throw new Error(`no free port found starting from ${startPort}`)
}

function serverEnv(extra = {}) {
  return {
    ...process.env,
    DEBUG: 'false',
    E2E_DEV_SEED_ENABLED: 'true',
    E2E_DEV_SEED_TOKEN: process.env.E2E_DEV_SEED_TOKEN || 'test-playwright-seed',
    E2E_DEV_REQUIRE_ADMIN_JWT:
      process.env.E2E_DEV_REQUIRE_ADMIN_JWT !== undefined
        ? process.env.E2E_DEV_REQUIRE_ADMIN_JWT
        : 'true',
    INIT_DEFAULT_DATA: 'false',
    SECRET_KEY: 'playwright-e2e-secret-key-minimum-32-chars-xx',
    ENABLE_LLM_GRADING_WORKER: useRealWorker ? 'true' : 'false',
    LLM_GRADING_WORKER_LEADER: useRealWorker ? 'true' : 'false',
    LLM_GRADING_WORKER_POLL_SECONDS: '1',
    ...extra
  }
}

function requestOk(url) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: 2_000 }, (res) => {
      res.resume()
      resolve(res.statusCode && res.statusCode < 500)
    })
    req.on('timeout', () => {
      req.destroy()
      resolve(false)
    })
    req.on('error', () => resolve(false))
  })
}

async function waitFor(url, name, timeoutMs = 120_000) {
  const deadline = Date.now() + timeoutMs
  let delay = 100
  while (Date.now() < deadline) {
    if (await requestOk(url)) return
    await new Promise((resolve) => setTimeout(resolve, delay))
    delay = Math.min(1_000, delay * 2)
  }
  throw new Error(`${name} did not become ready at ${url} within ${timeoutMs}ms`)
}

function launch(name, command, args, options) {
  console.log(`[e2e-runner] starting ${name}: ${command} ${args.join(' ')}`)
  const child = spawn(command, args, {
    stdio: 'inherit',
    windowsHide: true,
    ...options
  })
  child.once('exit', (code, signal) => {
    if (!cleanupStarted && code !== null && code !== 0) {
      console.error(`[e2e-runner] ${name} exited early with code ${code}`)
    } else if (!cleanupStarted && signal) {
      console.error(`[e2e-runner] ${name} exited early from signal ${signal}`)
    }
  })
  children.push({ name, child })
  return child
}

function killTree(child) {
  if (!child.pid || child.exitCode !== null || child.signalCode !== null) return
  if (isWindows) {
    spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore' })
    return
  }
  try {
    process.kill(-child.pid, 'SIGTERM')
  } catch {
    try {
      child.kill('SIGTERM')
    } catch {}
  }
}

async function cleanup() {
  if (cleanupStarted) return
  cleanupStarted = true
  for (const { child } of children.slice().reverse()) killTree(child)
  await new Promise((resolve) => setTimeout(resolve, 500))
}

async function main() {
  const rawArgs = process.argv.slice(2)
  const firstArg = rawArgs[0] || ''
  const customNodeScript =
    firstArg &&
    !firstArg.startsWith('-') &&
    /\.(cjs|mjs|js)$/.test(firstArg) &&
    path.isAbsolute(firstArg)
      ? firstArg
      : null
  const playwrightArgs = customNodeScript ? rawArgs.slice(1) : rawArgs
  const wantsParentUi =
    ['1', 'true', 'yes', 'on'].includes(String(process.env.E2E_PARENT_UI || '').trim().toLowerCase()) ||
    rawArgs.some(arg => /parent[-_]portal/i.test(String(arg)))
  const resolvedApiPort = await chooseOpenPort(requestedApiPort)
  const resolvedApiBase = buildHttpBase(resolvedApiPort)
  const resolvedUiPort = await chooseOpenPort(requestedUiPort)
  const resolvedUiBase = buildHttpBase(resolvedUiPort)
  const resolvedParentUiPort = wantsParentUi ? await chooseOpenPort(requestedParentUiPort) : requestedParentUiPort
  const resolvedParentUiBase = buildHttpBase(resolvedParentUiPort)
  const sqliteFile = isWindows
    ? path.join(os.tmpdir(), `playwright_e2e_${resolvedApiPort}.sqlite`)
    : `/tmp/playwright_e2e_${resolvedApiPort}.sqlite`
  const sqliteUrl = isWindows
    ? `sqlite:///${sqliteFile.replace(/\\/g, '/')}`
    : `sqlite:////tmp/playwright_e2e_${resolvedApiPort}.sqlite`
  const resolvedServerEnv = serverEnv({
    E2E_API_PORT: resolvedApiPort,
    E2E_UI_PORT: resolvedUiPort,
    E2E_PARENT_UI_PORT: resolvedParentUiPort,
    E2E_API_URL: process.env.E2E_API_URL || resolvedApiBase,
    DATABASE_URL: sqliteUrl,
  })
  try {
    if (fs.existsSync(sqliteFile)) {
      fs.rmSync(sqliteFile, { force: true })
    }
  } catch (error) {
    console.warn(`[e2e-runner] failed to reset sqlite file ${sqliteFile}: ${error}`)
  }
  const isolatedOutputDir = path.join(os.tmpdir(), 'courseeval-playwright-results', `playwright_${resolvedApiPort}`)
  if (!hasCliOption(playwrightArgs, '--output')) {
    playwrightArgs.push('--output', isolatedOutputDir)
  }
  try {
    if (fs.existsSync(isolatedOutputDir)) {
      fs.rmSync(isolatedOutputDir, { recursive: true, force: true })
    }
  } catch (error) {
    console.warn(`[e2e-runner] failed to reset output dir ${isolatedOutputDir}: ${error}`)
  }
  launch(
    'api',
    pythonExe,
    [
      '-m',
      'uvicorn',
      'apps.backend.courseeval_backend.main:app',
      '--host',
      '127.0.0.1',
      '--port',
      resolvedApiPort
    ],
    {
      cwd: repoRoot,
      env: resolvedServerEnv
    }
  )
  await waitFor(`${resolvedApiBase}/api/health`, 'api')

  launch('ui', 'node', [viteBin, '--host', '127.0.0.1', '--port', resolvedUiPort], {
    cwd: schoolRoot,
    env: {
      ...resolvedServerEnv,
      VITE_PROXY_TARGET: resolvedApiBase
    }
  })
  await waitFor(`${resolvedUiBase}/`, 'ui')

  if (wantsParentUi) {
    launch('parent-ui', 'node', [parentViteBin, '--host', '127.0.0.1', '--port', resolvedParentUiPort], {
      cwd: parentRoot,
      env: {
        ...resolvedServerEnv,
        VITE_PROXY_TARGET: resolvedApiBase,
        VITE_DEV_PORT: resolvedParentUiPort
      }
    })
    await waitFor(`${resolvedParentUiBase}/`, 'parent-ui')
  }

  const testCommand = customNodeScript
    ? [customNodeScript, ...playwrightArgs]
    : [playwrightCli, 'test', ...playwrightArgs]

  const test = spawn(process.execPath, testCommand, {
    cwd: schoolRoot,
    env: {
      ...process.env,
      DEBUG: 'false',
      PLAYWRIGHT_USE_EXTERNAL_SERVERS: 'true',
      E2E_API_PORT: resolvedApiPort,
      E2E_UI_PORT: resolvedUiPort,
      E2E_PARENT_UI_PORT: resolvedParentUiPort,
      E2E_API_URL: process.env.E2E_API_URL || resolvedApiBase,
      E2E_DEV_SEED_TOKEN: process.env.E2E_DEV_SEED_TOKEN || 'test-playwright-seed',
      PLAYWRIGHT_BASE_URL: process.env.PLAYWRIGHT_BASE_URL || resolvedUiBase,
      PLAYWRIGHT_PARENT_BASE_URL: process.env.PLAYWRIGHT_PARENT_BASE_URL || resolvedParentUiBase
    },
    stdio: 'inherit',
    windowsHide: true
  })
  const exitCode = await new Promise((resolve) => {
    test.once('exit', (code, signal) => {
      if (signal) {
        console.error(`[e2e-runner] Playwright exited from signal ${signal}`)
        resolve(1)
      } else {
        resolve(code ?? 1)
      }
    })
  })
  await cleanup()
  process.exit(exitCode)
}

for (const signal of ['SIGINT', 'SIGTERM', 'SIGHUP']) {
  process.on(signal, () => {
    cleanup().finally(() => process.exit(signal === 'SIGINT' ? 130 : 1))
  })
}

main().catch((error) => {
  console.error(`[e2e-runner] ${error.stack || error}`)
  cleanup().finally(() => process.exit(1))
})
