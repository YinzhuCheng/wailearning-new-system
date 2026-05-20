<template>
  <div class="material-read-page" :class="`material-read-page--${materialPresentationStyle}`" v-loading="loading">
    <div
      class="material-read-layout"
      :class="{ 'material-read-layout--outline-collapsed': isOutlineCollapsed }"
      v-if="material"
    >
      <aside v-show="!isOutlineCollapsed" class="material-read-outline">
        <div class="material-read-outline__head">
          <div class="material-read-outline__heading">
            <span class="material-read-outline__eyebrow">教材目录</span>
            <strong>{{ currentChapterTitle }}</strong>
          </div>
          <el-tooltip content="收起教材目录" placement="top">
            <el-button
              class="material-read-outline__toggle"
              text
              circle
              :icon="Fold"
              aria-label="收起教材目录"
              data-testid="material-read-collapse-outline"
              @click="isOutlineCollapsed = true"
            />
          </el-tooltip>
        </div>
        <div class="material-read-outline__list">
          <section
            v-for="chapter in outlineTree"
            :key="chapter.id"
            class="material-read-outline__chapter"
          >
            <div
              class="material-read-outline__chapter-title"
              :style="{ paddingLeft: `${chapter.depth * 14}px` }"
            >
              {{ chapter.title }}
            </div>
            <div class="material-read-outline__entries">
              <button
                v-for="entry in chapter.entries"
                :key="entry.id"
                type="button"
                class="material-read-outline__item"
                :class="{ 'material-read-outline__item--active': String(entry.id) === String(route.params.id) }"
                :style="{ marginLeft: `${chapter.depth * 14}px` }"
                @click="goEntry(entry.id)"
              >
                <span class="material-read-outline__index">{{ entry.indexLabel }}</span>
                <span class="material-read-outline__title">{{ entry.title }}</span>
              </button>
            </div>
          </section>
        </div>
      </aside>

      <section class="material-read-main">
        <div class="material-read-toolbar">
          <el-tooltip v-if="isOutlineCollapsed" content="展开教材目录" placement="top">
            <el-button
              class="material-read-outline__toggle"
              text
              circle
              :icon="Expand"
              aria-label="展开教材目录"
              data-testid="material-read-expand-outline"
              @click="isOutlineCollapsed = false"
            />
          </el-tooltip>
          <el-button data-testid="material-read-back" @click="goBack">返回目录</el-button>
          <el-button data-testid="material-read-prev" :disabled="!prevEntry" @click="goPrev">上一篇</el-button>
          <el-button data-testid="material-read-next" :disabled="!nextEntry" @click="goNext">下一篇</el-button>
        </div>

        <el-alert
          v-if="breadcrumb"
          class="material-read-breadcrumb"
          type="info"
          :closable="false"
          show-icon
          :title="breadcrumb"
        />

        <article class="material-read-body">
          <h1 class="material-read-title">{{ material.title }}</h1>
          <div class="material-read-actions">
            <button type="button" class="material-read-actions__link" @click="scrollToDiscussion">
              进入讨论区
            </button>
            <span class="material-read-actions__divider" aria-hidden="true" />
            <span class="material-read-actions__hint">讨论区在正文下方，可边读边提问。</span>
            <el-button
              v-if="material.attachment_url"
              class="material-read-actions__attachment"
              type="primary"
              link
              size="small"
              @click="downloadAttach"
            >
              {{ material.attachment_name || '下载附件' }}
            </el-button>
          </div>
          <div v-if="breadcrumb" class="material-read-meta">{{ breadcrumb }}</div>
          <div class="material-read-prose">
            <PlainOrMarkdownBlock
              :text="material.content"
              :format="material.content_format"
              variant="student"
              empty-text="暂无正文"
            />
          </div>
        </article>

        <section
          v-if="currentChapterHomeworkLinks.length || currentChapterMaterials.length || looseMaterialEntries.length || looseHomeworkLinks.length"
          class="material-read-links"
        >
          <div v-if="currentChapterHomeworkLinks.length" class="material-read-links__block">
            <div class="material-read-links__head">
              <strong>本章作业</strong>
            </div>
            <div class="material-read-links__chips">
              <el-button
                v-for="link in currentChapterHomeworkLinks"
                :key="`hw-${link.link_id}`"
                size="small"
                type="primary"
                plain
                @click="openHomeworkLink(link)"
              >
                {{ link.title }}
              </el-button>
            </div>
          </div>

          <div v-if="currentChapterMaterials.length" class="material-read-links__block">
            <div class="material-read-links__head">
              <strong>本章资料</strong>
            </div>
            <div class="material-read-links__chips">
              <el-button
                v-for="entry in currentChapterMaterials"
                :key="`mat-${entry.id}`"
                size="small"
                @click="goEntry(entry.id)"
              >
                {{ entry.title }}
              </el-button>
            </div>
          </div>

          <div v-if="looseMaterialEntries.length" class="material-read-links__block">
            <div class="material-read-links__head">
              <strong>未归档资料</strong>
            </div>
            <div class="material-read-links__chips">
              <el-button
                v-for="entry in looseMaterialEntries"
                :key="`loose-${entry.id}`"
                size="small"
                @click="goEntry(entry.id)"
              >
                {{ entry.title }}
              </el-button>
            </div>
          </div>

          <div v-if="looseHomeworkLinks.length" class="material-read-links__block">
            <div class="material-read-links__head">
              <strong>未归档作业</strong>
            </div>
            <div class="material-read-links__chips">
              <el-button
                v-for="link in looseHomeworkLinks"
                :key="`loose-hw-${link.link_id}`"
                size="small"
                type="primary"
                plain
                @click="openHomeworkLink(link)"
              >
                {{ link.title }}
              </el-button>
            </div>
          </div>
        </section>

        <section v-if="material.attachment_url" class="material-read-note" aria-label="配套附件">
          <strong class="material-read-note__title">配套附件</strong>
          <p class="material-read-note__body">如需原始讲义、PDF、课件或表格文件，可从这里下载。</p>
          <el-button class="material-read-actions__attachment" type="primary" link size="small" @click="downloadAttach">
            {{ material.attachment_name || '下载附件' }}
          </el-button>
        </section>

        <section ref="discussionSection" class="material-read-discussion" aria-label="资料讨论区">
          <CourseDiscussionPanel
            target-type="material"
            :target-id="material.id"
            :subject-id="material.subject_id"
            :class-id="material.class_id"
            :discussion-requires-context="material.discussion_requires_context"
            :is-student="userStore.isStudent"
          />
        </section>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Expand, Fold } from '@element-plus/icons-vue'

import api from '@/api'
import CourseDiscussionPanel from '@/components/CourseDiscussionPanel.vue'
import PlainOrMarkdownBlock from '@/components/PlainOrMarkdownBlock.vue'
import { useUserStore } from '@/stores/user'
import { downloadAttachment } from '@/utils/attachments'
import { normalizeContentFormat } from '@/utils/contentFormat'
import { loadAllPages } from '@/utils/pagedFetch'
import {
  getMaterialPresentationStyle,
  MATERIAL_PRESENTATION_EVENT
} from '@/utils/materialPresentation'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const material = ref(null)
/** Flat navigation entries for this course: chapter DFS × materials sort order */
const sequence = ref([])
const materialPresentationStyle = ref(getMaterialPresentationStyle())
const outlineTree = ref([])
const discussionSection = ref(null)
const isOutlineCollapsed = ref(false)
const chapterHomeworkLinks = ref({})
const looseMaterialEntries = ref([])
const looseHomeworkLinks = ref([])
const uncategorizedChapterId = ref(null)

const flattenChaptersDfs = (nodes, depth = 0) => {
  const out = []
  const walk = (list, level) => {
    for (const n of list || []) {
      out.push({
        id: n.id,
        title: n.title,
        is_uncategorized: Boolean(n.is_uncategorized),
        depth: level,
        homework_links: n.homework_links || []
      })
      if (n.children?.length) walk(n.children, level + 1)
    }
  }
  walk(nodes || [], depth)
  return out
}

const buildSequence = async () => {
  const course = userStore.selectedCourse
  const classId = course?.class_id || material.value?.class_id
  if (!course?.id) {
    sequence.value = []
    outlineTree.value = []
    chapterHomeworkLinks.value = {}
    looseMaterialEntries.value = []
    looseHomeworkLinks.value = []
    uncategorizedChapterId.value = null
    return
  }
  const treeRes = await api.materialChapters.tree({ subject_id: course.id })
  const chapters = flattenChaptersDfs(treeRes?.nodes || [])
  uncategorizedChapterId.value = chapters.find(ch => ch.is_uncategorized)?.id ?? null
  const seq = []
  const outline = []
  const chapterLinks = {}
  for (const ch of chapters) {
    chapterLinks[ch.id] = ch.homework_links || []
    const rows = await loadAllPages(pager =>
      api.materials.list({
        subject_id: course.id,
        ...(classId != null ? { class_id: classId } : {}),
        chapter_id: ch.id,
        ...pager
      })
    )
    const entries = []
    let index = 0
    for (const row of rows || []) {
      index += 1
      const entry = {
        id: row.id,
        title: row.title,
        chapterTitle: ch.title,
        chapterId: ch.id,
        indexLabel: `${index}`.padStart(2, '0')
      }
      seq.push({
        ...entry
      })
      entries.push(entry)
    }
    if (entries.length) {
      outline.push({
        id: ch.id,
        title: ch.is_uncategorized ? '资料库 / 未归档' : ch.title,
        depth: ch.depth || 0,
        entries
      })
    }
  }
  const looseHomework = (chapters.find(ch => ch.is_uncategorized)?.homework_links || []).map(link => ({ ...link }))
  const looseEntries = seq
    .filter(entry => entry.chapterId === uncategorizedChapterId.value)
    .map((entry, idx) => ({
      ...entry,
      chapterTitle: '资料库 / 未归档',
      indexLabel: `${idx + 1}`.padStart(2, '0')
    }))
  chapterHomeworkLinks.value = chapterLinks
  looseMaterialEntries.value = looseEntries
  looseHomeworkLinks.value = looseHomework
  sequence.value = seq
  outlineTree.value = outline
}

const ensureCurrentMaterialInSequence = () => {
  if (!material.value || sequence.value.some(x => String(x.id) === String(material.value.id))) {
    return
  }
  const placement = material.value.placements?.[0]
  const fallbackChapterTitle = placement?.chapter_title || '当前章节'
  const entry = {
    id: material.value.id,
    title: material.value.title,
    chapterTitle: fallbackChapterTitle,
    chapterId: placement?.chapter_id || material.value.chapter_id || null,
    indexLabel: '01'
  }
  sequence.value = [entry]
  outlineTree.value = [{
    id: entry.chapterId || 'current',
    title: fallbackChapterTitle,
    depth: 0,
    entries: [entry]
  }]
}

const currentIndex = computed(() => sequence.value.findIndex(x => String(x.id) === String(route.params.id)))

const prevEntry = computed(() => {
  const i = currentIndex.value
  return i > 0 ? sequence.value[i - 1] : null
})

const nextEntry = computed(() => {
  const i = currentIndex.value
  return i >= 0 && i < sequence.value.length - 1 ? sequence.value[i + 1] : null
})

const breadcrumb = computed(() => {
  if (!material.value) return ''
  const cur = sequence.value.find(x => String(x.id) === String(material.value.id))
  const ch = cur?.chapterTitle || '—'
  const pos = currentIndex.value >= 0 ? `${currentIndex.value + 1} / ${sequence.value.length}` : ''
  return `当前章节：${ch}${pos ? ` · 阅读顺序 ${pos}` : ''}`
})

const currentChapterTitle = computed(() => {
  const cur = sequence.value.find(x => String(x.id) === String(material.value?.id))
  return cur?.chapterTitle || '当前章节'
})

const currentChapterId = computed(() => {
  const cur = sequence.value.find(x => String(x.id) === String(material.value?.id))
  return cur?.chapterId ?? null
})

const currentChapterHomeworkLinks = computed(() => {
  const chapterId = currentChapterId.value
  if (!chapterId || chapterId === uncategorizedChapterId.value) {
    return []
  }
  return chapterHomeworkLinks.value[chapterId] || []
})

const currentChapterMaterials = computed(() => {
  const chapterId = currentChapterId.value
  if (!chapterId || chapterId === uncategorizedChapterId.value) {
    return []
  }
  return sequence.value.filter(
    entry => entry.chapterId === chapterId && String(entry.id) !== String(material.value?.id)
  )
})

const loadMaterial = async () => {
  const id = Number(route.params.id)
  if (!Number.isFinite(id)) {
    ElMessage.error('无效的资料 ID')
    router.push('/materials')
    return
  }
  loading.value = true
  try {
    const row = await api.materials.get(id)
    const subjectId = row.subject_id != null ? Number(row.subject_id) : null
    // Deep links (and Playwright flows that clear localStorage) may not have selected_course
    // matching this material; sync from teaching/enrollment list when possible.
    if (subjectId && Number(userStore.selectedCourse?.id) !== subjectId) {
      await userStore.fetchTeachingCourses(true)
      const match = userStore.teachingCourses.find(c => Number(c.id) === subjectId)
      if (!match) {
        ElMessage.warning('无法在您的可选课程列表中找到该资料所属课程，请从课程入口打开。')
        router.push('/materials')
        return
      }
      userStore.setSelectedCourse(match)
    }
    material.value = {
      ...row,
      content_format: normalizeContentFormat(row.content_format)
    }
    try {
      await buildSequence()
      ensureCurrentMaterialInSequence()
    } catch (seqErr) {
      console.error(seqErr)
      ElMessage.warning('章节导航加载失败，仍可阅读正文')
      sequence.value = []
      outlineTree.value = []
      ensureCurrentMaterialInSequence()
    }
  } catch (e) {
    console.error(e)
    ElMessage.error('加载资料失败')
    router.push('/materials')
  } finally {
    loading.value = false
  }
}

const goBack = () => {
  if (userStore.isStudent) {
    router.push('/course-home')
    return
  }
  router.push('/materials')
}

const goPrev = () => {
  if (!prevEntry.value) return
  router.replace({ name: 'MaterialRead', params: { id: prevEntry.value.id } })
}

const goNext = () => {
  if (!nextEntry.value) return
  router.replace({ name: 'MaterialRead', params: { id: nextEntry.value.id } })
}

const goEntry = id => {
  router.replace({ name: 'MaterialRead', params: { id } })
}

const openHomeworkLink = link => {
  if (!link?.homework_id) {
    return
  }
  if (userStore.isStudent) {
    router.push(`/homework/${link.homework_id}/submit`)
    return
  }
  router.push(`/homework/${link.homework_id}/submissions`)
}

const downloadAttach = () => {
  if (!material.value?.attachment_url) return
  downloadAttachment(material.value.attachment_url, material.value.attachment_name)
}

const scrollToDiscussion = () => {
  discussionSection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

watch(
  () => route.params.id,
  () => {
    loadMaterial()
  },
  { immediate: true }
)

const handleMaterialPresentationStyleChange = event => {
  materialPresentationStyle.value = event?.detail || getMaterialPresentationStyle()
}

onMounted(() => {
  if (typeof window !== 'undefined') {
    window.addEventListener(MATERIAL_PRESENTATION_EVENT, handleMaterialPresentationStyleChange)
  }
})

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener(MATERIAL_PRESENTATION_EVENT, handleMaterialPresentationStyleChange)
  }
})
</script>

<style scoped>
.material-read-page {
  padding: 24px;
  min-width: 0;
  color: var(--wa-color-text);
}

.material-read-layout {
  display: grid;
  grid-template-columns: 248px minmax(0, 1fr);
  gap: 22px;
  max-width: 1280px;
  margin: 0 auto;
  align-items: start;
}

.material-read-layout--outline-collapsed {
  grid-template-columns: minmax(0, 1fr);
  max-width: 1180px;
}

.material-read-outline {
  position: sticky;
  top: 20px;
  align-self: start;
  max-height: calc(100vh - 40px);
  min-height: 132px;
  overflow: auto;
  padding: 16px 14px;
  border: 1px solid transparent;
  border-radius: var(--wa-radius-lg);
  background:
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--wa-color-surface) 96%, var(--wa-color-primary-50)) 0%,
      var(--wa-color-surface) 46%,
      color-mix(in srgb, var(--wa-color-bg-soft) 88%, var(--wa-color-accent-50)) 100%
    ) padding-box,
    linear-gradient(
      135deg,
      color-mix(in srgb, var(--wa-color-primary-500) 28%, transparent) 0%,
      color-mix(in srgb, var(--wa-color-accent-600) 18%, transparent) 55%,
      color-mix(in srgb, var(--wa-color-primary-300) 12%, transparent) 100%
    ) border-box;
  box-shadow: var(--wa-shadow-object);
  scrollbar-width: thin;
  scrollbar-color: color-mix(in srgb, var(--wa-color-primary-300) 70%, transparent) transparent;
}

.material-read-outline__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid color-mix(in srgb, var(--wa-border-subtle) 78%, transparent);
}

.material-read-outline__heading {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.material-read-outline__eyebrow {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
  color: var(--wa-color-primary-600);
}

.material-read-outline__toggle {
  width: 28px;
  height: 28px;
  flex: 0 0 28px;
  border-radius: 50%;
  color: var(--wa-color-primary-600);
}

.material-read-outline__toggle:hover {
  background: color-mix(in srgb, var(--wa-color-primary-50) 82%, #fff);
}

.material-read-outline__list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.material-read-outline__chapter {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.material-read-outline__chapter-title {
  padding: 0 4px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  color: var(--wa-color-text-muted);
}

.material-read-outline__item {
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
  width: 100%;
  padding: 9px 10px;
  border: none;
  border-radius: 12px;
  background: transparent;
  color: var(--wa-color-text-soft);
  text-align: left;
  cursor: pointer;
  transition: background 0.16s ease, box-shadow 0.16s ease, color 0.16s ease;
}

.material-read-outline__item:hover {
  background: color-mix(in srgb, var(--wa-color-primary-50) 72%, transparent);
}

.material-read-outline__item--active {
  background: color-mix(in srgb, var(--wa-color-primary-50) 86%, #fff);
  color: var(--wa-color-text);
  box-shadow: inset 3px 0 0 var(--wa-color-primary-600);
}

.material-read-outline__index {
  font-size: 12px;
  font-weight: 700;
  color: var(--wa-color-primary-600);
}

.material-read-outline__title {
  line-height: 1.55;
}

.material-read-main {
  min-width: 0;
  display: grid;
  gap: 14px;
  align-content: start;
}

.material-read-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
  width: min(100%, 860px);
  justify-self: center;
  padding: 8px 10px;
  border: 1px solid color-mix(in srgb, var(--wa-border-subtle) 76%, transparent);
  border-radius: var(--wa-radius-lg);
  background: color-mix(in srgb, var(--wa-color-surface) 90%, var(--wa-color-bg-soft));
  box-shadow: 0 4px 14px color-mix(in srgb, var(--wa-color-text) 4%, transparent);
}

.material-read-breadcrumb {
  width: min(100%, 860px);
  justify-self: center;
}

.material-read-body {
  width: min(100%, 860px);
  justify-self: center;
  padding: 24px 28px;
  border-radius: var(--wa-radius-xl);
  background: var(--wa-color-surface);
  border: 1px solid color-mix(in srgb, var(--wa-border-subtle) 86%, transparent);
  box-shadow: var(--wa-shadow-surface);
}

.material-read-title {
  margin: 0 0 16px;
  font-size: clamp(24px, 2.1vw, 30px);
  font-weight: 700;
  color: var(--wa-color-text);
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.material-read-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin: 0 0 18px;
}

.material-read-actions__link {
  border: none;
  background: transparent;
  padding: 0;
  color: var(--wa-color-primary-700);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.material-read-actions__divider {
  width: 1px;
  height: 14px;
  background: var(--wa-border-strong);
}

.material-read-actions__hint {
  color: var(--wa-color-text-muted);
  font-size: 13px;
}

.material-read-actions__attachment {
  margin-left: auto;
}

.material-read-meta {
  margin: 0 0 18px;
  color: var(--wa-color-text-muted);
  font-size: 13px;
}

.material-read-prose {
  color: var(--wa-color-text-soft);
  font-size: 16px;
  line-height: 1.9;
  overflow-wrap: anywhere;
}

.material-read-prose :deep(h1),
.material-read-prose :deep(h2),
.material-read-prose :deep(h3),
.material-read-prose :deep(h4) {
  font-family: "Noto Serif SC", "Source Han Serif SC", "Songti SC", serif;
  line-height: 1.45;
}

.material-read-prose :deep(p),
.material-read-prose :deep(li),
.material-read-prose :deep(blockquote) {
  line-height: 1.9;
}

.material-read-prose :deep(ul),
.material-read-prose :deep(ol) {
  padding-left: 1.4em;
}

.material-read-prose :deep(blockquote) {
  margin: 1.2em 0;
  padding: 0.85em 1em;
  border-left: 3px solid var(--wa-border-strong);
  background: var(--wa-color-bg-soft);
  color: var(--wa-color-text-soft);
}

.material-read-note {
  width: min(100%, 860px);
  justify-self: center;
  padding: 16px 18px;
  border: 1px solid color-mix(in srgb, var(--wa-color-primary-200) 84%, transparent);
  border-radius: var(--wa-radius-xl);
  background: color-mix(in srgb, var(--wa-color-primary-50) 82%, #fff);
}

.material-read-links {
  width: min(100%, 860px);
  justify-self: center;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.material-read-links__block {
  padding: 14px 16px;
  border: 1px solid color-mix(in srgb, var(--wa-border-subtle) 86%, transparent);
  border-radius: var(--wa-radius-lg);
  background: color-mix(in srgb, var(--wa-color-surface) 94%, var(--wa-color-bg-soft));
}

.material-read-links__head {
  margin-bottom: 10px;
  color: var(--wa-color-text);
}

.material-read-links__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.material-read-note__title {
  display: block;
  margin-bottom: 6px;
  color: var(--wa-color-text);
}

.material-read-note__body {
  margin: 0 0 8px;
  color: var(--wa-color-text-muted);
  font-size: 14px;
}

.material-read-discussion {
  width: min(100%, 860px);
  justify-self: center;
  padding-top: 8px;
  border-top: 1px solid var(--wa-border-subtle);
  scroll-margin-top: 24px;
}

.material-read-page--reader .material-read-body {
  border-radius: var(--wa-radius-2xl);
  box-shadow: var(--wa-shadow-surface);
}

.material-read-page--reader .material-read-title,
.material-read-page--reader .material-read-outline__title {
  font-family: "Noto Serif SC", "Source Han Serif SC", "Songti SC", serif;
}

.material-read-page--compact .material-read-layout {
  grid-template-columns: 232px minmax(0, 1fr);
  gap: 18px;
  max-width: 1180px;
}

.material-read-page--compact .material-read-outline {
  padding: 14px 12px;
}

.material-read-page--compact .material-read-body {
  padding: 20px 22px;
}

.material-read-page--compact .material-read-prose {
  font-size: 15px;
  line-height: 1.75;
}

@media (max-width: 960px) {
  .material-read-layout {
    grid-template-columns: 1fr;
    gap: 16px;
  }

  .material-read-outline {
    position: static;
    max-height: none;
    padding: 16px;
  }

  .material-read-toolbar,
  .material-read-breadcrumb,
  .material-read-body,
  .material-read-note,
  .material-read-discussion {
    width: 100%;
  }

  .material-read-body {
    padding: 20px;
  }

  .material-read-title {
    font-size: 24px;
    line-height: 1.28;
  }
}
</style>
