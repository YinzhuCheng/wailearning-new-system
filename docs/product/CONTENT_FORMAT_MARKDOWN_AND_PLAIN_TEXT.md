# Content format: Markdown vs plain text (homework, submissions, materials, notifications, discussions)

## Purpose (for humans and LLM agents)

This repository stores long-form text in several places: homework instructions, student submission bodies, course materials, notifications, and discussion replies. Historically the school UI assumed **Markdown** for most authoring surfaces, but some users need **plain text** where characters like `#`, `*`, or `_` must appear literally without being interpreted as Markdown.

This document describes the **optional format switch** implemented as `content_format` (or `body_format` for discussions) with allowed values:

- `markdown` (default): render with the same Markdown + KaTeX pipeline as other course content.
- `plain`: render as pre-wrapped text (no Markdown parsing in the browser for that field).

The database stores the flag on the row so API consumers and LLM pipelines can behave consistently.

## Where the flag lives (ORM)

| Table | Column | Applies to |
|-------|--------|------------|
| `homeworks` | `content_format` | Teacher-authored **作业内容**（评分要点 / 教师私有要点 / 参考答案或思路另见独立列，格式同上均为 Markdown 管线渲染） |
| `homework_submissions` | `content_format` | Latest summary text mirrored from the latest attempt |
| `homework_attempts` | `content_format` | Each attempt body |
| `course_materials` | `content_format` | Material description body |
| `notifications` | `content_format` | Teacher/admin-authored notification body (`password_reset_request` remains HTML from the system) |
| `course_discussion_entries` | `body_format` | Each discussion message body (including LLM assistant rows, which remain `markdown`) |
| `learning_note_resources` | `content_format` | Owner-editable learning-note resources, including course material snapshots copied into a note |
| `learning_note_discussion_entries` | `body_format` | Learning-note discussion messages and assistant replies |

Schema migrations are applied via `ensure_schema_updates()` in `apps/backend/courseeval_backend/bootstrap.py` using `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ... DEFAULT 'markdown'`.

## API contracts (Pydantic)

- `HomeworkBase`, `HomeworkUpdate`, `HomeworkResponse`: `content_format: Literal["markdown","plain"]` (default `markdown`).
- `HomeworkSubmissionCreate`, `HomeworkSubmissionResponse`, `HomeworkAttemptResponse`: `content_format`.
- `HomeworkSubmissionStatusResponse`: includes `content_format` for teacher grid/detail views.
- `CourseDiscussionCreate`, `CourseDiscussionEntryResponse`: `body_format`.
- `LearningNoteResourceCreate` / `LearningNoteResourceUpdate` / `LearningNoteResourceResponse`: `content_format`.
- `LearningNoteDiscussionCreate` / `LearningNoteDiscussionEntryResponse`: `body_format`.
- `NotificationBase` / `NotificationUpdate` / `NotificationResponse`: `content_format`.
- `CourseMaterialBase` / `CourseMaterialUpdate` / `CourseMaterialResponse`: `content_format`.

Normalization helper: `apps/backend/courseeval_backend/domains/text_content_format.py` (`normalize_content_format`).

## LLM grading behavior (critical)

Auto-grading expands Markdown images for homework instructions and student bodies. If the homework `content_format` is `plain`, the instruction text is wrapped for the model using `body_text_for_grading_llm` so Markdown-like punctuation is not mis-parsed as structure.

Similarly, if a **student attempt** uses `content_format="plain"`, the attempt body is fenced before tokenization/truncation so the model receives literal text.

Discussion LLM (`llm_discussion.py`) also wraps plain homework bodies, plain material bodies, plain prior student attempt excerpts, and plain historical discussion lines when building the thread context.

## School SPA (Vue)

### Shared components

- `MarkdownEditorPanel.vue`: optional `v-model:contentFormat` + `showFormatToggle`. When `plain` is selected, the Markdown toolbar, KaTeX usage hint, fixed **LaTeX live demo** (`MarkdownLatexLiveDemo.vue`), and live preview are hidden; the textarea remains monospace for editing. In Markdown mode the toolbar includes **行内公式** / **独立公式** snippets (`\(…\)`, `$$…$$`). Above the textarea, a **non-editable canonical example** (`apps/web/school/src/utils/markdownLatexDemo.js`) is always rendered via `RichMarkdownDisplay` so authors see correct delimiter behavior before typing; below that, **您的内容预览** mirrors the editable textarea. Props `compact-demo` reduces padding / hides the collapsible raw-markdown panel when multiple Markdown fields stack in one dialog (homework rubric blocks still show the **same rendered** demo).
- `MarkdownLatexLiveDemo.vue`: reusable demo card + copy / insert actions. In large authoring surfaces (`MarkdownEditorPanel`) it is rendered immediately; in the discussion composer it is hidden behind an explicit **查看 Markdown + LaTeX 示例** toggle so the reply area does not start with a long instructional block.
- `RichMarkdownDisplay.vue` + `apps/web/school/src/utils/markdownIt.js`: shared Markdown + KaTeX render path. Important implementation detail: before calling `markdown-it`, the renderer temporarily replaces `\(`, `\)`, `\[`, `\]` with placeholder tokens and restores them in the generated HTML. Without that protection, `markdown-it` consumes the backslashes as Markdown escapes, so KaTeX never sees the promised delimiters. This placeholder round-trip is now part of the contract for editor preview, published discussion rows, material readers, and any other UI using `RichMarkdownDisplay` / `FeedbackRichText`.
  Multiline display math whose delimiters live on their own lines is also protected as a complete block before Markdown rendering (`$$...$$` and `\[...\]`). Do not remove this block-level placeholder pass: Markdown-it `breaks: true` can otherwise split multiline formulas into `<br>` / paragraph boundaries before KaTeX auto-render scans the DOM.
- `PlainOrMarkdownBlock.vue`: read-only display; delegates Markdown mode to `RichMarkdownDisplay` and uses `white-space: pre-wrap` for plain mode.
- `apps/web/school/src/utils/contentFormat.js`: mirrors backend normalization for client defaults.

### Screens touched

- **Homework submission** (`HomeworkSubmission.vue`): label renamed to **正文**; editor supports Markdown/plain; history timeline uses `PlainOrMarkdownBlock`.
- **Homework authoring** (`Homework.vue`): assignment body editor toggles format; homework detail uses `PlainOrMarkdownBlock` for instructions.
- **Materials** (`Materials.vue` + `MaterialRead.vue`): authoring uses the same Markdown panel; table rows expose **阅读页** linking to `/materials/read/:id` with prev/next navigation while the modal detail dialog keeps quick preview + discussion threading. **Full-page reader (`MaterialRead.vue`) also mounts `CourseDiscussionPanel` below the article** so behavior matches the modal: thread bodies render via `PlainOrMarkdownBlock` (Markdown + KaTeX vs plain); composer shows the same Markdown/LaTeX live demo when reply format is Markdown. Orphan materials (`discussion_requires_context=true`) show the existing warning card instead of the thread composer.
  Student navigation contract: student-side **课程目录** entry points should
  prefer the full-page reader instead of the teacher-oriented management hub
  when readable materials exist.
  Reader action contract: `MaterialRead.vue` may render **本章作业**,
  **本章资料**, **未归档资料**, and **未归档作业** blocks below the article body
  when chapter metadata and uncategorized entries exist.
- **Notifications** (`Notifications.vue`): compose + detail (non-password-reset) respect `content_format`.
- **Teacher submissions** (`HomeworkSubmissions.vue` + `HomeworkSubmissionReview.vue`): the **list** still uses `PlainOrMarkdownBlock` in the **历史** dialog for expanded attempt bodies. **「详情」** no longer opens a 720px dialog: it **navigates to** `HomeworkSubmissionReview.vue` at **`/homework/:homeworkId/submissions/:submissionId`** (query params such as `student_id` are preserved for return navigation). The review page uses the same render stack for the latest summary body, embeds a score/comment form, a collapsible per-attempt history timeline, and a **返回提交列表** control. The teacher-only API **`GET /api/homeworks/{homework_id}/submissions/{submission_id}/status`** returns a single `HomeworkSubmissionStatusResponse` row for that page (avoids paging the full class roster). **Pitfall:** older Playwright specs that waited for `getByRole('dialog')` after clicking **详情** must be updated to assert `toHaveURL(/\/homework\/\d+\/submissions\/\d+/)` and target `data-testid="homework-submission-detail-body"` on the **page** (not inside a dialog).
- **Discussions** (`CourseDiscussionPanel.vue` + `DiscussionAuthorAvatar.vue`): radio group **回复格式** before posting; choosing **Markdown** now shows two separate affordances:
  1. a lightweight toolbar row with **查看 Markdown + LaTeX 示例** / **隐藏 Markdown + LaTeX 示例** so the fixed example stays **collapsed by default**,
  2. an always-live **回复预览** block under the textarea, rendered by the same `RichMarkdownDisplay` stack used after publishing.
  
  Published rows also changed: **short** discussion bodies now render immediately via `PlainOrMarkdownBlock` (so Markdown + KaTeX works right after posting), while **long** bodies still use the existing three-logical-line collapsed preview and only switch to the full renderer after the user expands them. `POST /api/discussions` still sends `body_format`.

  **Discussion list presentation (May 2026, chat-oriented refinement)** — agents editing UX should preserve these contracts alongside Markdown/plain rendering:

  | Concern | Implementation detail |
  |---------|------------------------|
  | Author avatar | Each row mounts `DiscussionAuthorAvatar` with `author_avatar_url`, `author_real_name` (via `displayAuthorName`), `author_role`, and `message_kind`. Blob URLs use `fetchAttachmentBlobUrl` like other attachment-backed previews. |
  | Fallback initials | When no photo URL resolves, `el-avatar` shows one Chinese character: first character of display name when present; otherwise role-based **管 / 班 / 师 / 学 / 人**; assistant rows use **助** inside the avatar circle. |
  | Corner role badge | A **small overlay** at the bottom-right of the avatar (not only on fallback initials) shows **管 / 师 / 班 / 学 / 助** so staff vs student remains visible when a profile photo is shown. Mapping: `admin→管`, `teacher→师`, `class_teacher→班`, `student→学`, `message_kind===llm_assistant→助`. Unknown roles omit the badge character but keep gray fallback styling. CSS classes: `discussion-author-avatar__badge--role-*` and `discussion-author-avatar__badge--assistant`. |
  | Assistant contrast | Rows with `message_kind === 'llm_assistant'` get `discussion-row--assistant`: light green gradient panel, inset green left bar, subtle outer ring/shadow, stronger green emphasis on the avatar (`discussion-author-avatar--assistant`), and body text tint (`discussion-row__name--assistant`, darker green body copy). This is **in addition to** the avatar label **智能助教** — the duplicate `el-tag` “智能助教” next to the name was removed to avoid showing the same label twice. |
  | Compact meta row | `discussion-row__meta` uses tighter vertical spacing; **timestamp** uses `margin-left: auto` so on wide viewports it sits flush right on the first line (chat-header pattern). Role chips for humans remain `el-tag` with classes `discussion-row__role-tag`; **调用智能助教** keeps `discussion-row__llm-tag`. |
  | DOM hooks for E2E | Existing Playwright specs rely on **`.discussion-row`**, **`.discussion-row__body`**, **`.discussion-row__text`** — these class names remain stable. New styling is additive (`discussion-row--assistant`, badge spans). Do not remove `.discussion-row__text` from the rich-body path. |

## Testing

Integration tests live in:

- `tests/backend/content_format/test_content_format_api.py`

They assert round-trip persistence for homework update + student submission, discussion `body_format`, and notification `content_format`.

## Pitfalls encountered while implementing (agent-oriented)

1. **Pydantic model accidentally deleted mid-edit**
   During a large `schemas.py` edit, `class HomeworkCreate(HomeworkBase): pass` was dropped, leaving only `HomeworkUpdate`. Symptom: `ImportError: cannot import name 'HomeworkCreate'` when importing `apps.backend.courseeval_backend.main` or any router that imports schemas.
   **Fix:** restore `HomeworkCreate` immediately after `HomeworkBase`. Run `python3 -c "from apps.backend.courseeval_backend.api.schemas import HomeworkCreate"` as a quick gate.

2. **SQLite bootstrap ordering**  
   `ALTER TABLE course_materials ADD COLUMN ...` must exist for databases that already have `course_materials` from earlier releases. The migration list in `bootstrap.py` is append-only; if a new `ALTER` is missing, production SQLite can start but ORM loads may fail when selecting unknown columns depending on SQLAlchemy version and reflection—prefer adding the `ALTER TABLE ... IF NOT EXISTS` alongside the model field.

3. **Frontend duplicate `data-testid` attributes**  
   Vue does not allow two identical attributes on one element. If you add `data-testid` to a wrapper component prop, remove the duplicate from the parent template.

4. **`refresh_submission_summary` must mirror `content_format`**  
   If only attempts store `content_format` but the summary row is refreshed from the latest attempt, the summary column must be updated too or teacher APIs will return stale `markdown` for plain attempts.

5. **Playwright / E2E**  
   This change set does not automatically update every Playwright selector. If a spec asserted raw textarea DOM for homework submission content, it may need to target the inner `.md-panel__input` textarea or use `data-testid="homework-submit-content"` on the panel root.  
   **Material read + discussion:** after embedding `CourseDiscussionPanel` on `/materials/read/:id`, specs can scope assertions to `.material-read-page .discussion-card` (card header text 「讨论区」). Duplicate `data-testid="markdown-latex-demo-render"` remains limited to editor surfaces; the discussion list uses `PlainOrMarkdownBlock` per row without that test id.

6. **Dashboard `total_students` vs elective enrollment**  
   Earlier implementations counted every `Student` in the course class even when `subject_id` targeted an elective with partial `course_enrollments`. Symptoms: the **removed** teacher 「课程仪表盘」page showed “学生总数 = 班级人数” while **学生管理** listed fewer选课学生（演示种子「初等概率论」即如此）。  
   **Mitigated (API):** `GET /api/dashboard/stats?subject_id=…` counts `course_enrollments` rows for that subject. Regression guard: `tests/backend/integration/test_core_api_surface.py::test_dashboard_stats_subject_id_counts_enrollments_not_class_roster`.  
   **UI note (May 2026):** The **`Dashboard.vue` SPA page was deleted**; agents must not expect `/dashboard` metrics cards — bookmark `/dashboard` redirects to **`/students`**. Teacher-facing enrollment parity is asserted in Playwright via **学生管理 · 课程学生名单** header counts (`tests/e2e/web-school/e2e-course-ui-markdown-reader.spec.js`).

7. **KaTeX delimiter literacy**  
   Authors sometimes paste math wrapped only in `[ ... ]`. `RichMarkdownDisplay` uses KaTeX `renderMathInElement` with `\(…\)`, `$…$`, `$$…$$`, `\[…\]` only—the demo block shipped with `MarkdownEditorPanel` / discussions spells this out and renders a live counter-example.

8. **Course materials reading navigation**  
   Full-page reader lives at `<admin-base>/materials/read/:id` (`MaterialRead.vue`). Prev/next order is **DFS chapter tree × API sort order per chapter** (same sequencing logic as the list endpoint). After `GET /materials/{id}`, the reader **attempts to align `selected_course`** with `material.subject_id` using `fetchTeachingCourses` so deep links work even when `localStorage.selected_course` was cleared (Playwright `login()` clears storage). If the material’s subject is not in the teacher/student course list, the UI still redirects back to `/materials`. The article (`material.title` / body) is bound **before** chapter DFS completes so readers see the heading immediately; DFS failures downgrade to “导航不完整” rather than blocking the article.  
   **Discussion parity:** the reader intentionally includes **`CourseDiscussionPanel`** (same props contract as `Materials.vue` detail dialog: `target-type="material"`, `subject_id`, `class_id`, `discussion_requires_context`, `is-student`). Agents must not assume “reading mode” is article-only; regression tests should assert the discussion card is present on `/materials/read/:id` when the material is course-scoped.
   Student directory routing: `StudentCourseHome.vue` should send student
   “查看全部”, empty-state, and chapter-entry actions to `/materials/read/:id`
   whenever a readable material exists.
   Reader chapter context: `currentChapterHomeworkLinks` and
   `currentChapterMaterials` describe the active chapter, while
   `looseMaterialEntries` and `looseHomeworkLinks` represent the uncategorized
   bucket surfaced in the same reader.

9. **Teacher + student sidebars: removal of single-child submenu shells**  
   Historically `Layout.vue` wrapped **teacher** routes under 「日常教学」 (`teacher-daily`) and **student** routes under 「课程学习」 (`student-learning`), each forcing an extra expand click despite containing only one logical group. Both are now **flat `el-menu-item` rows** at the sidebar root (same paths and labels as the former children). **`default-openeds` / `homeworkMenuOpenIndices` no longer references `teacher-daily` or `student-learning`.** Admin 「学期与配置」 / 「消息与审计」 and **班主任「班级教学」** groupings remain as nested menus where multiple unrelated destinations still benefit from grouping.  
   **Menu active highlight:** `el-menu` `default-active` is driven by `sidebarMenuActivePath`, mapping nested routes (e.g. `/materials/read/123` → `/materials`, `/homework/9/submit` → `/homework`) so the correct rail item stays selected; without this mapping, Element Plus leaves no item highlighted when `route.path` does not exactly equal a menu `index`.

10. **Removal of teacher 「课程仪表盘」 (`Dashboard.vue`) + standalone `/teaching-calendar` page**
   Product decision: delete the aggregated dashboard view as low-value/noisy and avoid splitting the same attendance workflow across two sidebar destinations. **Teaching calendar** (`TeachingCalendar.vue`, titled 「教学日历」 inside the widget) previously moved through a standalone wrapper, but the current supported owner is **`Attendance.vue`** at **`/attendance`**. The widget is embedded at the top of the attendance page; selecting a rendered course day updates the attendance date and reloads / re-syncs the attendance draft for that day.
   - **任课教师 sidebar:** exposes **考勤管理** only for this workflow. There is no separate **教学日历** menu item; the calendar is part of attendance management.

11. **Student score appeals: homework-target branch**
   `StudentScores.vue` no longer exposes the raw **关联成绩ID** field. The
   student appeal form now supports:
   - total score;
   - homework average;
   - one specific homework score;
   - other daily score;
   - configured exam components.

   Homework-target rule:
   when the student chooses the homework branch, the UI must render a homework
   selector sourced from `composition.homework_assignments`, limited to rows
   that already have a review score. The API request carries `homework_id`
   instead of `score_id`.

   Backend/storage rule:
   score-appeal rows keep using `score_grade_appeals`, but the homework branch
   is encoded as `target_component = "homework:<homework_id>"`. Teacher-facing
   serializers normalize that branch back to `target_component = "homework"`
   plus `homework_id` / `homework_title`.

   Notification rule:
   score-appeal notifications for that homework-target branch must also carry
   `related_homework_id`, so teacher notification actions can jump directly to
   `/homework/:id/submissions` for the affected homework rather than only to
   the generic `/scores` appeal list.
   - **班主任 sidebar:** keeps teaching operations under **班级教学** and does not expose a standalone calendar page.
   - **Login / root redirect:** teachers and class teachers default to **`/students`** (see `Login.vue`, empty-path redirect in `router/index.js`). **`/dashboard` → `/students` redirect** preserves stale bookmarks without resurrecting the Vue page.  
   - **Historical deep link:** `/teaching-calendar` remains in `router/index.js` only as a compatibility redirect to **`/attendance`**. Agents should not recreate `TeachingCalendarPage.vue`; tests should assert the redirect and the embedded `.attendance-page .teaching-calendar` widget.
   - **Admin visibility:** `/teaching-calendar` remains listed in `adminHiddenPaths` like other teacher tools, so admins hitting it bounce to **`/students`** (admin home) before the teacher redirect matters.
   - **Students:** `/teaching-calendar` remains blocked (student redirect list in `router.beforeEach`), same spirit as `/scores`; students use course pages and attendance is not a student navigation target.
   **Backend:** `dashboard.router` APIs (`/api/dashboard/stats`, rankings, analysis) remain for **排行榜 / 数据分析** pages — only the dedicated SPA aggregate page and standalone calendar wrapper were removed.

11. **Discussion short-body rendering vs expand-only rendering**  
   A discussion row used to mount `PlainOrMarkdownBlock` **only when expanded**. Symptom: a newly posted short Markdown reply (including LaTeX) appeared as raw source in the list until the row was manually expanded — and because short rows are not truncated, there was no expand action at all, so users perceived this as “发布后渲染失败”.  
   **Fix:** `CourseDiscussionPanel.vue` now renders the rich block immediately when the body is **not truncated**, and keeps the collapsed plain-text preview path only for long rows. Regression guard: `tests/e2e/web-school/e2e-course-ui-markdown-reader.spec.js` case **material detail discussion keeps demo collapsed by default, shows live preview, and renders posted KaTeX**.

12. **Markdown-it escaping of `\(...\)` and `\[...\]`**  
   The repository documentation and UI hints explicitly promise four delimiter families: `$...$`, `$$...$$`, `\(...\)`, `\[...\]`. In practice, `markdown-it` treats `\(` / `\[` as escape sequences and drops the backslashes before the DOM reaches `renderMathInElement`, so the preview can degrade to literal `(x^2)` text even though KaTeX support is configured.  
   **Fix:** `apps/web/school/src/utils/markdownIt.js::renderCourseMarkdown` now performs a placeholder round-trip around `md.render(...)`. `RichMarkdownDisplay.vue` and `FeedbackRichText.vue` both call that helper, so editor previews and published views preserve these delimiters consistently.

13. **School SPA `npm run build` without prior `npm install` (missing local `vite`)**  
   Symptom (fresh clone / CI worktree / agent sandbox): from `<repo>/apps/web/school`, `npm run build` fails immediately with `sh: 1: vite: not found` or equivalent because devDependencies (including `vite`) are not installed in that directory’s `node_modules`.  
   **Fix:** run `npm install` in `<repo>/apps/web/school` before `npm run build`. Long-term, automation should treat `apps/web/school/package-lock.json` + `npm ci`/`npm install` as the gate for any Vue verification step. This is **not** a product bug; it is an environment precondition pitfall.

14. **Discussion assistant row: duplicate “智能助教” label vs accessibility**  
   Before the chat-oriented layout pass, the UI rendered **both** the bold display name **智能助教** (`displayAuthorName`) **and** a plain `el-tag` also labeled **智能助教** for `message_kind === 'llm_assistant'`. Symptom: noisy duplicate labels and wasted horizontal space in the meta row.  
   **Fix:** drop the redundant tag for assistant rows; rely on styled text (`discussion-row__name--assistant`), assistant row chrome (`discussion-row--assistant`), and the avatar corner badge **助**. Agents updating specs should **not** assume a second adjacent “智能助教” tag on assistant rows — filter Playwright assertions on `.discussion-row` text content or body content as today.

## Related documentation

- [LLM and Homework Guide](../product/LLM_HOMEWORK_GUIDE.md) — grading pipeline overview
- [Test Suite Map](../testing/TEST_SUITE_MAP.md) — where API tests live
- [Encoding And Mojibake Safety](../contributing/ENCODING_AND_MOJIBAKE_SAFETY.md) — UTF-8 expectations for text fields

## Learning notes format notes

`LearningNotes.vue` and `api/routers/learning_notes.py` use the same `markdown` / `plain` normalization model for note resources and note discussion bodies. The persistence tables are `learning_note_resources` and `learning_note_discussion_entries`, not `course_materials` or `course_discussion_entries`, because students can own and edit copied course outlines while official course materials remain teacher-published. When copying course materials into a note, attachment URLs are kept by reference rather than copied on disk. A future richer note editor should reuse `MarkdownEditorPanel` / `PlainOrMarkdownBlock` rather than inventing another renderer.
