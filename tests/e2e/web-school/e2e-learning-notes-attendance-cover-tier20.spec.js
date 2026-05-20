/**
 * Twenty additive E2E checks for newer surfaces that felt under-tested:
 * learning-note visibility/copy/edit/discussion, course cover card visibility,
 * and attendance-owned teaching-calendar routing.
 *
 * Run from apps/web/school:
 *   npx playwright test e2e-learning-notes-attendance-cover-tier20.spec.js --project=chromium
 */
const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario } = require('./fixtures.cjs')
const {
  apiBase,
  apiGetJson,
  apiJson,
  apiPostJson,
  apiPutJson,
  login,
  obtainAccessToken
} = require('./future-advanced-coverage-helpers.cjs')

const scenario = () => loadE2eScenario()
const tinyCover =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="160" height="90"><rect width="160" height="90" fill="#0f766e"/><text x="18" y="52" fill="white" font-size="22">E2E</text></svg>')

async function rawJson(method, pathname, { token, body } = {}) {
  const res = await fetch(`${apiBase()}${pathname}`, {
    method,
    headers: {
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: body === undefined ? undefined : JSON.stringify(body)
  })
  const text = await res.text()
  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }
  return { status: res.status, data, text }
}

async function createNote(token, payload = {}) {
  return apiPostJson('/api/learning-notes', token, {
    title: payload.title || `ln-${Date.now()}`,
    description: payload.description || null,
    subject_id: payload.subject_id ?? null,
    visibility: payload.visibility || 'private',
    copy_from_subject_id: payload.copy_from_subject_id ?? null,
    copy_chapters: payload.copy_chapters || false,
    copy_materials: payload.copy_materials || false
  })
}

async function publicNoteIds(token, params = '') {
  const data = await apiGetJson(`/api/learning-notes?scope=public${params}`, token)
  return new Set((data.data || []).map(row => row.id))
}

test.describe('learning notes, cover cards, attendance-calendar tier (20)', () => {
  test.describe.configure({ timeout: 300_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e seed; set E2E_DEV_SEED_TOKEN and globalSetup')
    }
  })

  test('01 private note is mine-only and hidden from public list', async () => {
    const s = scenario()
    const owner = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const peer = await obtainAccessToken(s.student_b.username, s.password_teacher_student)
    const note = await createNote(owner, { title: `ln-private-${s.suffix}` })
    const mine = await apiGetJson('/api/learning-notes?scope=mine', owner)
    expect((mine.data || []).some(row => row.id === note.id)).toBeTruthy()
    expect(await publicNoteIds(peer)).not.toContain(note.id)
    const blocked = await rawJson('GET', `/api/learning-notes/${note.id}`, { token: peer })
    expect(blocked.status).toBe(403)
  })

  test('02 public unbound note is visible to another authenticated course outsider', async () => {
    const s = scenario()
    const owner = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const outsider = await obtainAccessToken(s.teacher_other.username, s.password_teacher_student)
    const note = await createNote(owner, { title: `ln-global-${s.suffix}`, visibility: 'course' })
    expect(await publicNoteIds(outsider)).toContain(note.id)
    const detail = await apiGetJson(`/api/learning-notes/${note.id}`, outsider)
    expect(detail.subject_id).toBeNull()
  })

  test('03 course-bound public note is readable by same-course peer', async () => {
    const s = scenario()
    const owner = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const peer = await obtainAccessToken(s.student_b.username, s.password_teacher_student)
    const note = await createNote(owner, {
      title: `ln-course-${s.suffix}`,
      visibility: 'course',
      subject_id: s.course_required_id
    })
    const detail = await apiGetJson(`/api/learning-notes/${note.id}`, peer)
    expect(detail.id).toBe(note.id)
  })

  test('04 course-bound public note is not readable by unrelated teacher', async () => {
    const s = scenario()
    const owner = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const outsider = await obtainAccessToken(s.teacher_other.username, s.password_teacher_student)
    const note = await createNote(owner, {
      title: `ln-course-outsider-${s.suffix}`,
      visibility: 'course',
      subject_id: s.course_required_id
    })
    const blocked = await rawJson('GET', `/api/learning-notes/${note.id}`, { token: outsider })
    expect(blocked.status).toBe(403)
  })

  test('05 public list with subject filter excludes unbound public notes', async () => {
    const s = scenario()
    const owner = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const unbound = await createNote(owner, { title: `ln-global-filter-${s.suffix}`, visibility: 'course' })
    const bound = await createNote(owner, {
      title: `ln-bound-filter-${s.suffix}`,
      visibility: 'course',
      subject_id: s.course_required_id
    })
    const ids = await publicNoteIds(owner, `&subject_id=${s.course_required_id}`)
    expect(ids).toContain(bound.id)
    expect(ids).not.toContain(unbound.id)
  })

  test('06 owner can clear subject binding and make the public note global', async () => {
    const s = scenario()
    const owner = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const outsider = await obtainAccessToken(s.teacher_other.username, s.password_teacher_student)
    const note = await createNote(owner, {
      title: `ln-clear-${s.suffix}`,
      visibility: 'course',
      subject_id: s.course_required_id
    })
    const updated = await apiPutJson(`/api/learning-notes/${note.id}`, owner, { subject_id: null })
    expect(updated.subject_id).toBeNull()
    expect(await publicNoteIds(outsider)).toContain(note.id)
  })

  test('07 copy course outline without materials creates chapters and no resources', async () => {
    const s = scenario()
    const owner = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const note = await createNote(owner, {
      title: `ln-copy-chapters-${s.suffix}`,
      copy_from_subject_id: s.course_required_id,
      copy_chapters: true,
      copy_materials: false
    })
    expect(note.chapters.length).toBeGreaterThanOrEqual(1)
    const resources = JSON.stringify(note.chapters)
    expect(resources).not.toContain('source_material_id')
  })

  test('08 copy course outline with materials creates note resource snapshots', async () => {
    const s = scenario()
    const owner = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const note = await createNote(owner, {
      title: `ln-copy-materials-${s.suffix}`,
      copy_from_subject_id: s.course_required_id,
      copy_chapters: true,
      copy_materials: true
    })
    expect(JSON.stringify(note.chapters)).toContain('source_material_id')
    expect(note.copied_materials).toBeTruthy()
  })

  test('09 copied resource can be edited and detached from its copied chapter', async () => {
    const s = scenario()
    const owner = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const note = await createNote(owner, {
      title: `ln-resource-detach-${s.suffix}`,
      copy_from_subject_id: s.course_required_id,
      copy_chapters: true,
      copy_materials: true
    })
    const resource = note.chapters.flatMap(ch => ch.resources.concat((ch.children || []).flatMap(c => c.resources)))[0]
    expect(resource).toBeTruthy()
    const updated = await apiPutJson(`/api/learning-notes/${note.id}/resources/${resource.id}`, owner, {
      chapter_id: null,
      title: `loose-${s.suffix}`,
      attachment_name: null,
      attachment_url: null
    })
    expect(updated.loose_resources.some(row => row.id === resource.id && row.chapter_id === null)).toBeTruthy()
  })

  test('10 copied child chapter can be promoted to root', async () => {
    const s = scenario()
    const owner = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const note = await createNote(owner, { title: `ln-chapter-root-${s.suffix}` })
    const parent = await apiJson(`/api/learning-notes/${note.id}/chapters`, {
      method: 'POST',
      token: owner,
      body: { title: `parent-${s.suffix}` }
    })
    const child = await apiJson(`/api/learning-notes/${note.id}/chapters`, {
      method: 'POST',
      token: owner,
      body: { title: `child-${s.suffix}`, parent_id: parent.id }
    })
    const updated = await apiPutJson(`/api/learning-notes/${note.id}/chapters/${child.id}`, owner, { parent_id: null })
    expect(updated.chapters.some(row => row.id === child.id)).toBeTruthy()
  })

  test('11 non-owner cannot mutate public note metadata', async () => {
    const s = scenario()
    const owner = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const peer = await obtainAccessToken(s.student_b.username, s.password_teacher_student)
    const note = await createNote(owner, { visibility: 'course', subject_id: s.course_required_id })
    const blocked = await rawJson('PUT', `/api/learning-notes/${note.id}`, { token: peer, body: { title: 'bad' } })
    expect(blocked.status).toBe(403)
  })

  test('12 non-owner cannot add resources to public note', async () => {
    const s = scenario()
    const owner = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const peer = await obtainAccessToken(s.student_b.username, s.password_teacher_student)
    const note = await createNote(owner, { visibility: 'course', subject_id: s.course_required_id })
    const blocked = await rawJson('POST', `/api/learning-notes/${note.id}/resources`, {
      token: peer,
      body: { title: 'bad resource' }
    })
    expect(blocked.status).toBe(403)
  })

  test('13 private note discussion is owner-only', async () => {
    const s = scenario()
    const owner = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const peer = await obtainAccessToken(s.student_b.username, s.password_teacher_student)
    const note = await createNote(owner, { title: `ln-private-discussion-${s.suffix}` })
    const blocked = await rawJson('GET', `/api/learning-notes/${note.id}/discussion`, { token: peer })
    expect(blocked.status).toBe(403)
  })

  test('14 global public note accepts comments from any authenticated user and exposes author metadata', async () => {
    const s = scenario()
    const owner = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const commenter = await obtainAccessToken(s.teacher_other.username, s.password_teacher_student)
    const note = await createNote(owner, { visibility: 'course', title: `ln-global-discussion-${s.suffix}` })
    const entry = await apiPostJson(`/api/learning-notes/${note.id}/discussion`, commenter, {
      body: 'teacher-other comment',
      body_format: 'plain'
    })
    expect(entry.author_username).toBe(s.teacher_other.username)
    const list = await apiGetJson(`/api/learning-notes/${note.id}/discussion`, owner)
    expect(list.total).toBe(1)
    expect(list.data[0].body_format).toBe('plain')
  })

  test('15 discussion page_size above 100 rejects with 422', async () => {
    const s = scenario()
    const owner = await obtainAccessToken(s.student_plain.username, s.password_teacher_student)
    const note = await createNote(owner, { visibility: 'course' })
    const st = await rawJson('GET', `/api/learning-notes/${note.id}/discussion?page_size=101`, { token: owner })
    expect(st.status).toBe(422)
  })

  test('16 learning notes page renders mine and public tabs for student', async ({ page }) => {
    const s = scenario()
    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.goto('/learning-notes')
    await expect(page.getByRole('heading', { name: '学习笔记' })).toBeVisible()
    await expect(page.getByRole('tab', { name: '我的笔记' })).toBeVisible()
    await expect(page.getByRole('tab', { name: '公开笔记' })).toBeVisible()
    await expect(page.getByRole('button', { name: '新建笔记' })).toBeVisible()
  })

  test('17 learning notes UI defaults new note dialog to private', async ({ page }) => {
    const s = scenario()
    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.goto('/learning-notes')
    await page.getByRole('button', { name: '新建笔记' }).click()
    const dialog = page.getByRole('dialog', { name: /新建学习笔记/ })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole('radio', { name: '仅本人可见' })).toBeChecked()
  })

  test('18 course catalog and active course cards render cover image when course has cover URL', async ({ page }) => {
    const s = scenario()
    const admin = await obtainAccessToken(s.admin.username, s.password_admin)
    await apiPutJson(`/api/subjects/${s.course_required_id}`, admin, { cover_image_url: tinyCover })
    await login(page, s.student_plain.username, s.password_teacher_student)
    await page.goto('/courses')
    const card = page.locator('article.course-card').filter({ has: page.getByRole('heading', { name: `E2E必修课_${s.suffix}` }) })
    await expect(card.getByTestId('course-card-cover')).toBeVisible({ timeout: 15000 })
  })

  test('19 /teaching-calendar redirects to attendance and embeds teaching calendar', async ({ page }) => {
    const s = scenario()
    await login(page, s.teacher_own.username, s.password_teacher_student)
    await page.goto('/teaching-calendar')
    await expect(page).toHaveURL(/\/attendance/)
    await expect(page.locator('.attendance-page .teaching-calendar')).toBeVisible({ timeout: 15000 })
  })

  test('20 attendance API can create course-scoped record and filter by selected date/course', async () => {
    const s = scenario()
    const teacher = await obtainAccessToken(s.teacher_own.username, s.password_teacher_student)
    const date = '2026-05-07'
    const created = await apiJson('/api/attendance', {
      method: 'POST',
      token: teacher,
      body: {
        student_id: s.student_plain.student_row_id,
        class_id: s.class_id_1,
        subject_id: s.course_required_id,
        date,
        status: 'late',
        remark: 'calendar-linked'
      }
    })
    expect(created.subject_id).toBe(s.course_required_id)
    const list = await apiGetJson(
      `/api/attendance?subject_id=${s.course_required_id}&start_date=${date}&end_date=${date}`,
      teacher
    )
    expect((list.data || []).some(row => row.id === created.id && row.status === 'late')).toBeTruthy()
  })
})
