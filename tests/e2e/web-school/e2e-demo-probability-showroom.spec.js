const { expect, test } = require('@playwright/test')
const { login, obtainAccessToken, apiGetJson } = require('./future-advanced-coverage-helpers.cjs')

const demoEnabled = ['1', 'true', 'yes', 'on'].includes(
  String(process.env.DEMO_SHOWROOM_ENABLED || '').trim().toLowerCase()
)

const teacherUsername = process.env.DEMO_SHOWROOM_TEACHER || 'teacher_pro'
const teacherPassword = process.env.DEMO_SHOWROOM_TEACHER_PASSWORD || 'teacher_pro'
const studentUsername = process.env.DEMO_SHOWROOM_STUDENT || 'stu2'
const studentPassword = process.env.DEMO_SHOWROOM_STUDENT_PASSWORD || '111111'
const courseName = process.env.DEMO_SHOWROOM_COURSE_NAME || '初等概率论'
const homeworkOneTitle = process.env.DEMO_SHOWROOM_HOMEWORK_ONE || '初等概率论第一次作业：古典概型与 Bayes 计算'
const homeworkTwoTitle = process.env.DEMO_SHOWROOM_HOMEWORK_TWO || '初等概率论第二次作业：离散分布建模与事件树表达'
const noteTitle = process.env.DEMO_SHOWROOM_NOTE_TITLE || 'Bayes 公式课堂笔记'
const teacherNoteTitle = process.env.DEMO_SHOWROOM_TEACHER_NOTE_TITLE || '概率论课备课札记：Bayes 单元组织'
const readerMaterialTitle = process.env.DEMO_SHOWROOM_READER_MATERIAL || '阅读页样板：从先验、似然到后验的完整说明'

async function screenshot(page, testInfo, name) {
  const output = testInfo.outputPath(`${name}.png`)
  await page.screenshot({ path: output, fullPage: true })
  await testInfo.attach(name, { path: output, contentType: 'image/png' })
}

async function subjectIdByName(token, name) {
  const rows = await apiGetJson('/api/subjects', token)
  const hit = (rows || []).find(row => String(row.name || '') === String(name))
  if (!hit) {
    throw new Error(`subject not found: ${name}`)
  }
  return Number(hit.id)
}

async function homeworkIdByTitle(token, subjectId, title) {
  const data = await apiGetJson(`/api/homeworks?subject_id=${subjectId}&page=1&page_size=100`, token)
  const hit = (data.data || []).find(row => String(row.title || '') === String(title))
  if (!hit) {
    throw new Error(`homework not found: ${title}`)
  }
  return Number(hit.id)
}

async function materialIdByTitle(token, subjectId, title) {
  const data = await apiGetJson(`/api/materials?subject_id=${subjectId}&page=1&page_size=100`, token)
  const hit = (data.data || []).find(row => String(row.title || '') === String(title))
  if (!hit) {
    throw new Error(`material not found: ${title}`)
  }
  return Number(hit.id)
}

async function openCourseCard(page, headingText) {
  await page.goto('/courses', { waitUntil: 'domcontentloaded', timeout: 60000 })
  const card = page.locator('article.course-card').filter({ has: page.getByRole('heading', { name: headingText }) }).first()
  await expect(card).toBeVisible({ timeout: 20000 })
  await card.getByRole('button', { name: /进入课程|查看课程/ }).click()
}

test.describe('demo probability showroom', () => {
  test.describe.configure({ timeout: 300_000 })

  test.beforeEach(async ({}, testInfo) => {
    if (!demoEnabled) {
      testInfo.skip(true, 'Set DEMO_SHOWROOM_ENABLED=1 and run against a backend with INIT_DEFAULT_DATA=true.')
    }
  })

  test('teacher and student perspectives render the richer probability demo course', async ({ browser }, testInfo) => {
    const teacherToken = await obtainAccessToken(teacherUsername, teacherPassword)
    await obtainAccessToken(studentUsername, studentPassword)
    const subjectId = await subjectIdByName(teacherToken, courseName)
    const homeworkOneId = await homeworkIdByTitle(teacherToken, subjectId, homeworkOneTitle)
    const homeworkTwoId = await homeworkIdByTitle(teacherToken, subjectId, homeworkTwoTitle)
    const readerMaterialId = await materialIdByTitle(teacherToken, subjectId, readerMaterialTitle)

    const teacherPage = await browser.newPage()
    await login(teacherPage, teacherUsername, teacherPassword)
    await teacherPage.goto('/materials', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(teacherPage.getByText(courseName).first()).toBeVisible({ timeout: 20000 })
    await screenshot(teacherPage, testInfo, 'demo-probability-teacher-materials')

    await teacherPage.goto(`/homework/${homeworkOneId}/submissions`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(teacherPage.getByRole('heading', { name: '学生提交' })).toBeVisible({ timeout: 20000 })
    await expect(teacherPage.getByText('提交情况').first()).toBeVisible({ timeout: 20000 })
    await screenshot(teacherPage, testInfo, 'demo-probability-teacher-submissions')

    await teacherPage.goto('/learning-notes', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(teacherPage.locator('.note-card').filter({ hasText: teacherNoteTitle }).first()).toBeVisible({ timeout: 20000 })
    await teacherPage.locator('.note-card').filter({ hasText: teacherNoteTitle }).first().click()
    await screenshot(teacherPage, testInfo, 'demo-probability-teacher-note')

    const studentPage = await browser.newPage()
    await login(studentPage, studentUsername, studentPassword)
    await openCourseCard(studentPage, courseName)
    await screenshot(studentPage, testInfo, 'demo-probability-student-course-home')

    await studentPage.goto('/materials', { waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(studentPage.getByText('第一单元：概率空间、事件与计数方法').first()).toBeVisible({ timeout: 20000 })
    await expect(studentPage.getByText('第二单元：条件概率、全概率公式与 Bayes 推断').first()).toBeVisible({ timeout: 20000 })
    await screenshot(studentPage, testInfo, 'demo-probability-student-materials')
    await studentPage.goto(`/materials/read/${readerMaterialId}`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(studentPage.getByText('Bayes 推断的阅读页样板').first()).toBeVisible({ timeout: 20000 })
    await expect(studentPage.locator('.material-read-prose .md-card--example')).toBeVisible({ timeout: 20000 })
    await expect(studentPage.locator('.material-read-prose .md-card--pricing')).toBeVisible({ timeout: 20000 })
    await expect(studentPage.locator('.material-read-prose .md-card--note')).toBeVisible({ timeout: 20000 })
    await expect(studentPage.locator('.material-read-prose .md-card--warning')).toBeVisible({ timeout: 20000 })
    await expect(studentPage.locator('.material-read-prose .md-card--danger')).toBeVisible({ timeout: 20000 })
    await screenshot(studentPage, testInfo, 'demo-probability-student-reader-page')

    await studentPage.goto(`/homework/${homeworkOneId}/submit`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(studentPage.getByText('有效成绩与评语（截止前/计入总评取最高）').first()).toBeVisible({ timeout: 20000 })
    await screenshot(studentPage, testInfo, 'demo-probability-student-homework-one')

    await studentPage.goto(`/homework/${homeworkTwoId}/submit`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    await expect(studentPage.getByText('第二次作业：离散分布建模与事件树表达').first()).toBeVisible({ timeout: 20000 })
    await expect(studentPage.getByText('提交作业').first()).toBeVisible({ timeout: 20000 })
    await screenshot(studentPage, testInfo, 'demo-probability-student-homework-two')

    await studentPage.goto('/learning-notes', { waitUntil: 'domcontentloaded', timeout: 60000 })
    const noteCard = studentPage.locator('.note-card').filter({ hasText: noteTitle }).first()
    await expect(noteCard).toBeVisible({ timeout: 20000 })
    await noteCard.click()
    await screenshot(studentPage, testInfo, 'demo-probability-student-note')
  })
})
