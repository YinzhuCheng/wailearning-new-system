<template>
  <div class="student-course-home">
    <div class="page-header">
      <div>
        <h1 class="page-title">课程主页</h1>
        <p class="page-subtitle">
          {{ selectedCourse ? `${selectedCourse.name} · ${selectedCourse.class_name || '未分配班级'}` : '请先从课程列表中选择一门课程。' }}
        </p>
      </div>
    </div>

    <el-empty v-if="!selectedCourse" description="请先选择一门课程。" />

    <template v-else>
      <!-- 统一：标题行 + 内容区 -->
      <section class="panel-card panel-card--overview">
        <header class="panel-header">
          <div class="panel-header__titles">
            <h2 class="panel-title">课程概览</h2>
            <p class="panel-desc">学期、任课教师与上课时间</p>
          </div>
        </header>
        <div class="overview-body">
          <div class="overview-meta">
            <span class="meta-item">
              <el-icon class="meta-icon"><Calendar /></el-icon>
              <span class="meta-label">学期</span>
              <span class="meta-value">{{ selectedCourse.semester || '未设置' }}</span>
            </span>
            <span class="meta-divider" aria-hidden="true" />
            <span class="meta-item">
              <el-icon class="meta-icon"><User /></el-icon>
              <span class="meta-label">任课老师</span>
              <span class="meta-value">{{ selectedCourse.teacher_name || '未分配' }}</span>
            </span>
          </div>
          <div class="overview-schedule">
            <div class="schedule-head">
              <span class="schedule-label">
                <el-icon><Clock /></el-icon>
                课程时间
              </span>
              <el-button
                v-if="courseTimeCards.length > 1"
                text
                type="primary"
                class="panel-link"
                @click="scheduleExpanded = !scheduleExpanded"
              >
                {{ scheduleExpanded ? '收起' : `展开全部（${courseTimeCards.length} 条）` }}
              </el-button>
            </div>
            <template v-if="visibleCourseTimes.length">
              <ul class="schedule-list">
                <li
                  v-for="(courseTime, index) in visibleCourseTimes"
                  :key="`${courseTime.dateRange}-${courseTime.weekday}-${index}`"
                  class="schedule-row"
                >
                  <span class="schedule-row__title">{{ formatCourseTimeTitle(courseTime) }}</span>
                  <span v-if="courseTime.time" class="schedule-row__time">{{ courseTime.time }}</span>
                </li>
              </ul>
            </template>
            <p v-else class="empty-inline">未设置上课时间</p>
          </div>
        </div>
      </section>

      <!-- 主区：作业优先全宽 -->
      <section class="panel-card panel-card--homework">
        <header class="panel-header">
          <div class="panel-header__titles">
            <h2 class="panel-title">课程作业</h2>
            <p class="panel-desc">最近布置的作业</p>
          </div>
          <el-button text type="primary" class="panel-link panel-link--strong" @click="router.push('/homework')">
            查看全部
          </el-button>
        </header>
        <el-skeleton :loading="loading" animated :rows="3">
          <template v-if="!homeworks.length">
            <p class="empty-inline">暂无作业。有新作业时会显示在这里；也可点击上方「查看全部」进入作业列表。</p>
          </template>
          <ul v-else class="item-list item-list--homework">
            <li v-for="item in homeworksPreview" :key="item.id">
              <button class="item-row item-row--homework" type="button" @click="router.push('/homework')">
                <el-icon class="item-row__icon"><EditPen /></el-icon>
                <span class="item-row__main">
                  <span class="item-row__title">{{ item.title }}</span>
                  <span class="item-row__meta item-row__meta--accent">截止 {{ formatDate(item.due_date) }}</span>
                </span>
              </button>
            </li>
          </ul>
        </el-skeleton>
      </section>

      <!-- 次要：资料 + 通知并排 -->
      <el-row :gutter="16" class="secondary-row">
        <el-col :xs="24" :md="12">
          <section class="panel-card">
            <header class="panel-header">
              <div class="panel-header__titles">
                <h2 class="panel-title">课程目录</h2>
                <p class="panel-desc">章节目录与最近资料</p>
              </div>
              <el-button text type="primary" class="panel-link" @click="openMaterialsReaderHome">查看全部</el-button>
            </header>
            <el-skeleton :loading="loading" animated :rows="2">
              <div v-if="materialOutlineRows.length" class="material-outline" data-testid="course-home-material-outline">
                <div class="material-outline__head">
                  <span>章节目录</span>
                  <div class="material-outline__actions">
                    <el-button text size="small" @click="expandMaterialOutline">展开</el-button>
                    <el-button text size="small" @click="collapseMaterialOutline">收起</el-button>
                  </div>
                </div>
                <ul class="material-outline__list">
                  <li
                    v-for="row in materialOutlineRows"
                    :key="row.id"
                    class="material-outline__item"
                    :style="{ '--outline-depth': row.depth }"
                  >
                    <button
                      v-if="row.hasChildren"
                      class="material-outline__toggle"
                      type="button"
                      :aria-label="isMaterialOutlineExpanded(row.id) ? '收起子章节' : '展开子章节'"
                      :title="isMaterialOutlineExpanded(row.id) ? '收起子章节' : '展开子章节'"
                      :data-testid="`course-home-material-toggle-${row.id}`"
                      @click="toggleMaterialOutline(row.id)"
                    >
                      <el-icon>
                        <Minus v-if="isMaterialOutlineExpanded(row.id)" />
                        <Plus v-else />
                      </el-icon>
                    </button>
                    <span v-else class="material-outline__toggle-spacer" aria-hidden="true" />
                    <button class="material-outline__title" type="button" @click="openChapterReader(row.id)">
                      <span>{{ row.title }}</span>
                      <el-tag v-if="row.is_uncategorized" size="small" type="info">默认</el-tag>
                    </button>
                  </li>
                </ul>
              </div>
              <template v-if="!materials.length">
                <p class="empty-inline">暂无资料。</p>
                <el-button text type="primary" size="small" class="empty-cta empty-cta--text" @click="openMaterialsReaderHome">
                  去资料库
                </el-button>
              </template>
              <ul v-else class="item-list">
                <li v-for="item in materialsPreview" :key="item.id">
                  <button class="item-row" type="button" @click="openMaterialRead(item)">
                    <el-icon class="item-row__icon item-row__icon--muted"><Document /></el-icon>
                    <span class="item-row__main">
                      <span class="item-row__title">{{ item.title }}</span>
                      <span class="item-row__meta">{{ item.creator_name || '教师' }} · {{ formatDate(item.created_at) }}</span>
                    </span>
                  </button>
                </li>
              </ul>
            </el-skeleton>
          </section>
        </el-col>
        <el-col :xs="24" :md="12">
          <section class="panel-card">
            <header class="panel-header">
              <div class="panel-header__titles">
                <h2 class="panel-title">课程通知</h2>
                <p class="panel-desc">最近收到的通知</p>
              </div>
              <el-button text type="primary" class="panel-link" @click="router.push('/notifications')">查看全部</el-button>
            </header>
            <el-skeleton :loading="loading" animated :rows="2">
              <template v-if="!notifications.length">
                <p class="empty-inline">暂无通知。</p>
                <el-button text type="primary" size="small" class="empty-cta empty-cta--text" @click="router.push('/notifications')">
                  去通知中心
                </el-button>
              </template>
              <ul v-else class="item-list">
                <li v-for="item in notificationsPreview" :key="item.id">
                  <button class="item-row" type="button" @click="router.push('/notifications')">
                    <el-icon class="item-row__icon item-row__icon--muted"><Bell /></el-icon>
                    <span class="item-row__main">
                      <span class="item-row__title">{{ item.title }}</span>
                      <span class="item-row__meta">{{ priorityText(item.priority) }} · {{ formatDate(item.created_at) }}</span>
                    </span>
                  </button>
                </li>
              </ul>
            </el-skeleton>
          </section>
        </el-col>
      </el-row>
    </template>
  </div>
</template>

<script setup>
import { Bell, Calendar, Clock, Document, EditPen, Minus, Plus, User } from '@element-plus/icons-vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import api from '@/api'
import { useUserStore } from '@/stores/user'
import { buildCourseTimeCards } from '@/utils/courseTimes'
import { onNotificationRefresh } from '@/utils/notificationSync'

const router = useRouter()
const userStore = useUserStore()

const PREVIEW_COUNT = 3

const selectedCourse = computed(() => userStore.selectedCourse)
const courseTimeCards = computed(() => buildCourseTimeCards(selectedCourse.value))
const scheduleExpanded = ref(false)

const visibleCourseTimes = computed(() => {
  const cards = courseTimeCards.value || []
  if (scheduleExpanded.value || cards.length <= 1) {
    return cards
  }
  return cards.slice(0, 1)
})

const loading = ref(false)
const materials = ref([])
const materialChapterTree = ref([])
const materialOutlineExpandedIds = ref([])
const homeworks = ref([])
const notifications = ref([])

const materialsPreview = computed(() => (materials.value || []).slice(0, PREVIEW_COUNT))
const homeworksPreview = computed(() => (homeworks.value || []).slice(0, PREVIEW_COUNT))
const notificationsPreview = computed(() => (notifications.value || []).slice(0, PREVIEW_COUNT))

const collectMaterialChapterIds = nodes => {
  const ids = []
  for (const node of nodes || []) {
    ids.push(node.id)
    ids.push(...collectMaterialChapterIds(node.children))
  }
  return ids
}

const visibleMaterialOutlineRows = (nodes, depth = 0, rows = []) => {
  for (const node of nodes || []) {
    const children = node.children || []
    const hasChildren = children.length > 0
    rows.push({
      id: node.id,
      title: node.title,
      depth,
      hasChildren,
      is_uncategorized: Boolean(node.is_uncategorized)
    })
    if (hasChildren && materialOutlineExpandedIds.value.includes(node.id)) {
      visibleMaterialOutlineRows(children, depth + 1, rows)
    }
  }
  return rows
}

const materialOutlineRows = computed(() => visibleMaterialOutlineRows(materialChapterTree.value))

const firstReadableMaterialId = computed(() => {
  const firstMaterial = materialsPreview.value?.[0] || materials.value?.[0]
  return firstMaterial?.id || null
})

const currentCourseScope = computed(() => {
  if (!selectedCourse.value) {
    return {}
  }
  return {
    subject_id: selectedCourse.value.id,
    ...(selectedCourse.value.class_id != null ? { class_id: selectedCourse.value.class_id } : {})
  }
})

const isMaterialOutlineExpanded = id => materialOutlineExpandedIds.value.includes(id)

const toggleMaterialOutline = id => {
  if (isMaterialOutlineExpanded(id)) {
    materialOutlineExpandedIds.value = materialOutlineExpandedIds.value.filter(item => item !== id)
    return
  }
  materialOutlineExpandedIds.value = [...materialOutlineExpandedIds.value, id]
}

const expandMaterialOutline = () => {
  materialOutlineExpandedIds.value = collectMaterialChapterIds(materialChapterTree.value)
}

const collapseMaterialOutline = () => {
  materialOutlineExpandedIds.value = []
}

const openMaterialRead = item => {
  if (!item?.id) {
    if (firstReadableMaterialId.value) {
      router.push({ name: 'MaterialRead', params: { id: firstReadableMaterialId.value } })
      return
    }
    router.push('/materials')
    return
  }
  router.push({ name: 'MaterialRead', params: { id: item.id } })
}

const openMaterialsReaderHome = () => {
  if (firstReadableMaterialId.value) {
    router.push({ name: 'MaterialRead', params: { id: firstReadableMaterialId.value } })
    return
  }
  router.push('/materials')
}

const openChapterReader = async chapterId => {
  if (!selectedCourse.value || !chapterId) {
    openMaterialsReaderHome()
    return
  }
  try {
    const result = await api.materials.list({
      ...currentCourseScope.value,
      chapter_id: chapterId,
      page: 1,
      page_size: 1
    })
    const first = result?.data?.[0]
    if (first?.id) {
      router.push({ name: 'MaterialRead', params: { id: first.id } })
      return
    }
  } catch (error) {
    console.error('打开章节阅读失败', error)
  }
  openMaterialsReaderHome()
}

const formatCourseTimeTitle = courseTime =>
  [courseTime?.dateRange, courseTime?.weekday].filter(Boolean).join('，')

const formatDate = value => {
  if (!value) {
    return '未设置'
  }

  return new Date(value).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const priorityText = priority => {
  const map = {
    normal: '普通',
    important: '重要',
    urgent: '紧急'
  }
  return map[priority] || '普通'
}

const loadWorkspace = async () => {
  if (!selectedCourse.value) {
    materials.value = []
    materialChapterTree.value = []
    materialOutlineExpandedIds.value = []
    homeworks.value = []
    notifications.value = []
    return
  }

  scheduleExpanded.value = false
  loading.value = true

  try {
    const [materialsResult, chapterTreeResult, homeworksResult, notificationsResult] = await Promise.all([
      api.materials.list({
        ...currentCourseScope.value,
        page: 1,
        page_size: 5
      }),
      api.materialChapters.tree({ subject_id: selectedCourse.value.id }),
      api.homework.list({
        ...currentCourseScope.value,
        page: 1,
        page_size: 5
      }),
      api.notifications.list({
        subject_id: selectedCourse.value.id,
        page: 1,
        page_size: 5
      })
    ])

    materials.value = materialsResult?.data || []
    materialChapterTree.value = chapterTreeResult?.nodes || []
    materialOutlineExpandedIds.value = collectMaterialChapterIds(materialChapterTree.value)
    homeworks.value = homeworksResult?.data || []
    notifications.value = notificationsResult?.data || []
  } finally {
    loading.value = false
  }
}

let unsubscribeNotificationRefresh = () => {}

onMounted(() => {
  loadWorkspace()
  unsubscribeNotificationRefresh = onNotificationRefresh(() => {
    loadWorkspace()
  })
})

onBeforeUnmount(() => {
  unsubscribeNotificationRefresh()
})

watch(selectedCourse, () => {
  loadWorkspace()
})
</script>

<style scoped>
.student-course-home {
  --sch-radius: 12px;
  --sch-radius-sm: 8px;
  --sch-gap: 16px;
  --sch-border: color-mix(in srgb, var(--wa-border-subtle) 86%, transparent);
  --sch-surface: var(--wa-color-surface);
  --sch-muted: var(--wa-color-text-muted);
  --sch-text: var(--wa-color-text);
  --sch-accent: var(--wa-color-primary-600);
  --sch-accent-soft: var(--wa-color-primary-50);
  --sch-row-bg: var(--wa-color-bg-soft);

  padding: 24px;
  width: min(100%, 1180px);
  max-width: 1180px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: flex-start;
  gap: var(--sch-gap);
  margin-bottom: 28px;
}

.page-title {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
  color: var(--sch-text);
  letter-spacing: 0;
}

.page-subtitle {
  margin: 6px 0 0;
  font-size: 14px;
  color: var(--sch-muted);
  line-height: 1.5;
}

/* 统一卡片外壳 */
.panel-card {
  padding: 20px;
  border: 1px solid var(--sch-border);
  border-radius: var(--sch-radius);
  background: var(--sch-surface);
  margin-bottom: var(--sch-gap);
  box-shadow: var(--wa-shadow-surface);
}

.panel-card--overview {
  box-shadow: var(--wa-shadow-surface);
}

.panel-card--homework {
  border-color: color-mix(in srgb, var(--wa-color-primary-200) 82%, transparent);
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--wa-color-primary-50) 52%, #fff) 0%, #fff 52%);
}

.panel-header {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 10px;
  margin-bottom: 16px;
}

.panel-header__titles {
  min-width: 0;
}

.panel-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--sch-text);
  line-height: 1.35;
}

.panel-desc {
  display: none;
}

.panel-link {
  align-self: flex-start;
  flex-shrink: 0;
  padding-left: 0;
  font-weight: 500;
}

.panel-link--strong {
  font-weight: 600;
}

/* 概览：高密度 meta + 时间表 */
.overview-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.overview-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 16px;
  padding: 12px 14px;
  background: var(--sch-row-bg);
  border-radius: var(--sch-radius-sm);
  border: 1px solid var(--sch-border);
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.meta-icon {
  font-size: 16px;
  color: var(--sch-muted);
}

.meta-label {
  color: var(--sch-muted);
}

.meta-value {
  font-weight: 600;
  color: var(--sch-text);
}

.meta-divider {
  width: 1px;
  height: 18px;
  background: var(--sch-border);
}

.overview-schedule {
  padding-top: 2px;
}

.schedule-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.schedule-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--sch-text);
}

.schedule-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.schedule-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 12px 14px;
  border-radius: var(--sch-radius-sm);
  background: var(--sch-row-bg);
  border: 1px solid var(--sch-border);
}

.schedule-row__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--sch-text);
}

.schedule-row__time {
  font-size: 13px;
  color: var(--sch-muted);
}

/* 列表行 */
.item-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.item-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--sch-border);
  border-radius: var(--sch-radius-sm);
  background: var(--sch-surface);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.item-row:hover {
  border-color: color-mix(in srgb, var(--wa-color-primary-300) 42%, var(--sch-border));
  background: color-mix(in srgb, var(--wa-color-primary-50) 38%, #fff);
}

.item-row--homework {
  border-color: color-mix(in srgb, var(--wa-color-primary-200) 80%, transparent);
  background: color-mix(in srgb, var(--wa-color-primary-50) 72%, #fff);
}

.item-row--homework:hover {
  border-color: color-mix(in srgb, var(--wa-color-primary-400) 52%, transparent);
  background: color-mix(in srgb, var(--wa-color-primary-50) 86%, #fff);
}

.item-row__icon {
  flex-shrink: 0;
  margin-top: 2px;
  font-size: 18px;
  color: var(--sch-accent);
}

.item-row__icon--muted {
  color: var(--wa-color-text-muted);
}

.item-row__main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.item-row__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--sch-text);
  line-height: 1.4;
}

.item-row__meta {
  font-size: 12px;
  color: var(--sch-muted);
}

.item-row__meta--accent {
  color: #1d4ed8;
  font-weight: 500;
}

.material-outline {
  margin-bottom: 12px;
  padding: 12px;
  border: 1px solid var(--sch-border);
  border-radius: var(--sch-radius-sm);
  background:
    linear-gradient(180deg, rgba(248, 250, 252, 0.88), rgba(255, 255, 255, 0.96)),
    var(--sch-surface);
}

.material-outline__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  color: var(--sch-text);
  font-size: 13px;
  font-weight: 600;
}

.material-outline__actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.material-outline__actions :deep(.el-button) {
  height: 24px;
  padding: 0 8px;
  border-radius: 7px;
}

.material-outline__list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.material-outline__item {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  padding-left: calc(var(--outline-depth, 0) * 18px);
}

.material-outline__toggle,
.material-outline__toggle-spacer {
  width: 24px;
  height: 24px;
  flex: 0 0 24px;
}

.material-outline__toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(37, 99, 235, 0.22);
  border-radius: 7px;
  background: rgba(239, 246, 255, 0.86);
  color: var(--sch-accent);
  cursor: pointer;
  transition: background 0.16s ease, border-color 0.16s ease, transform 0.16s ease;
}

.material-outline__toggle:hover {
  border-color: rgba(37, 99, 235, 0.38);
  background: #dbeafe;
  transform: scale(1.06);
}

.material-outline__toggle:focus-visible {
  outline: 2px solid rgba(37, 99, 235, 0.32);
  outline-offset: 2px;
}

.material-outline__title {
  display: inline-flex;
  min-width: 0;
  flex: 1;
  align-items: center;
  gap: 6px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  padding: 5px 7px;
  color: var(--sch-text);
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: background 0.16s ease, color 0.16s ease;
}

.material-outline__title:hover {
  background: rgba(37, 99, 235, 0.06);
  color: var(--sch-accent);
}

.material-outline__title span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-inline {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--sch-muted);
  line-height: 1.5;
}

.empty-cta {
  margin-top: 2px;
}

.empty-cta--text {
  padding-left: 0;
  height: auto;
}

.secondary-row {
  margin-top: 0;
}

@media (max-width: 768px) {
  .student-course-home {
    padding: 16px;
  }

  .meta-divider {
    display: none;
  }

  .overview-meta {
    flex-direction: column;
    align-items: flex-start;
  }

  .material-outline__item {
    padding-left: calc(var(--outline-depth, 0) * 14px);
  }
}
</style>
