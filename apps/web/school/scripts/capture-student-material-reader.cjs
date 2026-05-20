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
  process.argv[2] || path.join('pics', 'student-material-reader-fixed.png')
)

function ensureDir(targetPath) {
  fs.mkdirSync(path.dirname(targetPath), { recursive: true })
}

async function getJson(url, headers = {}) {
  const res = await fetch(url, { headers })
  if (!res.ok) {
    throw new Error(`GET ${url} failed ${res.status}: ${await res.text()}`)
  }
  return res.json()
}

function flattenChapterTree(nodes = [], depth = 0, rows = []) {
  for (const node of nodes || []) {
    rows.push({
      ...node,
      depth
    })
    flattenChapterTree(node.children || [], depth + 1, rows)
  }
  return rows
}

async function loginApi(username, password) {
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

async function tryLoginApi(username, password) {
  try {
    const result = await loginApi(username, password)
    return result
  } catch {
    return null
  }
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

async function main() {
  ensureDir(outputPath)
  const scenario = await refreshScenario()
  const loginCandidates = [
    { username: 'stu1', password: '111111', label: 'demo-stu1' },
    { username: 'stu2', password: '111111', label: 'demo-stu2' },
    { username: scenario.student_plain.username, password: scenario.student_plain.password, label: 'e2e-student' }
  ]

  let chosenLogin = null
  let chosenToken = null
  let bestCandidate = null

  for (const account of loginCandidates) {
    const loginResult = await tryLoginApi(account.username, account.password)
    if (!loginResult?.access_token) {
      continue
    }
    const studentToken = loginResult.access_token
    const catalog = await getJson(`${apiBase}/api/subjects/course-catalog`, {
      Authorization: `Bearer ${studentToken}`
    })
    for (const row of catalog || []) {
      try {
        const tree = await getJson(`${apiBase}/api/material-chapters/tree?subject_id=${row.id}`, {
          Authorization: `Bearer ${studentToken}`
        })
        const chapters = flattenChapterTree(tree?.nodes || [])
        const uncategorized = chapters.find(item => item.is_uncategorized)
        const structuredChapters = chapters.filter(item => !item.is_uncategorized)

        let bestChapterMaterial = null
        let hasStructuredHomeworkLink = false
        let hasLooseHomeworkLink = Boolean(uncategorized?.homework_links?.length)
        let hasLooseMaterial = false
        let chapterWithMultipleMaterials = false

        for (const chapter of chapters) {
          const params = new URLSearchParams()
          params.set('subject_id', String(row.id))
          params.set('chapter_id', String(chapter.id))
          params.set('page', '1')
          params.set('page_size', '20')
          if (row.class_id != null) {
            params.set('class_id', String(row.class_id))
          }
          const probe = await getJson(`${apiBase}/api/materials?${params.toString()}`, {
            Authorization: `Bearer ${studentToken}`
          })
          const entries = probe?.data || []
          if (chapter.is_uncategorized && entries.length) {
            hasLooseMaterial = true
          }
          if (!chapter.is_uncategorized && chapter.homework_links?.length) {
            hasStructuredHomeworkLink = true
            if (entries[0]?.id) {
              bestChapterMaterial = entries[0]
              break
            }
          }
          if (!chapter.is_uncategorized && entries.length > 1) {
            chapterWithMultipleMaterials = true
          }
          if (!bestChapterMaterial && entries[0]?.id) {
            bestChapterMaterial = entries[0]
          }
        }

        if (!bestChapterMaterial?.id) {
          continue
        }

        const preferredNameBonus =
          /概率|数据挖掘/i.test(String(row.name || '')) ? 50 : 0
        const score =
          preferredNameBonus +
          (hasStructuredHomeworkLink ? 20 : 0) +
          (hasLooseHomeworkLink ? 10 : 0) +
          (hasLooseMaterial ? 10 : 0) +
          (chapterWithMultipleMaterials ? 5 : 0) +
          structuredChapters.length

        if (!bestCandidate || score > bestCandidate.score) {
          chosenLogin = account
          chosenToken = studentToken
          bestCandidate = {
            score,
            course: row,
            materialId: bestChapterMaterial.id
          }
        }
      } catch {
        // try the next student-visible catalog row
      }
    }
  }

  if (!chosenLogin || !chosenToken || !bestCandidate?.course || !bestCandidate?.materialId) {
    throw new Error('no student-readable course material found in the current catalog')
  }

  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 980 } })

  try {
    await page.goto(`${uiBase}/login`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.evaluate(() => {
      localStorage.clear()
      sessionStorage.clear()
    })
    await page.goto(`${uiBase}/login`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.getByTestId('login-username').fill(chosenLogin.username)
    await page.getByTestId('login-password').fill(chosenLogin.password)
    await page.getByTestId('login-submit').click()
    await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 30000 })
    await page.evaluate(course => {
      localStorage.setItem('selected_course', JSON.stringify(course))
    }, bestCandidate.course)
    await page.goto(`${uiBase}/materials/read/${bestCandidate.materialId}`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    await page.waitForURL(url => url.pathname.includes('/materials/read/'), { timeout: 60000 })
    await page.waitForLoadState('networkidle', { timeout: 60000 })
    await page.locator('.material-read-body').waitFor({ state: 'visible', timeout: 30000 })
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
