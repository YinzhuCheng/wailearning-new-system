<template>
  <el-card shadow="never" class="discussion-card">
    <template #header>
      <div class="discussion-head">
        <div class="discussion-head__main">
          <span class="discussion-head__title">讨论区</span>
          <el-text v-if="canUseDiscussion" type="info" size="small">
            实名讨论，每页 {{ effectivePageSize }} 条回复
          </el-text>
        </div>
        <el-button
          v-if="canUseDiscussion"
          text
          type="primary"
          size="small"
          class="discussion-head__toggle"
          @click="discussionCollapsed = !discussionCollapsed"
        >
          {{ discussionCollapsed ? '展开' : '收起' }}
        </el-button>
      </div>
    </template>

    <el-alert
      v-if="!canUseDiscussion"
      type="warning"
      :closable="false"
      title="该条目未关联课程，无法在课程实例下讨论。请从课程内打开或联系管理员关联课程与班级。"
      show-icon
    />

    <template v-else-if="!discussionCollapsed">
      <div v-loading="loading" class="discussion-body">
        <section class="discussion-list-section" aria-label="讨论列表">
          <div v-if="!entries.length && !loading" class="muted-text">暂无讨论，发表第一条回复吧。</div>
          <div
            v-for="row in entries"
            :key="row.id"
            class="discussion-row"
            :class="{
              'discussion-row--assistant': row.message_kind === 'llm_assistant',
              'discussion-row--highlighted': Number(highlightedEntryId) === Number(row.id)
            }"
            :data-discussion-entry-id="row.id"
          >
            <div class="discussion-row__main">
              <DiscussionAuthorAvatar
                :user-id="row.author_user_id"
                :avatar-url="row.author_avatar_url"
                :name="displayAuthorName(row)"
                :role="row.author_role"
                :student-id="row.author_student_id"
                :course="selectedCourse"
                :message-kind="row.message_kind"
              />
              <div class="discussion-row__content">
                <div class="discussion-row__meta">
                  <span
                    class="discussion-row__name"
                    :class="{ 'discussion-row__name--assistant': row.message_kind === 'llm_assistant' }"
                  >
                    {{ displayAuthorName(row) }}
                  </span>
                  <el-tag
                    v-if="row.message_kind !== 'llm_assistant'"
                    size="small"
                    effect="plain"
                    class="discussion-row__role-tag"
                  >
                    {{ roleLabel(row.author_role) }}
                  </el-tag>
                  <el-tag
                    v-if="row.llm_invocation"
                    type="warning"
                    size="small"
                    effect="plain"
                    class="discussion-row__llm-tag"
                  >
                    调用智能助教
                  </el-tag>
                  <span class="discussion-row__time">{{ formatTime(row.created_at) }}</span>
                </div>
                <div
                  class="discussion-row__body"
                  :class="{
                    'discussion-row__body--clickable': isTruncated(row.body) && !isExpanded(row.id)
                  }"
                  @click="onBodyClick(row)"
                >
                  <div
                    class="discussion-row__text"
                    :class="{ 'discussion-row__text--block': shouldRenderRichBody(row) }"
                  >
                    <PlainOrMarkdownBlock
                      v-if="shouldRenderRichBody(row)"
                      :text="row.body"
                      :format="row.body_format"
                      variant="student"
                    />
                    <template v-else>{{ collapsedBodyPreview(row) }}</template>
                  </div>
                  <DiscussionLinkedTargetCards
                    v-if="row.linked_targets?.length"
                    :items="row.linked_targets"
                    clickable
                    compact
                    @open="openLinkedTarget"
                  />
                  <button
                    v-if="isTruncated(row.body) && isExpanded(row.id)"
                    type="button"
                    class="discussion-row__collapse-btn"
                    @click.stop="collapseRow(row.id)"
                  >
                    收起
                  </button>
                </div>
                <div v-if="canDelete(row)" class="discussion-row__actions">
                  <el-button type="danger" link size="small" @click="removeEntry(row)">删除</el-button>
                </div>
              </div>
            </div>
          </div>

          <el-pagination
            v-if="total > effectivePageSize"
            v-model:current-page="page"
            class="discussion-pager"
            :page-size="effectivePageSize"
            :total="total"
            layout="total, prev, pager, next"
            small
            @current-change="loadList"
          />
        </section>

        <section class="discussion-composer-section" aria-label="发表回复">
          <div class="discussion-composer-head">
            <div>
              <strong>回复</strong>
              <el-text v-if="!composerExpanded" type="info" size="small">展开后编辑内容</el-text>
            </div>
            <el-button text type="primary" size="small" @click="toggleComposer">
              {{ composerExpanded ? '收起回复框' : '写回复' }}
            </el-button>
          </div>

          <div v-if="composerExpanded" class="discussion-composer-body">
            <div class="discussion-composer-toolbar">
              <el-radio-group v-model="composerMode" size="small">
                <el-radio-button label="edit">编辑</el-radio-button>
                <el-radio-button label="preview">预览</el-radio-button>
              </el-radio-group>
              <span class="discussion-format-bar__label">回复格式</span>
              <el-radio-group v-model="draftFormat" size="small">
                <el-radio-button label="markdown">Markdown</el-radio-button>
                <el-radio-button label="plain">纯文本</el-radio-button>
              </el-radio-group>
            </div>

            <div v-if="canInvokeLlm" class="discussion-llm-bar">
              <el-button
                size="small"
                :type="llmMode ? 'primary' : 'default'"
                plain
                data-testid="discussion-llm-toggle"
                @click="toggleLlmMode"
              >
                请 LLM 回复
              </el-button>
              <el-text v-if="llmMode" type="info" size="small">
                {{ llmModeHint }}
              </el-text>
            </div>

            <div v-if="draftFormat === 'markdown'" class="discussion-md-toolbar">
              <el-button
                type="primary"
                link
                size="small"
                data-testid="discussion-markdown-demo-toggle"
                @click="toggleMarkdownDemo"
              >
                {{ showMarkdownDemo ? '隐藏卡片 / Markdown / LaTeX 示例' : '查看卡片 / Markdown / LaTeX 示例' }}
              </el-button>
              <el-button
                type="primary"
                link
                size="small"
                data-testid="discussion-image-help-toggle"
                @click="showMarkdownImageHelp = !showMarkdownImageHelp"
              >
                {{ showMarkdownImageHelp ? '隐藏插图说明' : '查看当前支持的插图' }}
              </el-button>
              <span class="discussion-md-toolbar__hint">预览会在同一区域切换显示。</span>
            </div>
            <div v-if="draftFormat === 'markdown' && showMarkdownDemo" class="discussion-md-demo-wrap">
              <MarkdownLatexLiveDemo
                compact
                :show-insert="true"
                :show-card-section-toggle="true"
                :show-image-section-toggle="true"
                :show-source-collapse="false"
                title="卡片 / Markdown / LaTeX 示例"
                subtitle="回复格式为 Markdown 时按需展开：先看基础渲染，再显示卡片和插图示例。"
                @insert="appendDraftSnippet"
              />
              <DiscussionLinkedTargetCards
                v-if="draftLinkedTargets.length"
                :items="draftLinkedTargets"
                compact
              />
            </div>
            <div v-if="draftFormat === 'markdown' && showMarkdownImageHelp" class="discussion-md-image-help">
              <div class="discussion-md-image-help__title">当前系统支持的插图方式</div>
              <ul class="discussion-md-image-help__list">
                <li>Markdown 图片语法：`![说明](https://...)`</li>
                <li>当前编辑器提供本地上传与图片 URL 两种常用入口</li>
                <li>也可以按需插入系统内置的示例图，先确认版式效果再写正文</li>
              </ul>
              <div class="discussion-md-image-help__actions">
                <el-button size="small" @click="appendDraftSnippet('\n![图片说明](https://example.com/your-image.png)\n')">
                  插入图片模板
                </el-button>
                <el-button size="small" type="primary" plain @click="appendDraftSnippet(`\n${MARKDOWN_IMAGE_EXAMPLE_MARKDOWN}\n`)">
                  插入示例图
                </el-button>
              </div>
            </div>

            <div class="discussion-linked-targets-toolbar">
              <DiscussionLinkTargetPicker
                :preferred-subject-id="resolvedSubjectId"
                :selected-targets="draftLinkedTargets"
                @select="attachLinkedTarget"
              />
            </div>

            <DiscussionLinkedTargetCards
              v-if="draftLinkedTargets.length"
              :items="draftLinkedTargets"
              removable
              @remove="removeLinkedTarget"
            />

            <el-input
              v-if="composerMode === 'edit'"
              v-model="draft"
              type="textarea"
              :rows="4"
              maxlength="8000"
              show-word-limit
              :placeholder="inputPlaceholder"
              class="discussion-input"
            />
            <div v-else class="discussion-preview" data-testid="discussion-markdown-preview">
              <PlainOrMarkdownBlock
                :text="draft"
                :format="draftFormat"
                variant="student"
                empty-text="（空）"
              />
            </div>

            <div class="discussion-composer-actions">
              <el-button
                type="primary"
                :loading="posting"
                :disabled="!draft.trim()"
                data-testid="discussion-submit"
                @click="submit"
              >
                {{ llmMode ? '发送（调用智能助教）' : '发表回复' }}
              </el-button>
              <el-button @click="composerExpanded = false">取消</el-button>
            </div>
          </div>
        </section>
      </div>
    </template>

    <div v-else class="discussion-collapsed">
      <span>{{ total }} 条回复</span>
      <span>每页 {{ effectivePageSize }} 条</span>
    </div>
  </el-card>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import api from '@/api'
import DiscussionAuthorAvatar from '@/components/DiscussionAuthorAvatar.vue'
import DiscussionLinkedTargetCards from '@/components/DiscussionLinkedTargetCards.vue'
import DiscussionLinkTargetPicker from '@/components/DiscussionLinkTargetPicker.vue'
import MarkdownLatexLiveDemo from '@/components/MarkdownLatexLiveDemo.vue'
import PlainOrMarkdownBlock from '@/components/PlainOrMarkdownBlock.vue'
import { useUserStore } from '@/stores/user'
import { normalizeContentFormat } from '@/utils/contentFormat'
import { discussionLinkedTargetKey, openDiscussionLinkedTarget } from '@/utils/discussionLinkTargets'
import { MARKDOWN_IMAGE_EXAMPLE_MARKDOWN } from '@/utils/markdownLatexDemo'

/** Each segment renders as one logical line: a text line (may be empty) or one image. */
const PREVIEW_LINE_LIMIT = 3

/** Markdown ![alt](url) or HTML <img ...> each counts as one line. */
const INLINE_IMAGE_RE = /!\[[^\]]*\]\([^)]+\)|<img\b[^>]*>/gi

const props = defineProps({
  targetType: {
    type: String,
    required: true,
    validator: v => v === 'homework' || v === 'material'
  },
  targetId: { type: Number, required: true },
  /** When set, used for API scope (course instance). */
  subjectId: { type: Number, default: null },
  classId: { type: Number, default: null },
  /** Backend hint: homework/material not linked to a subject. */
  discussionRequiresContext: { type: Boolean, default: false },
  /** Student UI flag from callers; actual LLM permissions derive from current user role. */
  isStudent: { type: Boolean, default: false }
})

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const selectedCourse = computed(() => userStore.selectedCourse)

const resolvedSubjectId = computed(() => {
  if (props.subjectId != null && props.subjectId !== '') return Number(props.subjectId)
  const c = selectedCourse.value
  return c?.id != null ? Number(c.id) : null
})

const resolvedClassId = computed(() => {
  if (props.classId != null && props.classId !== '') return Number(props.classId)
  const c = selectedCourse.value
  return c?.class_id != null ? Number(c.class_id) : null
})

const canUseDiscussion = computed(() => {
  if (props.discussionRequiresContext) return false
  return resolvedSubjectId.value != null && resolvedClassId.value != null
})

const effectivePageSize = computed(() => {
  const raw = userStore.userInfo?.discussion_page_size
  const n = raw != null ? Number(raw) : 5
  if (Number.isFinite(n) && n >= 5 && n <= 50) return n
  return 5
})

const loading = ref(false)
const posting = ref(false)
const page = ref(1)
const total = ref(0)
const entries = ref([])
const draft = ref('')
const draftFormat = ref('markdown')
const draftLinkedTargets = ref([])
const showMarkdownDemo = ref(false)
const showMarkdownImageHelp = ref(false)
const llmMode = ref(false)
const discussionCollapsed = ref(false)
const composerExpanded = ref(false)
const composerMode = ref('edit')
/** entry id -> expanded full body */
const expandedEntryIds = ref(new Set())
const highlightedEntryId = ref(null)

let pollTimer = null
let pollAbort = null

const inputPlaceholder = computed(() => {
  if (llmMode.value) {
    return '首行已自动包含 @LLM（勿删），下一行起输入要向智能助教说明的问题…'
  }
  return '输入讨论内容（需登录，不支持匿名）'
})

const canInvokeLlm = computed(() =>
  ['student', 'teacher', 'class_teacher', 'admin'].includes(userStore.userInfo?.role || '')
)

const llmModeHint = computed(() => {
  if (userStore.isStudent) {
    return '将附带「@LLM」并消耗你的全站 LLM 日额度；教师若为课程设置输出上限则会生效，留空时默认不限制输出长度。'
  }
  return '将附带「@LLM」并调用课程智能助教；教师/班主任/管理员发起的讨论助教请求不受学生 token 日额度限制，课程输出上限留空时默认不限制输出长度。'
})

const appendDraftSnippet = snippet => {
  const cur = (draft.value || '').trim()
  draft.value = cur ? `${cur}\n\n${snippet}` : snippet
}

const attachLinkedTarget = item => {
  const key = discussionLinkedTargetKey(item)
  if (draftLinkedTargets.value.some(existing => discussionLinkedTargetKey(existing) === key)) {
    return
  }
  draftLinkedTargets.value = [...draftLinkedTargets.value, item]
}

const removeLinkedTarget = item => {
  const key = discussionLinkedTargetKey(item)
  draftLinkedTargets.value = draftLinkedTargets.value.filter(existing => discussionLinkedTargetKey(existing) !== key)
}

const openLinkedTarget = async item => {
  await openDiscussionLinkedTarget(item, router, userStore)
}

const routeDiscussionEntryId = computed(() => {
  const raw = Number(route.query.discussion_entry || 0)
  return Number.isFinite(raw) && raw > 0 ? raw : null
})

const routeDiscussionPage = computed(() => {
  const raw = Number(route.query.discussion_page || 0)
  return Number.isFinite(raw) && raw > 0 ? raw : null
})

const highlightRouteEntry = async () => {
  const targetId = routeDiscussionEntryId.value
  if (!targetId) return
  await nextTick()
  const el = typeof document !== 'undefined' ? document.querySelector(`[data-discussion-entry-id="${targetId}"]`) : null
  if (!el) return
  highlightedEntryId.value = targetId
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  window.setTimeout(() => {
    if (Number(highlightedEntryId.value) === Number(targetId)) {
      highlightedEntryId.value = null
    }
  }, 3200)
}

const roleLabel = role =>
  ({ admin: '管理员', class_teacher: '班主任', teacher: '教师', student: '学生' }[role] || role || '—')

const displayAuthorName = row => {
  if (row.message_kind === 'llm_assistant') return '智能助教'
  return row.author_real_name
}

const formatTime = v => {
  if (!v) return ''
  try {
    return new Date(v).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return String(v)
  }
}

const canDelete = row => {
  const uid = userStore.userInfo?.id
  if (uid != null && Number(row.author_user_id) === Number(uid)) return true
  if (userStore.isAdmin) return true
  if (userStore.isStudent) return false
  return userStore.canManageTeaching
}

const stopPolling = () => {
  if (pollTimer != null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  if (pollAbort) {
    try {
      pollAbort.abort()
    } catch {
      /* ignore */
    }
    pollAbort = null
  }
}

/**
 * Split body into line-sized segments: each `\\n`-split text line is one segment;
 * each markdown image and each HTML <img> tag is one segment (in order).
 */
function lineSegmentsFromBody(body) {
  const raw = body == null ? '' : String(body)
  const segments = []
  let last = 0
  let m
  const re = new RegExp(INLINE_IMAGE_RE.source, 'gi')
  while ((m = re.exec(raw)) !== null) {
    if (m.index > last) {
      const chunk = raw.slice(last, m.index)
      for (const line of chunk.split('\n')) {
        segments.push({ kind: 'text', value: line })
      }
    }
    segments.push({ kind: 'image', value: m[0] })
    last = m.index + m[0].length
  }
  if (last < raw.length) {
    for (const line of raw.slice(last).split('\n')) {
      segments.push({ kind: 'text', value: line })
    }
  }
  if (!segments.length) {
    segments.push({ kind: 'text', value: '' })
  }
  return segments
}

/** Rebuild original string from segments (inverse of lineSegmentsFromBody). */
function joinSegments(parts) {
  let s = ''
  for (let i = 0; i < parts.length; i += 1) {
    const seg = parts[i]
    if (seg.kind === 'text' && i > 0 && parts[i - 1].kind === 'text') {
      s += '\n'
    }
    s += seg.value
  }
  return s
}

function isTruncated(body) {
  return lineSegmentsFromBody(body).length > PREVIEW_LINE_LIMIT
}

function isExpanded(id) {
  return expandedEntryIds.value.has(id)
}

function shouldRenderRichBody(row) {
  return isExpanded(row.id) || !isTruncated(row.body)
}

function previewText(body) {
  const segs = lineSegmentsFromBody(body)
  if (segs.length <= PREVIEW_LINE_LIMIT) {
    return joinSegments(segs)
  }
  const head = segs.slice(0, PREVIEW_LINE_LIMIT)
  return `${joinSegments(head)}...`
}

function collapsedBodyPreview(row) {
  const body = row?.body ?? ''
  const fmt = normalizeContentFormat(row?.body_format)
  if (fmt === 'plain') {
    return previewText(body)
  }
  // Markdown / HTML-ish bodies: use the same logical-line ellipsis as plain text so
  // collapsed previews hide beyond PREVIEW_LINE_LIMIT lines (see tier-3 Playwright specs).
  if (isTruncated(body)) {
    return previewText(body)
  }
  const flat = String(body).replace(/\r?\n+/g, ' ').replace(/\s+/g, ' ').trim()
  if (!flat) {
    return ''
  }
  if (flat.length <= 240) {
    return flat
  }
  return `${flat.slice(0, 238)}…`
}

function onBodyClick(row) {
  if (!isTruncated(row.body) || isExpanded(row.id)) {
    return
  }
  const next = new Set(expandedEntryIds.value)
  next.add(row.id)
  expandedEntryIds.value = next
}

function collapseRow(id) {
  const next = new Set(expandedEntryIds.value)
  next.delete(id)
  expandedEntryIds.value = next
}

const loadList = async () => {
  if (!canUseDiscussion.value) return
  loading.value = true
  try {
    const res = await api.discussions.list({
      target_type: props.targetType,
      target_id: props.targetId,
      subject_id: resolvedSubjectId.value,
      class_id: resolvedClassId.value,
      page: page.value,
      page_size: effectivePageSize.value
    })
    total.value = res?.total ?? 0
    entries.value = res?.data ?? []
    expandedEntryIds.value = new Set()
    await highlightRouteEntry()
  } catch (e) {
    console.error(e)
    ElMessage.error(e?.response?.data?.detail || '加载讨论失败')
  } finally {
    loading.value = false
  }
}

const pollUntilAssistant = async (afterUserEntryId, maxSeconds = 90) => {
  stopPolling()
  const ac = new AbortController()
  pollAbort = ac
  const deadline = Date.now() + maxSeconds * 1000
  pollTimer = setInterval(async () => {
    if (Date.now() > deadline) {
      stopPolling()
      ElMessage.warning('智能助教响应超时，请稍后刷新页面查看。')
      return
    }
    try {
      const res = await api.discussions.listSignal(
        {
          target_type: props.targetType,
          target_id: props.targetId,
          subject_id: resolvedSubjectId.value,
          class_id: resolvedClassId.value,
          page: 1,
          page_size: Math.min(50, Math.max(effectivePageSize.value, 20))
        },
        ac.signal
      )
      const list = res?.data ?? []
      const hasAssistantAfter = list.some(r => r.message_kind === 'llm_assistant' && r.id > afterUserEntryId)
      if (hasAssistantAfter) {
        stopPolling()
        const lastPage = Math.max(1, Math.ceil((res?.total ?? total.value) / effectivePageSize.value))
        page.value = lastPage
        await loadList()
        ElMessage.success('智能助教已回复')
      }
    } catch (e) {
      if (e?.name === 'CanceledError' || e?.code === 'ERR_CANCELED') return
      console.error(e)
    }
  }, 1500)
}

const FORBIDDEN_AT = /@(?!LLM\b)[\w.-]+/gi

watch(draft, val => {
  if (typeof val !== 'string') return
  if (FORBIDDEN_AT.test(val)) {
    draft.value = val.replace(FORBIDDEN_AT, '').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n')
    ElMessage.warning('讨论区不支持 @ 其他用户或助教，已自动移除。')
  }
})

watch(draftFormat, val => {
  if (normalizeContentFormat(val) !== 'markdown') {
    showMarkdownDemo.value = false
    showMarkdownImageHelp.value = false
  }
})

const ensureLlmPrefix = () => {
  const t = draft.value || ''
  if (!/^\s*@LLM\b/i.test(t)) {
    draft.value = t.trim() ? `@LLM\n${t}` : '@LLM\n'
  }
}

const toggleLlmMode = () => {
  llmMode.value = !llmMode.value
  if (llmMode.value) ensureLlmPrefix()
  else {
    draft.value = (draft.value || '').replace(/^\s*@LLM\s*\n?/i, '').trimStart()
  }
}

const toggleMarkdownDemo = () => {
  showMarkdownDemo.value = !showMarkdownDemo.value
}

const toggleComposer = () => {
  composerExpanded.value = !composerExpanded.value
  if (composerExpanded.value) {
    composerMode.value = 'edit'
  } else {
    showMarkdownDemo.value = false
    showMarkdownImageHelp.value = false
  }
}

const submit = async () => {
  const text = draft.value.trim()
  if (!text || !canUseDiscussion.value) return
  if (llmMode.value) {
    const inner = text.replace(/^\s*@LLM\s*\n?/i, '').trim()
    if (!inner) {
      ElMessage.warning('请填写要向智能助教说明的内容（@LLM 之后不能为空）。')
      return
    }
  }
  posting.value = true
  try {
    const invokeLlm = Boolean(llmMode.value && canInvokeLlm.value)
    const res = await api.discussions.create({
      target_type: props.targetType,
      target_id: props.targetId,
      subject_id: resolvedSubjectId.value,
      class_id: resolvedClassId.value,
      body: text,
      body_format: normalizeContentFormat(draftFormat.value),
      linked_targets: draftLinkedTargets.value.map(item => ({
        target_type: item.target_type,
        target_id: item.target_id
      })),
      invoke_llm: invokeLlm
    })
    draft.value = ''
    draftFormat.value = 'markdown'
    draftLinkedTargets.value = []
    showMarkdownDemo.value = false
    showMarkdownImageHelp.value = false
    llmMode.value = false
    composerMode.value = 'edit'
    composerExpanded.value = false
    const lastPage = Math.max(1, Math.ceil((total.value + 1) / effectivePageSize.value))
    page.value = lastPage
    await loadList()
    ElMessage.success(invokeLlm ? '已提交，正在请求智能助教…' : '已发表')
    if (invokeLlm && res?.id != null) {
      pollUntilAssistant(Number(res.id))
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '发表失败')
  } finally {
    posting.value = false
  }
}

const removeEntry = async row => {
  try {
    await ElMessageBox.confirm('确定删除这条讨论吗？', '确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.discussions.delete(row.id)
    ElMessage.success('已删除')
    await loadList()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

watch(
  () => [props.targetId, props.targetType, props.subjectId, props.classId, props.discussionRequiresContext],
  () => {
    stopPolling()
    page.value = 1
    draftLinkedTargets.value = []
    loadList()
  }
)

watch(
  () => userStore.userInfo?.discussion_page_size,
  () => {
    stopPolling()
    page.value = 1
    loadList()
  }
)

watch(
  () => [resolvedSubjectId.value, resolvedClassId.value],
  () => {
    stopPolling()
    page.value = 1
    loadList()
  }
)

watch(
  () => [route.query.discussion_entry, route.query.discussion_page],
  () => {
    const targetPage = routeDiscussionPage.value
    if (routeDiscussionEntryId.value && targetPage && targetPage !== page.value) {
      page.value = targetPage
      loadList()
      return
    }
    highlightRouteEntry()
  }
)

onBeforeUnmount(() => {
  stopPolling()
})

if (routeDiscussionPage.value) {
  page.value = routeDiscussionPage.value
}
loadList()
</script>

<style scoped>
.discussion-card {
  margin-top: 16px;
  border-radius: 12px;
}

.discussion-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.discussion-head__main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  min-width: 0;
}

.discussion-head__title {
  font-weight: 700;
  color: #0f172a;
}

.discussion-head__toggle {
  flex-shrink: 0;
}

.discussion-body {
  min-height: 80px;
}

.discussion-list-section {
  padding-bottom: 12px;
}

.discussion-composer-section {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.discussion-composer-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 12px;
}

.discussion-composer-head > div {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.discussion-composer-body {
  margin-top: 10px;
}

.discussion-composer-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 10px;
}

.discussion-composer-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
}

.discussion-collapsed {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  color: #64748b;
  font-size: 13px;
}

.discussion-row {
  padding: 8px 0 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.discussion-row--highlighted {
  margin: 4px 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: #fff7ed;
  box-shadow: inset 3px 0 0 #f97316, 0 0 0 1px rgba(249, 115, 22, 0.22);
}

.discussion-row--assistant {
  margin: 4px 0;
  padding: 10px 12px 12px;
  border-bottom: none;
  border-radius: 12px;
  background: linear-gradient(120deg, rgba(240, 253, 244, 0.95), rgba(236, 253, 245, 0.65));
  box-shadow:
    inset 3px 0 0 0 #22c55e,
    0 0 0 1px rgba(34, 197, 94, 0.12),
    0 4px 14px rgba(15, 118, 110, 0.06);
}

.discussion-row:last-of-type {
  border-bottom: none;
}

.discussion-row__main {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.discussion-row__content {
  min-width: 0;
  flex: 1 1 auto;
}

.discussion-row__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 8px;
  margin-bottom: 4px;
  font-size: 13px;
  line-height: 1.35;
}

.discussion-row__name {
  font-weight: 600;
  color: #0f172a;
}

.discussion-row__name--assistant {
  color: #166534;
  letter-spacing: 0.02em;
}

.discussion-row__role-tag,
.discussion-row__llm-tag {
  flex-shrink: 0;
}

.discussion-row__time {
  margin-left: auto;
  color: #94a3b8;
  font-size: 11px;
  white-space: nowrap;
}

.discussion-row__body {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 14px;
  line-height: 1.5;
  color: #334155;
}

.discussion-row--assistant .discussion-row__body {
  color: #14532d;
}

.discussion-row__body--clickable {
  cursor: pointer;
}

.discussion-row__body--clickable:hover .discussion-row__text:not(.discussion-row__text--block) {
  color: #2563eb;
}

.discussion-row__text {
  display: inline;
  vertical-align: baseline;
}

.discussion-row__text--block {
  display: block;
}

.discussion-row__collapse-btn {
  margin-left: 8px;
  padding: 0;
  border: none;
  background: none;
  color: var(--el-color-primary);
  font-size: 13px;
  cursor: pointer;
  text-decoration: underline;
  vertical-align: baseline;
}

.discussion-row__collapse-btn:hover {
  color: var(--el-color-primary-light-3);
}

.discussion-row__actions {
  margin-top: 6px;
}

.discussion-pager {
  margin: 12px 0;
  justify-content: flex-end;
}

.discussion-llm-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
}

.discussion-md-demo-wrap {
  margin-top: 10px;
}

.discussion-md-image-help {
  margin-top: 10px;
  padding: 10px 12px;
  border: 1px solid #dbe4ee;
  border-radius: 10px;
  background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
}

.discussion-md-image-help__title {
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
}

.discussion-md-image-help__list {
  margin: 0 0 8px 18px;
  padding: 0;
  color: #475569;
  font-size: 12px;
  line-height: 1.6;
}

.discussion-md-image-help__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.discussion-linked-targets-toolbar {
  margin-top: 10px;
}

.discussion-md-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  margin-top: 8px;
}

.discussion-md-toolbar__hint {
  font-size: 12px;
  color: #64748b;
}

.discussion-format-bar__label {
  font-size: 12px;
  color: #64748b;
}

.discussion-input {
  margin-top: 10px;
}

.discussion-preview {
  min-height: 96px;
  margin-top: 10px;
  padding: 12px 14px;
  border: 1px dashed #dbe3ee;
  border-radius: 10px;
  background: #fafbfc;
}

.muted-text {
  color: #94a3b8;
  font-size: 14px;
}
</style>
