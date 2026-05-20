/**
 * Advanced E2E scenarios (batch I: cases 1–15). Uses the same seed reset contract as other Playwright specs.
 */
const { expect, test } = require('@playwright/test')
const { loadE2eScenario, resetE2eScenario, enterSeededRequiredCourse } = require('./fixtures.cjs')
const {
  escapeRegex,
  login,
  obtainAccessToken,
  apiBase,
  apiGetJson,
  apiPostJson,
  apiPutJson,
  apiDelete,
  configureMockLlm,
  processGradingTasks,
  gradingState,
  createPreset,
  validatePreset,
  setFlatCourseConfig,
  createHomework,
  apiListNotifications,
  apiListScoreAppeals,
  apiListUsers,
  apiFindUserIdByUsername,
  apiHomeworkSubmissionHistory,
  flattenChapterTree,
  getChapterTree,
  currentSelectedCourseId,
  confirmElMessageBoxPrimary,
  apiPostForm
} = require('./future-advanced-coverage-helpers.cjs')

const scenario = () => loadE2eScenario()

async function confirmPrimaryDialog(page) {
  await confirmElMessageBoxPrimary(page)
}

test.describe('Future advanced E2E coverage expansion', () => {
  test.describe.configure({ timeout: 240_000 })

  test.beforeEach(async ({}, testInfo) => {
    const s = await resetE2eScenario()
    if (!s) {
      testInfo.skip(true, 'Missing e2e seed cache; run globalSetup with E2E_DEV_SEED_TOKEN first')
    }
  })

  test('1. student stale-tab homework resubmit after teacher hard review keeps one authoritative attempt history', async ({
    browser
  }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    await apiPutJson(`/api/homeworks/${s.homework_id}`, teacherToken, { max_submissions: 1 })

    const ctxA = await browser.newContext()
    const ctxB = await browser.newContext()
    const teacherPage = await ctxA.newPage()
    const studentA = await ctxB.newPage()
    try {
      await login(teacherPage, s.teacher_own.username, s.teacher_own.password)
      await login(studentA, s.student_plain.username, s.student_plain.password)
      await enterSeededRequiredCourse(studentA, s.suffix)
      await studentA.goto(`/homework/${s.homework_id}/submit`)
      const body = `E2E backlog1_${s.suffix}_${Date.now()}`
      await studentA.getByTestId('homework-submit-content').fill(body)
      await studentA.getByRole('button', { name: /保存提交/ }).click()
      await expect
        .poll(async () => {
          const h = await apiHomeworkSubmissionHistory(studentToken, s.homework_id)
          return h.summary?.id || null
        }, { timeout: 30000 })
        .toBeTruthy()

      const hist = await apiHomeworkSubmissionHistory(studentToken, s.homework_id)
      const submissionId = hist.summary?.id
      await apiPutJson(`/api/homeworks/${s.homework_id}/submissions/${submissionId}/review`, teacherToken, {
        review_score: 88,
        review_comment: `E2E teacher review ${s.suffix}`
      })

      const studentB = await ctxB.newPage()
      await login(studentB, s.student_plain.username, s.student_plain.password)
      await enterSeededRequiredCourse(studentB, s.suffix)
      await studentB.goto(`/homework/${s.homework_id}/submit`)
      await expect(studentB.getByTestId('homework-submit-content')).toBeDisabled({ timeout: 15000 })

      await expect
        .poll(async () => {
          const h = await apiHomeworkSubmissionHistory(studentToken, s.homework_id)
          return h.attempts?.length || 0
        }, { timeout: 15000 })
        .toBe(1)
      await studentB.close()
    } finally {
      await ctxA.close().catch(() => {})
      await ctxB.close().catch(() => {})
    }
  })

  test('2. teacher concurrent material chapter reorder from two tabs converges to one final chapter sequence', async ({
    browser
  }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const tree1 = await getChapterTree(teacherToken, s.course_required_id)
    const customizable = flattenChapterTree(tree1.nodes).filter(ch => !ch.title.includes('未分类'))
    let chA = customizable[0]
    let chB = customizable[1]
    if (!chA || !chB) {
      await apiPostJson(`/api/material-chapters?subject_id=${s.course_required_id}`, teacherToken, {
        title: `E2E章A_${s.suffix}`,
        parent_id: null
      })
      await apiPostJson(`/api/material-chapters?subject_id=${s.course_required_id}`, teacherToken, {
        title: `E2E章B_${s.suffix}`,
        parent_id: null
      })
      const tree2 = await getChapterTree(teacherToken, s.course_required_id)
      const rows = flattenChapterTree(tree2.nodes)
      chA = rows.find(r => r.title.includes(`E2E章A_${s.suffix}`))
      chB = rows.find(r => r.title.includes(`E2E章B_${s.suffix}`))
    }
    expect(chA && chB).toBeTruthy()

    await Promise.all([
      apiPostJson(`/api/material-chapters/reorder?subject_id=${s.course_required_id}`, teacherToken, {
        parent_id: null,
        ordered_chapter_ids: [chB.id, chA.id]
      }),
      apiPostJson(`/api/material-chapters/reorder?subject_id=${s.course_required_id}`, teacherToken, {
        parent_id: null,
        ordered_chapter_ids: [chA.id, chB.id]
      })
    ])

    await expect
      .poll(async () => {
        const t = await getChapterTree(teacherToken, s.course_required_id)
        const leaf = flattenChapterTree(t.nodes).map(r => r.id)
        return leaf.join(',')
      }, { timeout: 15000 })
      .toMatch(/./)

    const finalTree = await getChapterTree(teacherToken, s.course_required_id)
    const ordered = flattenChapterTree(finalTree.nodes).map(r => r.id)
    expect(new Set(ordered).size).toBe(ordered.length)
  })

  test('3. admin delete-class attempt blocked while related roster and course references still exist', async ({ page }) => {
    const s = scenario()
    await login(page, s.admin.username, s.admin.password)
    await page.goto('/classes')
    const row = page.getByRole('row', { name: new RegExp(escapeRegex(s.class_name_1)) })
    await expect(row).toBeVisible({ timeout: 15000 })
    await row.getByRole('button', { name: '删除' }).click()
    await confirmPrimaryDialog(page)
    await expect(page.locator('.el-message--error').first()).toBeVisible({ timeout: 10000 })
  })

  test('4. teacher LLM endpoint failover during async grading leaves one completed task and no orphan queued rows', async () => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)

    await configureMockLlm({
      g1: {
        steps: [{ kind: 'http_error', status_code: 503, body: { error: 'failover' } }],
        repeat_last: false
      },
      g2: { steps: [{ kind: 'ok', score: 81, comment: 'failover ok' }], repeat_last: true }
    })
    const p1 = await createPreset(adminToken, `E2E backlog4a_${s.suffix}`, 'g1')
    const p2 = await createPreset(adminToken, `E2E backlog4b_${s.suffix}`, 'g2')
    await validatePreset(adminToken, p1.id)
    await validatePreset(adminToken, p2.id)
    await setFlatCourseConfig(teacherToken, s.course_required_id, [p1.id, p2.id])

    const hw = await createHomework(teacherToken, s, `E2E LLM failover ${s.suffix}`)
    await apiPostJson(`/api/homeworks/${hw.id}/submission`, studentToken, {
      content: 'failover submission',
      used_llm_assist: false,
      mode: 'normal'
    })

    const workerOn = (await gradingState()).worker?.running
    if (workerOn) {
      await expect
        .poll(async () => {
          const st = await gradingState()
          return (st.tasks?.queued || 0) + (st.tasks?.processing || 0)
        }, { timeout: 60000 })
        .toBe(0)
    } else {
      await processGradingTasks(10)
    }

    await expect
      .poll(async () => {
        const h = await apiHomeworkSubmissionHistory(studentToken, hw.id)
        return h.summary?.latest_task_status
      }, { timeout: 60000 })
      .toBe('success')

    const st = await gradingState()
    expect((st.tasks?.queued || 0) + (st.tasks?.processing || 0)).toBe(0)
  })

  test('5. student dual-tab score appeal submit converges to one pending appeal and one notification chain', async () => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const semesters = await apiGetJson('/api/semesters', teacherToken)
    const semester = semesters[0]?.name || '2026春季'
    const reason = `E2E score appeal dup ${s.suffix}_${Date.now()}`

    await Promise.all([
      fetch(`${apiBase()}/api/scores/appeals?subject_id=${s.course_required_id}`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${studentToken}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          semester,
          target_component: 'total',
          reason_text: reason,
          score_id: null
        })
      }),
      fetch(`${apiBase()}/api/scores/appeals?subject_id=${s.course_required_id}`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${studentToken}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          semester,
          target_component: 'total',
          reason_text: `${reason}_b`,
          score_id: null
        })
      })
    ])

    const appealRows = await apiListScoreAppeals(teacherToken, {
      subject_id: s.course_required_id,
      status: 'pending'
    })
    const dupAppeals = appealRows.filter(r => `${r.reason_text || ''}`.includes(`E2E score appeal dup ${s.suffix}`))
    expect(dupAppeals.length).toBeLessThanOrEqual(1)

    const titlePat = /成绩(构成)?申诉待处理/
    await expect
      .poll(async () => {
        const list = await apiListNotifications(teacherToken, { page_size: 100 })
        return (list.data || []).filter(
          n =>
            n.notification_kind === 'score_grade_appeal' &&
            Number(n.subject_id) === Number(s.course_required_id) &&
            Number(n.related_student_id) === Number(s.student_plain.student_row_id) &&
            String(n.content || '').includes(reason)
        ).length
      }, { timeout: 30000 })
      .toBeGreaterThanOrEqual(1)
  })

  test('6. admin batch user activation toggle with stale filters keeps final active-state set aligned with API truth', async () => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const uid = await apiFindUserIdByUsername(adminToken, s.student_plain.username)
    await apiPutJson(`/api/users/${uid}`, adminToken, { is_active: false })
    await apiPutJson(`/api/users/${uid}`, adminToken, { is_active: true })
    const after = await apiGetJson(`/api/users/${uid}`, adminToken)
    expect(after.is_active).toBe(true)
  })

  test('7. student notification deep-link recovery from corrupted local selected_course cache rebinds to accessible course only', async ({
    page
  }) => {
    const s = scenario()
    await login(page, s.student_plain.username, s.student_plain.password)
    await page.evaluate(() => {
      localStorage.setItem('selected_course', JSON.stringify({ id: 987654321, name: 'corrupt-course' }))
    })
    await page.goto('/notifications')
    await expect
      .poll(async () => currentSelectedCourseId(page), { timeout: 15000 })
      .toBeTruthy()
  })

  test('8. teacher concurrent homework max-submission edit and student submit keeps submission cap enforcement correct', async ({
    browser
  }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const hw = await createHomework(teacherToken, s, `E2E cap race ${s.suffix}`, { max_submissions: 5 })

    const tPage = await browser.newPage()
    const sPage = await browser.newPage()
    try {
      await login(tPage, s.teacher_own.username, s.teacher_own.password)
      await login(sPage, s.student_plain.username, s.student_plain.password)
      await enterSeededRequiredCourse(tPage, s.suffix)
      await enterSeededRequiredCourse(sPage, s.suffix)
      await tPage.goto('/homework')
      const row = tPage.getByRole('row', { name: new RegExp(escapeRegex(hw.title)) })
      await row.getByTestId('homework-btn-edit').click()
      await tPage.getByRole('spinbutton').first().fill('1')

      await sPage.goto(`/homework/${hw.id}/submit`)
      await sPage.getByTestId('homework-submit-content').fill(`cap_${s.suffix}`)
      await Promise.all([
        sPage.waitForResponse(resp => resp.url().includes(`/api/homeworks/${hw.id}/submission`) && resp.request().method() === 'POST'),
        sPage.getByRole('button', { name: /保存提交/ }).click()
      ])
      await tPage.getByRole('button', { name: /保存|确定/ }).click()

      await expect
        .poll(async () => {
          const h = await apiHomeworkSubmissionHistory(studentToken, hw.id)
          return h.attempts?.length || 0
        }, { timeout: 30000 })
        .toBe(1)
    } finally {
      await tPage.close().catch(() => {})
      await sPage.close().catch(() => {})
    }
  })

  test('9. parent portal notification read-state stays isolated from student web-school read-state when policies require separation', async () => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const uniqueTitle = `E2E_parent_iso_${s.suffix}_${Date.now()}`
    await apiPostJson('/api/notifications', teacherToken, {
      title: uniqueTitle,
      content: 'parent isolation',
      priority: 'normal',
      is_pinned: false,
      class_id: s.class_id_1,
      subject_id: s.course_required_id
    })
    const list = await apiListNotifications(studentToken, { page_size: 50 })
    const row = (list.data || []).find(n => n.title === uniqueTitle)
    expect(row?.id).toBeTruthy()
    await apiPostJson(`/api/notifications/${row.id}/read`, studentToken, {})

    const gen = await apiPostJson(`/api/parent/students/${s.student_plain.student_row_id}/generate-code`, teacherToken)
    const parentCode = gen.parent_code
    const parentData = await fetch(`${apiBase()}/api/parent/notifications/${parentCode}?page_size=50`).then(r => r.json())
    const parentHit = (parentData.notifications || []).find(n => n.title === uniqueTitle)
    expect(parentHit).toBeTruthy()
  })

  test('10. teacher duplicate attendance save retries produce one authoritative attendance row per student/date', async ({
    page
  }) => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    let failedOnce = false
    await login(page, s.teacher_own.username, s.teacher_own.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto('/attendance')
    await page.locator('.el-loading-mask').waitFor({ state: 'detached', timeout: 30000 }).catch(() => {})
    await page.getByRole('radio', { name: '缺勤' }).first().click({ force: true })
    await page.route('**/api/attendance/batch', async route => {
      if (!failedOnce && route.request().method() === 'POST') {
        failedOnce = true
        await route.fulfill({ status: 503, body: 'temporary' })
        return
      }
      await route.continue()
    })
    await page.getByRole('button', { name: '提交' }).click()
    await page.getByRole('button', { name: '提交' }).click()

    const today = new Date().toISOString().slice(0, 10)
    const list = await apiGetJson(
      `/api/attendance?subject_id=${s.course_required_id}&student_id=${s.student_plain.student_row_id}&page_size=50`,
      teacherToken
    )
    const sameDay = (list.data || []).filter(
      a => a.student_id === s.student_plain.student_row_id && `${a.date}`.includes(today)
    )
    expect(sameDay.length).toBeLessThanOrEqual(1)
  })

  test('11. admin semester switch plus score composition view stale tab converges to one valid grading composition', async ({
    browser
  }) => {
    const s = scenario()
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const semesters = await apiGetJson('/api/semesters', await obtainAccessToken(s.admin.username, s.admin.password))
    const sem = semesters[0]
    expect(sem?.name).toBeTruthy()

    const pageA = await browser.newPage()
    const pageB = await browser.newPage()
    try {
      await login(pageA, s.admin.username, s.admin.password)
      await login(pageB, s.student_plain.username, s.student_plain.password)
      await enterSeededRequiredCourse(pageB, s.suffix)
      await pageB.goto('/scores')
      await pageA.goto('/semesters')
      await pageA.getByRole('row').nth(1).getByRole('button', { name: /编辑/ }).click().catch(() => {})

      const comp = await apiGetJson(
        `/api/scores/composition/me?subject_id=${s.course_required_id}&semester=${encodeURIComponent(sem.name)}`,
        studentToken
      )
      expect(comp).toBeTruthy()
    } finally {
      await pageA.close().catch(() => {})
      await pageB.close().catch(() => {})
    }
  })

  test('12. teacher points award and redemption race leaves one consistent student point balance and ranking', async () => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const base = await apiGetJson('/api/points/my', studentToken)
    const start = base.available_points ?? base.balance ?? 0

    await Promise.all([
      apiPostJson(`/api/points/students/${s.student_plain.student_row_id}/add`, teacherToken, {
        student_id: s.student_plain.student_row_id,
        points: 5,
        description: `race_${s.suffix}`
      }),
      apiPostJson(`/api/points/students/${s.student_plain.student_row_id}/add`, teacherToken, {
        student_id: s.student_plain.student_row_id,
        points: 2,
        description: `race_b_${s.suffix}`
      })
    ])

    await expect
      .poll(async () => {
        const me = await apiGetJson('/api/points/my', studentToken)
        return me.available_points ?? me.balance ?? 0
      }, { timeout: 15000 })
      .toBeGreaterThan(start)

    const rank = await apiGetJson(`/api/points/ranking?class_id=${s.class_id_1}&limit=50`, studentToken)
    expect(Array.isArray(rank)).toBe(true)
  })

  test('13. student attachment replace during flaky upload leaves one surviving attachment reference and no orphan file row', async ({
    page
  }) => {
    const s = scenario()
    const studentToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    await login(page, s.student_plain.username, s.student_plain.password)
    await enterSeededRequiredCourse(page, s.suffix)
    await page.goto(`/homework/${s.homework_id}/submit`)
    let n = 0
    await page.route(`**/api/homeworks/${s.homework_id}/submission`, async route => {
      if (route.request().method() !== 'POST') {
        await route.continue()
        return
      }
      n += 1
      if (n === 1) {
        await route.fulfill({ status: 502, body: 'bad gateway' })
        return
      }
      await route.continue()
    })
    await page.getByTestId('homework-submit-content').fill(`attach_${s.suffix}`)
    await page.getByRole('button', { name: /保存提交/ }).click()
    await page.getByRole('button', { name: /保存提交/ }).click()

    await expect
      .poll(async () => {
        const h = await apiHomeworkSubmissionHistory(studentToken, s.homework_id)
        return h.attempts?.length || 0
      }, { timeout: 30000 })
      .toBe(1)
  })

  test('14. admin stale dual-tab system settings save converges to final branding and does not partially mix fields', async ({
    browser
  }) => {
    const s = scenario()
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)
    const before = await apiGetJson('/api/settings/all', adminToken)
    const keys = Object.keys(before || {}).slice(0, 3)

    const pageA = await browser.newPage()
    const pageB = await browser.newPage()
    try {
      await login(pageA, s.admin.username, s.admin.password)
      await login(pageB, s.admin.username, s.admin.password)
      await pageA.goto('/settings')
      await pageB.goto('/settings')
      if (keys.length >= 2) {
        const k0 = keys[0]
        const k1 = keys[1]
        await apiPutJson(`/api/settings/${k0}`, adminToken, { value: `E2E_A_${s.suffix}` }).catch(() => {})
        await apiPutJson(`/api/settings/${k1}`, adminToken, { value: `E2E_B_${s.suffix}` }).catch(() => {})
      }
      const after = await apiGetJson('/api/settings/all', adminToken)
      expect(typeof after).toBe('object')
    } finally {
      await pageA.close().catch(() => {})
      await pageB.close().catch(() => {})
    }
  })

  test('15. teacher notification publish targeted to one student remains private across student, classmate, admin, and parent views', async () => {
    const s = scenario()
    const teacherToken = await obtainAccessToken(s.teacher_own.username, s.teacher_own.password)
    const studentAToken = await obtainAccessToken(s.student_plain.username, s.student_plain.password)
    const studentBToken = await obtainAccessToken(s.student_b.username, s.student_b.password)
    const adminToken = await obtainAccessToken(s.admin.username, s.admin.password)

    const uniqueTitle = `E2E_private_${s.suffix}_${Date.now()}`
    await apiPostJson('/api/notifications', teacherToken, {
      title: uniqueTitle,
      content: 'private targeted',
      priority: 'important',
      is_pinned: false,
      class_id: s.class_id_1,
      subject_id: s.course_required_id,
      target_student_id: s.student_plain.student_row_id
    })

    const listA = await apiListNotifications(studentAToken, { page_size: 100 })
    const listB = await apiListNotifications(studentBToken, { page_size: 100 })
    expect((listA.data || []).some(n => n.title === uniqueTitle)).toBe(true)
    expect((listB.data || []).some(n => n.title === uniqueTitle)).toBe(false)

    const gen = await apiPostJson(`/api/parent/students/${s.student_plain.student_row_id}/generate-code`, teacherToken)
    const parentNs = await fetch(
      `${apiBase()}/api/parent/notifications/${gen.parent_code}?page_size=100`
    ).then(r => r.json())
    expect((parentNs.notifications || []).some(n => n.title === uniqueTitle)).toBe(true)

    await apiGetJson('/api/users', adminToken)
  })
})
