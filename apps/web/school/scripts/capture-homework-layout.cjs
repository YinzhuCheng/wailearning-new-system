#!/usr/bin/env node

const fs = require('fs')
const path = require('path')
const { chromium } = require('playwright')

const schoolRoot = path.resolve(__dirname, '..')
const repoRoot = path.resolve(schoolRoot, '..', '..', '..')
const { writeScenarioCache } = require(path.join(repoRoot, 'tests', 'e2e', 'web-school', 'scenario-cache.cjs'))

const apiPort = process.env.E2E_API_PORT || '8012'
const uiPort = process.env.E2E_UI_PORT || '3012'
const apiBase = (process.env.E2E_API_URL || `http://127.0.0.1:${apiPort}`).replace(/\/$/, '')
const uiBase = (process.env.PLAYWRIGHT_BASE_URL || `http://127.0.0.1:${uiPort}`).replace(/\/$/, '')
const seedToken = (process.env.E2E_DEV_SEED_TOKEN || 'test-playwright-seed').trim()
const outputPath = path.resolve(
  repoRoot,
  process.argv[2] || path.join('pics', 'homework-layout-fixed.png')
)

function ensureDir(targetPath) {
  fs.mkdirSync(path.dirname(targetPath), { recursive: true })
}

async function postJson(url, body, headers = {}) {
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...headers
    },
    body: JSON.stringify(body)
  })
  if (!res.ok) {
    throw new Error(`POST ${url} failed ${res.status}: ${await res.text()}`)
  }
  return res.json()
}

async function getJson(url, headers = {}) {
  const res = await fetch(url, { headers })
  if (!res.ok) {
    throw new Error(`GET ${url} failed ${res.status}: ${await res.text()}`)
  }
  return res.json()
}

async function login(username, password) {
  const body = new URLSearchParams()
  body.set('username', username)
  body.set('password', password)
  const res = await fetch(`${apiBase}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body
  })
  if (!res.ok) {
    throw new Error(`login failed ${res.status}: ${await res.text()}`)
  }
  return res.json()
}

async function refreshScenario() {
  const res = await fetch(`${apiBase}/api/e2e/dev/reset-scenario`, {
    method: 'POST',
    headers: { 'X-E2E-Seed-Token': seedToken }
  })
  if (!res.ok) {
    throw new Error(`reset-scenario failed ${res.status}: ${await res.text()}`)
  }
  const scenario = await res.json()
  writeScenarioCache(scenario)
  return scenario
}

async function createDemoHomework(token, scenario, title, dueDateIso, maxSubmissions) {
  return postJson(
    `${apiBase}/api/homeworks`,
    {
      title,
      content: `用于布局截图验证：${title}`,
      content_format: 'markdown',
      attachment_name: null,
      attachment_url: null,
      due_date: dueDateIso,
      max_score: 100,
      grade_precision: 'integer',
      auto_grading_enabled: true,
      rubric_text: null,
      rubric_staff_only: null,
      reference_answer: null,
      response_language: 'zh-CN',
      allow_late_submission: true,
      late_submission_affects_score: false,
      max_submissions: maxSubmissions,
      llm_routing_spec: null,
      class_id: scenario.class_id_1,
      subject_id: scenario.course_required_id
    },
    {
      Authorization: `Bearer ${token}`
    }
  )
}

async function main() {
  ensureDir(outputPath)

  const scenario = await refreshScenario()
  const teacherLogin = await login(scenario.teacher_own.username, scenario.teacher_own.password)
  const teacherToken = teacherLogin.access_token
  const subjects = await getJson(`${apiBase}/api/subjects`, {
    Authorization: `Bearer ${teacherToken}`
  })
  const selectedCourse = (subjects || []).find(row => Number(row.id) === Number(scenario.course_required_id))
  if (!selectedCourse) {
    throw new Error(`required course ${scenario.course_required_id} not found`)
  }

  const stamp = new Date().toISOString().replace(/[:.]/g, '-')
  await createDemoHomework(
    teacherToken,
    scenario,
    `布局修复演示作业 A ${stamp}`,
    '2026-06-01T20:04:13+08:00',
    3
  )
  await createDemoHomework(
    teacherToken,
    scenario,
    `布局修复演示作业 B ${stamp}`,
    '2026-06-11T20:04:13+08:00',
    4
  )

  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1526, height: 752 } })

  try {
    await page.goto(`${uiBase}/login`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.evaluate(() => {
      localStorage.clear()
      sessionStorage.clear()
    })
    await page.goto(`${uiBase}/login`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.getByTestId('login-username').fill(scenario.teacher_own.username)
    await page.getByTestId('login-password').fill(scenario.teacher_own.password)
    await page.getByTestId('login-submit').click()
    await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 30000 })
    await page.evaluate(course => {
      localStorage.setItem('selected_course', JSON.stringify(course))
    }, selectedCourse)
    await page.goto(`${uiBase}/homework`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.waitForLoadState('networkidle', { timeout: 60000 })
    await page.locator('.homework-table-scroll .el-table__body-wrapper').waitFor({
      state: 'visible',
      timeout: 30000
    })
    await page.screenshot({ path: outputPath, fullPage: true })
  } finally {
    await browser.close()
  }

  process.stdout.write(`${outputPath}\n`)
}

main().catch(error => {
  console.error(error.stack || error)
  process.exit(1)
})
