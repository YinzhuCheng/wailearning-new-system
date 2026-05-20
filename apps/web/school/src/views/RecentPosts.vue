<template>
  <div class="recent-posts-page">
    <header class="recent-posts-head">
      <div class="author-block">
        <el-avatar :size="56" :src="authorAvatarSrc || undefined" class="author-avatar">
          {{ authorInitial }}
        </el-avatar>
        <div class="author-text">
          <div class="author-title-row">
            <h1>{{ authorName }}</h1>
            <el-tag effect="plain" size="small">{{ roleText(author?.role) }}</el-tag>
          </div>
          <div class="author-meta">
            <span>{{ author?.username || '-' }}</span>
            <span v-if="author?.class_name">{{ author.class_name }}</span>
          </div>
        </div>
      </div>
    </header>

    <section class="filters-row">
      <el-date-picker
        v-model="dateRange"
        type="datetimerange"
        unlink-panels
        range-separator="至"
        start-placeholder="开始时间"
        end-placeholder="结束时间"
        format="YYYY-MM-DD HH:mm"
        value-format="YYYY-MM-DDTHH:mm:ssZ"
        @change="loadGroupedFeed"
      />
    </section>

    <main v-loading="loading" class="recent-posts-groups">
      <el-empty v-if="!groups.length && !loading" description="暂无可查看的发表内容" />

      <section v-for="group in groups" :key="group.kind" class="post-group">
        <button class="post-group__head" type="button" @click="toggleGroup(group.kind)">
          <span class="post-group__icon" :class="`post-group__icon--${group.kind}`">
            <el-icon>
              <component :is="kindIcon(group.kind)" />
            </el-icon>
          </span>
          <span class="post-group__title">{{ groupTitle(group) }}</span>
          <span v-if="group.latest_created_at" class="post-group__latest">最新 {{ formatTime(group.latest_created_at) }}</span>
          <el-icon class="post-group__chevron" :class="{ 'post-group__chevron--closed': !isGroupOpen(group.kind) }">
            <ArrowDown />
          </el-icon>
        </button>

        <div v-show="isGroupOpen(group.kind)" class="post-group__body">
          <article v-for="item in group.items" :key="item.id" class="post-row">
            <div class="post-row__icon" :class="`post-row__icon--${item.kind}`">
              <el-icon>
                <component :is="kindIcon(item.kind)" />
              </el-icon>
            </div>

            <div class="post-row__content">
              <div class="post-row__topline">
                <el-tag size="small" effect="plain" :type="kindTagType(item.kind)">
                  {{ kindText(item.kind) }}
                </el-tag>
                <span class="post-row__time">{{ formatTime(item.created_at) }}</span>
              </div>
              <h2>{{ item.title }}</h2>
              <p v-if="item.body_preview" class="post-row__preview">{{ item.body_preview }}</p>
              <div class="post-row__meta">
                <span v-if="item.subject_name">{{ item.subject_name }}</span>
                <span v-if="item.class_name">{{ item.class_name }}</span>
                <span v-if="item.context_title">{{ item.context_title }}</span>
                <el-tag v-if="item.has_attachment" size="small" type="info" effect="plain">附件</el-tag>
              </div>
            </div>

            <el-button type="primary" link :icon="ArrowRight" @click="openItem(item)">打开</el-button>
          </article>

          <div v-if="group.items.length < group.total" class="post-group__more">
            <el-button link type="primary" :loading="loadingMore[group.kind]" @click="loadMore(group.kind)">
              查看更多 {{ group.total - group.items.length }} 条
            </el-button>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowDown, ArrowRight, ChatDotRound, Collection, Document, EditPen, Reading } from '@element-plus/icons-vue'

import api from '@/api'
import { useUserStore } from '@/stores/user'
import { fetchAttachmentBlobUrl } from '@/utils/attachments'
import { openDiscussionLinkedTarget } from '@/utils/discussionLinkTargets'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const GROUP_LIMIT = 3
const LOAD_MORE_SIZE = 10

const loading = ref(false)
const author = ref(null)
const groups = ref([])
const openGroups = ref([])
const dateRange = ref([])
const authorAvatarSrc = ref('')
const loadingMore = reactive({})
let authorAvatarBlobUrl = ''

const isMine = computed(() => route.name === 'RecentPostsMine')
const routeUserId = computed(() => Number(route.params.userId || 0))

const authorName = computed(() => author.value?.real_name || author.value?.username || '用户')
const authorInitial = computed(() => authorName.value.trim().charAt(0) || 'U')

const roleText = role =>
  ({
    admin: '管理员',
    class_teacher: '班主任',
    teacher: '教师',
    student: '学生'
  }[role] || role || '-')

const kindText = value =>
  ({
    comment: '讨论',
    note: '笔记',
    material: '资料',
    homework: '作业',
    course: '课程'
  }[value] || '发表')

const kindTagType = value =>
  ({
    comment: 'primary',
    note: 'success',
    material: 'warning',
    homework: 'danger',
    course: 'info'
  }[value] || 'info')

const kindIcon = value =>
  ({
    comment: ChatDotRound,
    note: EditPen,
    material: Collection,
    homework: Document,
    course: Reading
  }[value] || ChatDotRound)

const groupTitle = group => `${group.label || kindText(group.kind)} ${group.total}`

const isGroupOpen = kind => openGroups.value.includes(kind)

const toggleGroup = kind => {
  if (isGroupOpen(kind)) {
    openGroups.value = openGroups.value.filter(item => item !== kind)
    return
  }
  openGroups.value = [...openGroups.value, kind]
}

const revokeAuthorAvatar = () => {
  if (authorAvatarBlobUrl) {
    URL.revokeObjectURL(authorAvatarBlobUrl)
    authorAvatarBlobUrl = ''
  }
  authorAvatarSrc.value = ''
}

const loadAuthorAvatar = async () => {
  revokeAuthorAvatar()
  if (!author.value?.avatar_url) {
    return
  }
  try {
    authorAvatarBlobUrl = await fetchAttachmentBlobUrl(author.value.avatar_url)
    authorAvatarSrc.value = authorAvatarBlobUrl
  } catch {
    revokeAuthorAvatar()
  }
}

const buildDateParams = () => {
  const params = {}
  if (Array.isArray(dateRange.value) && dateRange.value.length === 2) {
    params.from_created_at = dateRange.value[0]
    params.to_created_at = dateRange.value[1]
  }
  return params
}

const fetchGroupedFeed = params =>
  isMine.value ? api.recentPosts.mineGrouped(params) : api.recentPosts.userGrouped(routeUserId.value, params)

const fetchKindFeed = params =>
  isMine.value ? api.recentPosts.mine(params) : api.recentPosts.user(routeUserId.value, params)

const normalizeGroup = group => ({
  ...group,
  items: group?.data || []
})

const loadGroupedFeed = async () => {
  loading.value = true
  try {
    const result = await fetchGroupedFeed({
      ...buildDateParams(),
      group_limit: GROUP_LIMIT
    })
    author.value = result?.author || null
    groups.value = (result?.groups || []).map(normalizeGroup)
    openGroups.value = groups.value.map(group => group.kind)
    await loadAuthorAvatar()
  } finally {
    loading.value = false
  }
}

const loadMore = async kind => {
  const group = groups.value.find(item => item.kind === kind)
  if (!group || group.items.length >= group.total || loadingMore[kind]) {
    return
  }
  loadingMore[kind] = true
  try {
    const nextPage = Math.floor(group.items.length / LOAD_MORE_SIZE) + 1
    const result = await fetchKindFeed({
      ...buildDateParams(),
      kind,
      page: nextPage,
      page_size: LOAD_MORE_SIZE
    })
    const seen = new Set(group.items.map(item => item.id))
    const incoming = (result?.data || []).filter(item => !seen.has(item.id))
    group.items = [...group.items, ...incoming]
    group.total = Number(result?.total || group.total || 0)
  } finally {
    loadingMore[kind] = false
  }
}

const openItem = async item => {
  if (!item?.target?.available) {
    ElMessage.info('当前无法打开该内容')
    return
  }
  await openDiscussionLinkedTarget(item.target, router, userStore)
}

const formatTime = value => {
  if (!value) return ''
  try {
    return new Date(value).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return String(value)
  }
}

watch(
  () => [route.name, route.params.userId],
  () => {
    loadGroupedFeed()
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  revokeAuthorAvatar()
})
</script>

<style scoped>
.recent-posts-page {
  width: min(100%, 980px);
  margin: 0 auto;
  padding: 24px 28px 48px;
}

.recent-posts-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding-bottom: 18px;
  border-bottom: 1px solid #e5e7eb;
}

.author-block {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 14px;
}

.author-avatar {
  flex-shrink: 0;
  background: #2563eb;
  color: #fff;
  font-weight: 700;
}

.author-text {
  min-width: 0;
}

.author-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.author-title-row h1 {
  margin: 0;
  color: #111827;
  font-size: 24px;
  font-weight: 720;
  line-height: 1.25;
}

.author-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 5px;
  color: #64748b;
  font-size: 13px;
}

.filters-row {
  display: flex;
  justify-content: flex-end;
  padding: 14px 0;
}

.recent-posts-groups {
  min-height: 240px;
}

.post-group {
  border-bottom: 1px solid #e5e7eb;
}

.post-group__head {
  display: grid;
  grid-template-columns: 38px auto minmax(0, 1fr) 24px;
  align-items: center;
  width: 100%;
  gap: 12px;
  padding: 16px 0;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.post-group__icon,
.post-row__icon {
  display: grid;
  place-items: center;
  border-radius: 8px;
}

.post-group__icon {
  width: 34px;
  height: 34px;
}

.post-group__title {
  color: #0f172a;
  font-size: 17px;
  font-weight: 700;
}

.post-group__latest {
  justify-self: end;
  min-width: 0;
  color: #64748b;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.post-group__chevron {
  justify-self: end;
  color: #64748b;
  transition: transform 0.16s ease;
}

.post-group__chevron--closed {
  transform: rotate(-90deg);
}

.post-group__body {
  padding-bottom: 8px;
}

.post-row {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr) auto;
  align-items: start;
  gap: 14px;
  padding: 14px 0 16px 50px;
  border-top: 1px solid #eef2f7;
}

.post-row__icon {
  width: 38px;
  height: 38px;
}

.post-group__icon--comment,
.post-row__icon--comment {
  background: #dbeafe;
  color: #1d4ed8;
}

.post-group__icon--note,
.post-row__icon--note {
  background: #dcfce7;
  color: #15803d;
}

.post-group__icon--material,
.post-row__icon--material {
  background: #fef3c7;
  color: #b45309;
}

.post-group__icon--homework,
.post-row__icon--homework {
  background: #fee2e2;
  color: #b91c1c;
}

.post-group__icon--course,
.post-row__icon--course {
  background: #e0f2fe;
  color: #0369a1;
}

.post-row__content {
  min-width: 0;
}

.post-row__topline {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

.post-row__time {
  color: #64748b;
  font-size: 13px;
}

.post-row h2 {
  margin: 0;
  color: #0f172a;
  font-size: 16px;
  font-weight: 680;
  line-height: 1.35;
}

.post-row__preview {
  margin: 7px 0 0;
  color: #334155;
  font-size: 14px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.post-row__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  color: #64748b;
  font-size: 13px;
}

.post-group__more {
  display: flex;
  justify-content: center;
  padding: 4px 0 14px 50px;
}

@media (max-width: 720px) {
  .recent-posts-page {
    padding: 16px 14px 36px;
  }

  .recent-posts-head {
    align-items: stretch;
    flex-direction: column;
  }

  .filters-row {
    justify-content: stretch;
  }

  .filters-row :deep(.el-date-editor) {
    width: 100%;
  }

  .post-group__head {
    grid-template-columns: 34px minmax(0, 1fr) 24px;
  }

  .post-group__latest {
    grid-column: 2;
    justify-self: start;
    margin-top: -6px;
  }

  .post-row {
    grid-template-columns: 34px minmax(0, 1fr);
    padding-left: 0;
  }

  .post-row > .el-button {
    grid-column: 2;
    justify-self: start;
  }

  .post-group__more {
    justify-content: flex-start;
    padding-left: 48px;
  }
}
</style>
