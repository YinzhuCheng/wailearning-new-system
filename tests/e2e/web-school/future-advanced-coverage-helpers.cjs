const { expect } = require('@playwright/test')
const { seedHeaders } = require('./e2e-seed-headers.cjs')

function apiBase() {
  return (process.env.E2E_API_URL || 'http://127.0.0.1:8012').replace(/\/$/, '')
}

function escapeRegex(text) {
  return `${text || ''}`.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * Open header course dropdown and select a course row by visible label text.
 * Element Plus teleports the menu, so prefer the explicit popper class and keep
 * the legacy menu class as a fallback for older branches.
 */
async function clickCourseSwitcherOption(page, courseLabel) {
  const switcher = page.getByTestId('header-course-switch')
  await expect(switcher).toBeVisible({ timeout: 15000 })
  const menu = page.locator('.course-dropdown-popper, .course-dropdown-menu').filter({ visible: true }).first()
  const trigger = switcher.getByRole('button').first()
  for (let attempt = 0; attempt < 4; attempt++) {
    if (await menu.isVisible().catch(() => false)) {
      break
    }
    await trigger.click({ force: true }).catch(() => switcher.click({ force: true }))
    try {
      await menu.waitFor({ state: 'visible', timeout: 2000 })
      break
    } catch {
      await switcher.hover({ force: true })
    }
    try {
      await menu.waitFor({ state: 'visible', timeout: 2000 })
      break
    } catch {
      await page.mouse.move(4 + attempt, 4 + attempt)
    }
  }
  await expect(menu).toBeVisible({ timeout: 15000 })
  const row = menu.locator('.course-option').filter({ hasText: courseLabel }).first()
  await expect(row).toBeVisible({ timeout: 12000 })
  await row.click({ force: true })
}

function isDestroyedContextError(err) {
  const msg = `${err && err.message ? err.message : err}`
  return (
    msg.includes('Execution context was destroyed') ||
    msg.includes('Target page, context or browser has been closed') ||
    msg.includes('interrupted by another navigation') ||
    msg.includes('net::ERR_ABORTED')
  )
}

async function gotoLogin(page) {
  for (let attempt = 0; attempt < 8; attempt++) {
    try {
      await page.goto('/login', { waitUntil: 'domcontentloaded', timeout: 60000 })
      return
    } catch (e) {
      if (!isDestroyedContextError(e) || attempt === 7) {
        throw e
      }
      await new Promise(r => setTimeout(r, 200 + attempt * 100))
    }
  }
}

async function login(page, username, password) {
  await gotoLogin(page)
  try {
    await page.evaluate(() => {
      try {
        localStorage.clear()
        sessionStorage.clear()
      } catch {
        /* ignore */
      }
    })
  } catch (e) {
    if (!isDestroyedContextError(e)) {
      throw e
    }
  }
  await gotoLogin(page)
  await expect(page.getByTestId('login-username')).toBeVisible({ timeout: 30000 })
  await page.getByTestId('login-username').fill(username)
  await page.getByTestId('login-password').fill(password)
  await page.getByTestId('login-submit').click({ timeout: 30000 })

  let user = await waitForStoredUser(page, 12000)
  if (!user) {
    const session = await loginViaApi(username, password)
    user = session.user
    await page.evaluate(
      ({ token, user: userData }) => {
        try {
          sessionStorage.clear()
        } catch {
          /* ignore */
        }
        localStorage.setItem('token', token)
        localStorage.setItem('user', JSON.stringify(userData))
        if (userData?.role === 'student') {
          localStorage.removeItem('selected_course')
        }
      },
      session
    )
  }

  if (page.url().includes('/login')) {
    const fallbackTarget = user?.role === 'student' ? '/courses' : '/students'
    await page.goto(fallbackTarget, { waitUntil: 'load', timeout: 60000 })
  }

  await expect(page).not.toHaveURL(/\/login/, { timeout: 20000 })
  return user
}

async function obtainAccessToken(username, password) {
  const body = new URLSearchParams()
  body.set('username', username)
  body.set('password', password)
  const res = await fetch(`${apiBase()}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body
  })
  if (!res.ok) {
    throw new Error(`login failed ${res.status}: ${await res.text()}`)
  }
  const data = await res.json()
  return data.access_token
}

async function loginViaApi(username, password) {
  const token = await obtainAccessToken(username, password)
  const me = await fetch(`${apiBase()}/api/auth/me`, {
    headers: { Authorization: `Bearer ${token}` }
  })
  if (!me.ok) {
    throw new Error(`GET /api/auth/me failed ${me.status}: ${await me.text()}`)
  }
  return { token, user: await me.json() }
}

async function waitForStoredUser(page, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const user = await page.evaluate(() => {
        try {
          const token = localStorage.getItem('token')
          const parsed = JSON.parse(localStorage.getItem('user') || 'null')
          return token && parsed?.role ? parsed : null
        } catch {
          return null
        }
      })
      if (user?.role) {
        return user
      }
    } catch (e) {
      if (!isDestroyedContextError(e)) {
        throw e
      }
    }
    await page.waitForTimeout(250).catch(() => {})
  }
  return null
}

async function apiGetJson(pathname, token) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  })
  if (!res.ok) {
    throw new Error(`GET ${pathname} failed ${res.status}: ${await res.text()}`)
  }
  return res.json()
}

async function apiPostJson(pathname, token, body) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify(body)
  })
  if (!res.ok) {
    throw new Error(`POST ${pathname} failed ${res.status}: ${await res.text()}`)
  }
  return res.json()
}

async function apiPutJson(pathname, token, body) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify(body)
  })
  if (!res.ok) {
    throw new Error(`PUT ${pathname} failed ${res.status}: ${await res.text()}`)
  }
  return res.json()
}

async function apiPatchJson(pathname, token, body) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify(body)
  })
  if (!res.ok) {
    throw new Error(`PATCH ${pathname} failed ${res.status}: ${await res.text()}`)
  }
  return res.json()
}

async function apiDelete(pathname, token) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method: 'DELETE',
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  })
  if (!res.ok) {
    throw new Error(`DELETE ${pathname} failed ${res.status}: ${await res.text()}`)
  }
  try {
    return await res.json()
  } catch {
    return {}
  }
}

async function apiJson(pathname, { method = 'GET', token, body, headers = {} } = {}) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method,
    headers: {
      ...(body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers
    },
    body:
      body == null
        ? undefined
        : body instanceof FormData
          ? body
          : typeof body === 'string'
            ? body
            : JSON.stringify(body)
  })
  if (!res.ok) {
    throw new Error(`${method} ${pathname} failed ${res.status}: ${await res.text()}`)
  }
  return res.json()
}

async function configureMockLlm(profiles) {
  return apiJson('/api/e2e/dev/mock-llm/configure', {
    method: 'POST',
    headers: seedHeaders(),
    body: { profiles }
  })
}

async function processGradingTasks(maxTasks = 5) {
  let total = 0
  for (let i = 0; i < 12; i += 1) {
    const res = await apiJson('/api/e2e/dev/process-grading', {
      method: 'POST',
      headers: seedHeaders(),
      body: { max_tasks: maxTasks }
    })
    total += res.processed || 0
    if ((res.processed || 0) === 0) {
      await new Promise(r => setTimeout(r, 200))
    }
  }
  return total
}

async function gradingState() {
  return apiJson('/api/e2e/dev/grading-state', { headers: seedHeaders() })
}

async function createPreset(adminToken, name, profile, options = {}) {
  return apiJson('/api/llm-settings/presets', {
    method: 'POST',
    token: adminToken,
    body: {
      name,
      base_url: `${apiBase()}/api/e2e/dev/mock-llm/${profile}/v1/`,
      api_key: options.api_key || 'mock-api-key',
      model_name: options.model_name || 'mock-model',
      connect_timeout_seconds: options.connect_timeout_seconds || 2,
      read_timeout_seconds: options.read_timeout_seconds || 2,
      max_retries: options.max_retries ?? 0,
      initial_backoff_seconds: options.initial_backoff_seconds || 1,
      is_active: options.is_active ?? true
    }
  })
}

async function validatePreset(adminToken, presetId) {
  return apiJson('/api/e2e/dev/mark-preset-validated', {
    method: 'POST',
    headers: seedHeaders(),
    body: { preset_id: presetId }
  })
}

async function updateCourseLlmConfig(token, subjectId, payload) {
  return apiJson(`/api/llm-settings/courses/${subjectId}`, {
    method: 'PUT',
    token,
    body: payload
  })
}

async function setFlatCourseConfig(token, subjectId, presetIds, extra = {}) {
  return updateCourseLlmConfig(token, subjectId, {
    is_enabled: true,
    response_language: 'zh-CN',
    max_input_tokens: 16000,
    max_output_tokens: 1200,
    system_prompt: null,
    teacher_prompt: null,
    endpoints: presetIds.map((presetId, index) => ({ preset_id: presetId, priority: index + 1 })),
    replace_group_routing_with_flat_endpoints: true,
    ...extra
  })
}

async function createHomework(token, ctx, title, extra = {}) {
  return apiJson('/api/homeworks', {
    method: 'POST',
    token,
    body: {
      title,
      content: extra.content || `content ${title}`,
      attachment_name: null,
      attachment_url: null,
      due_date: null,
      max_score: 100,
      grade_precision: 'integer',
      auto_grading_enabled: extra.auto_grading_enabled ?? true,
      rubric_text: extra.rubric_text || null,
      rubric_staff_only: extra.rubric_staff_only || null,
      reference_answer: extra.reference_answer || null,
      response_language: extra.response_language || 'zh-CN',
      allow_late_submission: true,
      late_submission_affects_score: false,
      max_submissions: extra.max_submissions ?? null,
      llm_routing_spec: extra.llm_routing_spec ?? null,
      class_id: ctx.class_id_1,
      subject_id: ctx.course_required_id
    }
  })
}

async function mySubmissionHistory(token, homeworkId) {
  return apiJson(`/api/homeworks/${homeworkId}/submission/me/history`, { token })
}

async function apiListHomeworkRows(token, subjectId) {
  const url = new URL(`${apiBase()}/api/homeworks`)
  url.searchParams.set('subject_id', String(subjectId))
  url.searchParams.set('page_size', '100')
  const res = await fetch(url.toString(), { headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok) {
    throw new Error(`homeworks list ${res.status}`)
  }
  const data = await res.json()
  return data.data || []
}

async function apiListNotifications(token, params = {}) {
  const url = new URL(`${apiBase()}/api/notifications`)
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value))
    }
  }
  const res = await fetch(url.toString(), {
    headers: { Authorization: `Bearer ${token}` }
  })
  if (!res.ok) {
    throw new Error(`notifications list failed ${res.status}`)
  }
  return res.json()
}

async function apiListScoreAppeals(token, params = {}) {
  const url = new URL(`${apiBase()}/api/scores/appeals`)
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value))
    }
  }
  const res = await fetch(url.toString(), {
    headers: { Authorization: `Bearer ${token}` }
  })
  if (!res.ok) {
    throw new Error(`score appeals ${res.status}`)
  }
  return res.json()
}

async function apiStudentCourseCatalog(token) {
  return apiGetJson('/api/subjects/course-catalog', token)
}

async function apiListUsers(token) {
  return apiGetJson('/api/users', token)
}

async function apiBatchSetClass(token, userIds, classId) {
  return apiPostJson('/api/users/batch-set-class', token, {
    user_ids: userIds,
    class_id: classId
  })
}

async function apiFindUserIdByUsername(token, username) {
  const users = await apiListUsers(token)
  const user = users.find(row => row.username === username)
  if (!user) {
    throw new Error(`user ${username} not found`)
  }
  return user.id
}

async function apiHomeworkSubmissionHistory(token, homeworkId) {
  return apiGetJson(`/api/homeworks/${homeworkId}/submission/me/history`, token)
}

function flattenChapterTree(nodes, acc = []) {
  for (const n of nodes || []) {
    if (!n.is_uncategorized) {
      acc.push(n)
    }
    if (n.children && n.children.length) {
      flattenChapterTree(n.children, acc)
    }
  }
  return acc
}

async function getChapterTree(token, subjectId) {
  return apiGetJson(`/api/material-chapters/tree?subject_id=${subjectId}`, token)
}

async function currentSelectedCourseId(page) {
  return page.evaluate(() => {
    const raw = localStorage.getItem('selected_course')
    if (!raw) {
      return null
    }
    try {
      const parsed = JSON.parse(raw)
      return parsed && typeof parsed.id !== 'undefined' ? parsed.id : null
    } catch {
      return null
    }
  })
}

async function apiPostForm(pathname, token, formData) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData
  })
  if (!res.ok) {
    throw new Error(`POST ${pathname} failed ${res.status}: ${await res.text()}`)
  }
  return res.json()
}

/**
 * Element Plus ElMessageBox.confirm — teleported, NOT `el-dialog` course forms.
 * Using generic `getByRole('dialog')` often matches the wrong overlay after long SQLite runs.
 */
async function confirmElMessageBoxPrimary(page) {
  const overlay = page
    .locator('.el-overlay')
    .filter({ has: page.locator('.el-message-box') })
    .filter({ visible: true })
    .last()
  try {
    await overlay.waitFor({ state: 'visible', timeout: 2000 })
  } catch {
    await page.keyboard.press('Enter')
    return
  }
  const box = overlay.locator('.el-message-box').last()
  await box.waitFor({ state: 'visible', timeout: 30000 })
  await box.locator('.el-message-box__btns .el-button--primary').click({ timeout: 60000, force: true })
}

module.exports = {
  apiBase,
  seedHeaders,
  escapeRegex,
  clickCourseSwitcherOption,
  login,
  obtainAccessToken,
  apiGetJson,
  apiPostJson,
  apiPutJson,
  apiPatchJson,
  apiDelete,
  apiJson,
  configureMockLlm,
  processGradingTasks,
  gradingState,
  createPreset,
  validatePreset,
  updateCourseLlmConfig,
  setFlatCourseConfig,
  createHomework,
  mySubmissionHistory,
  apiListHomeworkRows,
  apiListNotifications,
  apiListScoreAppeals,
  apiStudentCourseCatalog,
  apiListUsers,
  apiBatchSetClass,
  apiFindUserIdByUsername,
  apiHomeworkSubmissionHistory,
  flattenChapterTree,
  getChapterTree,
  currentSelectedCourseId,
  apiPostForm,
  confirmElMessageBoxPrimary
}
