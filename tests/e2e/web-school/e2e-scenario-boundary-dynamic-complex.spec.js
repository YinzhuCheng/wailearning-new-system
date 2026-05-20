/**
 * Scenario-style Playwright tests: boundary (cold start / CRUD), dynamic (mutations visible end-to-end),
 * complex (multi-step, multi-role, optional API audit).
 *
 * Relies on globalSetup -> e2e/.cache/scenario.json (same as other e2e specs).
 */
const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario, enterSeededRequiredCourse } = require('./fixtures.cjs')

const { confirmElMessageBoxPrimary } = require('./future-advanced-coverage-helpers.cjs')

const scenario = () => loadE2eScenario()

function apiBase() {
  return (process.env.E2E_API_URL || 'http://127.0.0.1:8012').replace(/\/$/, '')
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

async function login(page, username, password) {
  await page.goto('/login', { waitUntil: 'load', timeout: 60000 })
  await page.evaluate(() => {
    try {
      localStorage.clear()
      sessionStorage.clear()
    } catch {
      /* ignore opaque origins */
    }
  })
  await expect(page.getByTestId('login-username')).toBeVisible({ timeout: 60000 })
  await page.getByTestId('login-username').fill(username)
  await page.getByTestId('login-password').fill(password)
  await page.getByTestId('login-submit').click()
  await expect
    .poll(
      async () =>
        page.evaluate(() => {
          try {
            const user = JSON.parse(localStorage.getItem('user') || 'null')
            return user?.role || null
          } catch {
            return null
          }
        }),
      { timeout: 20000 }
    )
    .not.toBeNull()
  if (page.url().includes('/login')) {
    const fallbackTarget = await page.evaluate(() => {
      try {
        const user = JSON.parse(localStorage.getItem('user') || 'null')
        return user?.role === 'student' ? '/courses' : '/students'
      } catch {
        return '/students'
      }
    })
    await page.goto(fallbackTarget, { waitUntil: 'load', timeout: 60000 })
  }
  await expect(page).not.toHaveURL(/\/login/, { timeout: 20000 })
}

async function confirmMessageBox(page) {
  await confirmElMessageBoxPrimary(page)
}

async function apiCourseExistsForTeacher(token, courseNameSubstring) {
  const res = await fetch(`${apiBase()}/api/subjects`, {
    headers: { Authorization: `Bearer ${token}` }
  })
  if (!res.ok) {
    throw new Error(`subjects list ${res.status}`)
  }
  const rows = await res.json()
  return (Array.isArray(rows) ? rows : []).some(c => `${c.name || ''}`.includes(courseNameSubstring))
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
    const t = await res.text()
    throw new Error(`login failed ${res.status}: ${t}`)
  }
  const data = await res.json()
  return data.access_token
}

async function apiHomeworkTitlesForSubject(token, subjectId) {
  const url = new URL(`${apiBase()}/api/homeworks`)
  url.searchParams.set('subject_id', String(subjectId))
  url.searchParams.set('page_size', '100')
  const res = await fetch(url.toString(), {
    headers: { Authorization: `Bearer ${token}` }
  })
  if (!res.ok) {
    throw new Error(`homeworks list ${res.status}`)
  }
  const data = await res.json()
  return (data.data || []).map(h => h.title)
}

test.describe('E2E scenarios: boundary / dynamic / complex', () => {
  test.describe.configure({ timeout: 300_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e/.cache/scenario.json - run with Playwright globalSetup (E2E_DEV_SEED_TOKEN)')
    }
  })

  test('boundary: first staff home load after login shows seeded teaching context', async ({ page }) => {
    const s = scenario()
    await login(page, s.teacher_own.username, s.teacher_own.password)
    await page.goto('/students')
    await expect(page.locator('.layout-container')).toBeVisible({ timeout: 15000 })
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto('/homework')
    await expect(page.getByRole('cell', { name: new RegExp(`E2E_UI作业_${s.suffix}`) })).toBeVisible({
      timeout: 20000
    })
  })

  test('boundary: admin creates a course with schedule then deletes it (UI + list consistency)', async ({
    page
  }) => {
    const s = scenario()
    const u = `e2e_del_${s.suffix}`
    await login(page, s.admin.username, s.admin.password)
    const adminTok = await obtainAccessToken(s.admin.username, s.admin.password)
    const createdApi = await apiPostJson('/api/subjects', adminTok, {
      name: `E2E待删课_${u}`,
      class_id: s.class_id_1,
      teacher_id: s.teacher_user_id,
      course_type: 'required',
      status: 'active'
    })
    const created = { id: createdApi.id }

    await expect
      .poll(async () => {
        const tok = await obtainAccessToken(s.admin.username, s.admin.password)
        const res = await page.request.get(`${apiBase()}/api/subjects`, {
          headers: { Authorization: `Bearer ${tok}` }
        })
        if (!res.ok()) {
          return false
        }
        const rows = await res.json()
        return Array.isArray(rows) && rows.some(c => `${c.name || ''}`.includes(`E2E待删课_${u}`))
      }, { timeout: 60000 })
      .toBe(true)

    await page.goto('/subjects', { waitUntil: 'load', timeout: 120000 })
    const delPromise = page.waitForResponse(
      r =>
        r.url().includes(`/api/subjects/${created.id}`) &&
        r.request().method() === 'DELETE' &&
        !r.url().includes('/students/'),
      { timeout: 120000 }
    )
    await page.getByTestId(`subjects-delete-${created.id}`).click({ force: true })
    await confirmMessageBox(page)
    const delResp = await delPromise
    expect(delResp.ok()).toBeTruthy()

    await page.goto('/subjects', { waitUntil: 'load', timeout: 60000 })
    await expect(page.getByTestId(`subjects-delete-${created.id}`)).toHaveCount(0, { timeout: 30000 })
  })

  test('boundary: admin creates a new student user aligned to class', async ({ page }) => {
    const s = scenario()
    const uname = `e2e_newstu_${s.suffix}_${Date.now()}`
    const adminTok = await obtainAccessToken(s.admin.username, s.admin.password)
    await apiPostJson('/api/users', adminTok, {
      username: uname,
      password: s.password_teacher_student,
      real_name: 'E2E新建学生',
      role: 'student',
      class_id: s.class_id_1
    })

    await login(page, s.admin.username, s.admin.password)
    await page.goto('/users', { waitUntil: 'load', timeout: 120000 })
    await expect(page.locator('tbody tr').filter({ hasText: uname })).toHaveCount(1, { timeout: 120000 })
  })

  test('dynamic: teacher publishes homework; student sees it; API list matches', async ({ page }) => {
    const s = scenario()
    const title = `E2E动态作业_${s.suffix}_${Date.now()}`
    await login(page, s.teacher_own.username, s.teacher_own.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto('/homework')
    await page.getByTestId('homework-btn-create').click()
    await expect(page.getByRole('dialog', { name: '发布作业' })).toBeVisible()
    await page.getByTestId('homework-form-title').fill(title)
    await page.getByTestId('homework-form-save').click()
    await expect(page.getByRole('dialog', { name: '发布作业' })).toBeHidden({ timeout: 25000 })
    await expect(page.getByRole('cell', { name: title })).toBeVisible({ timeout: 15000 })

    const tok = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const titles = await apiHomeworkTitlesForSubject(tok, s.course_required_id)
    expect(titles.some(t => t === title)).toBeTruthy()

    await login(page, s.student_plain.username, s.student_plain.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto('/homework')
    await expect(page.getByRole('row', { name: new RegExp(title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) })).toBeVisible({
      timeout: 20000
    })
  })

  test('dynamic: student updates display name; persists after reload', async ({ page }) => {
    const s = scenario()
    const newName = `E2E改名_${s.suffix}`
    await login(page, s.student_plain.username, s.student_plain.password)
    await page.goto('/personal-settings')
    await page.getByTestId('personal-profile-real-name').fill(newName)
    await page.getByTestId('personal-profile-save').click()
    await expect(page.getByText('已保存').first()).toBeVisible({ timeout: 10000 })
    await page.reload()
    await expect(page.getByTestId('personal-profile-real-name')).toHaveValue(newName, { timeout: 15000 })
  })

  test('complex: teacher publishes -> student sees -> teacher renames -> student sees new title (API check)', async ({
    page
  }) => {
    const s = scenario()
    const t1 = `E2E复杂A_${s.suffix}`
    const t2 = `E2E复杂B_${s.suffix}`
    await login(page, s.teacher_own.username, s.teacher_own.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto('/homework')
    await page.getByTestId('homework-btn-create').click()
    await page.getByTestId('homework-form-title').fill(t1)
    await page.getByTestId('homework-form-save').click()
    await expect(page.getByRole('dialog', { name: '发布作业' })).toBeHidden({ timeout: 25000 })

    await login(page, s.student_plain.username, s.student_plain.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto('/homework')
    await expect(page.getByRole('row', { name: t1 })).toBeVisible({ timeout: 20000 })

    await login(page, s.teacher_own.username, s.teacher_own.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto('/homework')
    const editRow = page.getByRole('row', { name: t1 })
    await editRow.getByTestId('homework-btn-edit').click()
    await page.getByTestId('homework-form-title').fill(t2)
    await page.getByTestId('homework-form-save').click()
    await expect(page.getByRole('dialog', { name: '编辑作业' })).toBeHidden({ timeout: 25000 })

    const tok = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const titles = await apiHomeworkTitlesForSubject(tok, s.course_required_id)
    expect(titles.some(x => x === t2)).toBeTruthy()
    expect(titles.some(x => x === t1)).toBeFalsy()

    await login(page, s.student_plain.username, s.student_plain.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto('/homework')
    await expect(page.getByRole('row', { name: t2 })).toBeVisible({ timeout: 20000 })
    await expect(page.getByRole('row', { name: t1 })).toHaveCount(0)
  })

  test('complex: admin and teacher contexts - admin creates course; teacher sees new course card', async ({
    browser
  }) => {
    const s = scenario()
    const courseName = `E2E双角_${s.suffix}_${Date.now()}`
    const adminContext = await browser.newContext()
    const teacherContext = await browser.newContext()
    const adminPage = await adminContext.newPage()
    const teacherPage = await teacherContext.newPage()
    try {
      await login(adminPage, s.admin.username, s.admin.password)
      const adminTok = await obtainAccessToken(s.admin.username, s.admin.password)
      await apiPostJson('/api/subjects', adminTok, {
        name: courseName,
        class_id: s.class_id_1,
        teacher_id: s.teacher_user_id,
        course_type: 'required',
        status: 'active'
      })

      await login(teacherPage, s.teacher_own.username, s.teacher_own.password)
      const tok = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
      await expect
        .poll(async () => apiCourseExistsForTeacher(tok, courseName), { timeout: 30_000 })
        .toBeTruthy()
      await teacherPage.goto('/courses')
      await expect(
        teacherPage.locator('article.course-card').filter({ has: teacherPage.getByRole('heading', { name: courseName }) })
      ).toBeVisible({ timeout: 20000 })
    } finally {
      await adminContext.close().catch(() => {})
      await teacherContext.close().catch(() => {})
    }
  })
})
