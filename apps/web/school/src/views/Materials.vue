<template>
  <div class="materials-page" :class="`materials-page--${materialPresentationStyle}`">
    <div class="page-header">
      <div>
        <h1 class="page-title">课程目录</h1>
        <p class="page-subtitle">
          {{ selectedCourse ? `${selectedCourse.name} · ${selectedCourse.class_name || '未分配班级'}` : '请先选择课程后查看目录。' }}
        </p>
      </div>
      <div class="header-actions">
        <el-button v-if="!userStore.isStudent && selectedCourse" type="primary" @click="openCreateDialog">
          发布资料
        </el-button>
      </div>
    </div>

    <el-empty v-if="!selectedCourse" description="请先选择一门课程。" />

    <template v-else>
      <div
        v-if="selectedCourse.cover_image_url"
        class="materials-course-cover"
        data-testid="materials-course-cover-banner"
      >
        <el-image
          :src="selectedCourse.cover_image_url"
          fit="cover"
          class="materials-course-cover__image"
        />
      </div>

      <div class="materials-layout" :class="{ 'materials-layout--outline-collapsed': isChapterSidebarCollapsed }">
        <aside
          v-show="!isChapterSidebarCollapsed"
          class="chapter-sidebar"
          :class="{ 'chapter-sidebar--narrow': userStore.isStudent }"
        >
          <div class="chapter-sidebar__head">
            <div class="chapter-sidebar__heading">
              <span class="chapter-sidebar__eyebrow">课程目录</span>
              <span class="chapter-sidebar__title">章节</span>
              <span class="chapter-sidebar__meta">{{ chapterSummaryText }}</span>
            </div>
            <div class="chapter-sidebar__actions">
              <el-tooltip content="展开全部章节" placement="top">
                <el-button
                  class="chapter-outline-btn"
                  text
                  circle
                  :icon="Expand"
                  aria-label="展开全部章节"
                  data-testid="materials-expand-all-chapters"
                  @click="expandAllChapters"
                />
              </el-tooltip>
              <el-tooltip content="收起全部章节" placement="top">
                <el-button
                  class="chapter-outline-btn"
                  text
                  circle
                  :icon="Fold"
                  aria-label="收起全部章节"
                  data-testid="materials-collapse-all-chapters"
                  @click="collapseAllChapters"
                />
              </el-tooltip>
              <el-tooltip content="收起课程目录" placement="top">
                <el-button
                  class="chapter-outline-btn"
                  text
                  circle
                  :icon="Fold"
                  aria-label="收起课程目录"
                  data-testid="materials-collapse-chapter-sidebar"
                  @click="isChapterSidebarCollapsed = true"
                />
              </el-tooltip>
              <el-button v-if="canManageChapters" type="primary" plain size="small" @click="openAddChapterDialog(null)">根章节</el-button>
            </div>
          </div>
          <el-skeleton v-if="treeLoading" :rows="6" animated />
          <el-tree
            v-else
            ref="treeRef"
            class="chapter-tree"
            :data="chapterTreeNodes"
            node-key="id"
            :props="{ label: 'title', children: 'children' }"
            highlight-current
            :expand-on-click-node="false"
            :draggable="canManageChapters"
            :allow-drop="allowChapterDrop"
            :default-expanded-keys="expandedChapterKeys"
            @node-click="handleChapterClick"
            @node-expand="handleChapterExpand"
            @node-collapse="handleChapterCollapse"
            @node-drop="handleChapterDrop"
          >
            <template #default="{ node, data }">
              <button
                v-if="isChapterExpandable(data)"
                class="chapter-node-toggle"
                type="button"
                :aria-label="node.expanded ? '收起子章节' : '展开子章节'"
                :title="node.expanded ? '收起子章节' : '展开子章节'"
                :data-testid="`materials-chapter-toggle-${data.id}`"
                @click.stop="toggleChapterExpansion(node, data)"
              >
                <el-icon>
                  <Minus v-if="node.expanded" />
                  <Plus v-else />
                </el-icon>
              </button>
              <span v-else class="chapter-node-toggle-spacer" aria-hidden="true" />
              <button
                type="button"
                class="tree-node-label"
                :class="{ 'tree-node-label--uncategorized': data.is_uncategorized }"
                @click.stop="handleChapterClick(data)"
                @dblclick.stop="openChapterRead(data)"
              >
                <span class="tree-node-label__title">{{ displayChapterTitle(data) }}</span>
                <el-tag v-if="data.is_uncategorized" size="small" type="info" class="tree-tag">资料库</el-tag>
              </button>
              <span v-if="canManageChapters && !data.is_uncategorized" class="tree-node-actions" @click.stop>
                <el-button link type="primary" size="small" @click="openRenameChapterDialog(data)">重命名</el-button>
                <el-button link type="primary" size="small" @click="openAddChapterDialog(data.id)">子章节</el-button>
                <el-button link type="danger" size="small" @click="confirmDeleteChapter(data)">删除</el-button>
              </span>
            </template>
          </el-tree>
        </aside>

        <section class="materials-main">
          <div class="materials-toolbar">
            <div class="materials-toolbar__summary">
              <el-tooltip v-if="isChapterSidebarCollapsed" content="展开课程目录" placement="top">
                <el-button
                  class="chapter-outline-btn materials-toolbar__outline-toggle"
                  text
                  circle
                  :icon="Expand"
                  aria-label="展开课程目录"
                  data-testid="materials-expand-chapter-sidebar"
                  @click="isChapterSidebarCollapsed = false"
                />
              </el-tooltip>
              <div class="materials-toolbar__text">
                <span class="materials-toolbar__eyebrow">当前章节</span>
                <strong data-testid="materials-current-chapter">{{ currentChapterTitle }}</strong>
                <span class="materials-toolbar__count">
                  {{ materials.length }} 篇资料 · {{ currentChapterHomeworkLinks.length }} 个作业
                </span>
              </div>
            </div>
            <div class="materials-toolbar__actions">
              <el-button type="primary" text size="small" @click="openFirstMaterialReadInChapter">
                进入本章阅读
              </el-button>
              <el-button text size="small" @click="isMaterialShelfCollapsed = !isMaterialShelfCollapsed">
                {{ isMaterialShelfCollapsed ? '展开资料列表' : '收起资料列表' }}
              </el-button>
            </div>
          </div>

          <div class="chapter-homework-panel" data-testid="materials-homework-links-panel">
            <div class="chapter-homework-panel__head">
              <div>
                <span class="materials-toolbar__eyebrow">关联作业</span>
                <strong>{{ currentChapterTitle }}</strong>
              </div>
              <el-button
                v-if="canManageChapters && selectedChapterId"
                type="primary"
                plain
                size="small"
                data-testid="materials-add-homework-link"
                @click="openHomeworkLinkDialog"
              >
                添加作业链接
              </el-button>
            </div>
            <el-empty
              v-if="!currentChapterHomeworkLinks.length"
              description="当前章节暂无关联作业"
              :image-size="72"
            />
            <div v-else class="chapter-homework-list">
              <article
                v-for="link in currentChapterHomeworkLinks"
                :key="link.link_id"
                class="chapter-homework-card"
                data-testid="materials-homework-link-card"
                @click="openHomeworkLink(link)"
              >
                <div class="chapter-homework-card__main">
                  <span class="chapter-homework-card__type">作业</span>
                  <strong>{{ link.title }}</strong>
                  <span class="chapter-homework-card__meta">
                    {{ link.subject_name || selectedCourse?.name || '课程作业' }}
                    <template v-if="link.due_date"> · 截止 {{ formatDate(link.due_date) }}</template>
                  </span>
                </div>
                <div class="chapter-homework-card__actions" @click.stop>
                  <el-button type="primary" link size="small" @click="openHomeworkLink(link)">打开</el-button>
                  <el-button
                    v-if="canManageChapters"
                    type="danger"
                    link
                    size="small"
                    @click="removeHomeworkLink(link)"
                  >
                    移除
                  </el-button>
                </div>
              </article>
            </div>
          </div>

          <el-card v-show="!isMaterialShelfCollapsed" shadow="never" class="materials-shelf-card">
            <div class="materials-shelf-card__head">
              <div>
                <span class="materials-toolbar__eyebrow">资料列表</span>
                <strong>{{ currentChapterTitle }}</strong>
              </div>
              <span>{{ materials.length }} 篇</span>
            </div>
            <DualHorizontalScroll target-selector=".materials-table-scroll">
              <div class="materials-table-scroll dual-scroll-target">
                <el-table
                  :data="materials"
                  v-loading="loading"
                  row-key="id"
                  @row-click="viewMaterial"
                >
              <el-table-column prop="title" label="资料标题" min-width="200" align="center" header-align="center" />
              <el-table-column v-if="showPlacementColumn" label="所在章节" min-width="180" align="center" header-align="center">
                <template #default="{ row }">
                  {{ placementSummary(row) }}
                </template>
              </el-table-column>
              <el-table-column label="附件" width="120" align="center" header-align="center">
                <template #default="{ row }">
                  <el-button v-if="row.attachment_url" type="primary" link @click.stop="openAttachment(row)">
                    下载
                  </el-button>
                  <span v-else class="muted-text">无</span>
                </template>
              </el-table-column>
              <el-table-column prop="creator_name" label="发布人" width="100" align="center" header-align="center" />
              <el-table-column prop="created_at" label="发布时间" width="170" align="center" header-align="center">
                <template #default="{ row }">
                  {{ formatDate(row.created_at) }}
                </template>
              </el-table-column>
              <el-table-column label="阅读" width="96" align="center" header-align="center">
                <template #default="{ row }">
                  <el-button
                    type="primary"
                    link
                    size="small"
                    data-testid="materials-open-read-page"
                    @click.stop="openMaterialRead(row)"
                  >
                    阅读页
                  </el-button>
                </template>
              </el-table-column>
              <el-table-column v-if="canManageChapters" label="排序" width="100" align="center" header-align="center">
                <template #default="{ row, $index }">
                  <el-button
                    link
                    type="primary"
                    size="small"
                    :disabled="$index === 0"
                    @click.stop="moveMaterial(row, -1)"
                  >
                    上移
                  </el-button>
                  <el-button
                    link
                    type="primary"
                    size="small"
                    :disabled="$index >= materials.length - 1"
                    @click.stop="moveMaterial(row, 1)"
                  >
                    下移
                  </el-button>
                </template>
              </el-table-column>
              <el-table-column v-if="!userStore.isStudent" label="操作" width="240" fixed="right" align="center" header-align="center">
                <template #default="{ row }">
                  <div class="wa-table-actions">
                    <el-button
                      v-if="canEditMaterial(row)"
                      type="primary"
                      link
                      size="small"
                      @click.stop="openEditDialog(row)"
                    >
                      编辑
                    </el-button>
                    <el-button
                      v-if="canManageChapters"
                      type="primary"
                      link
                      size="small"
                      @click.stop="openPlacementDialog(row)"
                    >
                      引用
                    </el-button>
                    <el-button
                      v-if="canDeleteMaterial(row)"
                      type="danger"
                      link
                      size="small"
                      @click.stop="deleteMaterial(row)"
                    >
                      删除
                    </el-button>
                  </div>
                </template>
              </el-table-column>
                </el-table>
              </div>
            </DualHorizontalScroll>
          </el-card>
        </section>
      </div>
    </template>

    <!-- 发布 / 编辑 -->
    <el-dialog v-model="dialogVisible" :title="editingMaterial ? '编辑资料' : '发布资料'" width="900px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="资料标题" prop="title">
          <el-input v-model="form.title" />
        </el-form-item>
        <el-form-item label="所属章节" prop="chapter_ids">
          <el-select
            v-model="form.chapter_ids"
            multiple
            filterable
            placeholder="可选择多个章节（引用）"
            style="width: 100%"
          >
            <el-option v-for="opt in flatChapterOptions" :key="opt.id" :label="opt.label" :value="opt.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="资料说明" prop="content">
          <MarkdownEditorPanel
            v-model="form.content"
            v-model:content-format="form.content_format"
            :min-rows="6"
            :max-rows="24"
            placeholder="支持 Markdown、LaTeX（$...$ / $$...$$）、本地上传或 URL 插图"
            hint="工具栏可插入格式；图片会插入为 Markdown，学生与教师预览一致。"
            :show-format-toggle="true"
          />
        </el-form-item>
        <el-form-item label="附件">
          <el-upload :auto-upload="false" :show-file-list="false" :limit="1" :on-change="handleAttachmentChange">
            <el-button>选择附件</el-button>
          </el-upload>
          <div class="attachment-help">{{ attachmentHintText }}</div>
          <div v-if="attachmentDisplayName" class="attachment-preview">
            <el-button v-if="form.attachment_url" type="primary" link @click="downloadFormAttachment">
              {{ attachmentDisplayName }}
            </el-button>
            <span v-else>{{ attachmentDisplayName }}</span>
            <el-button link type="danger" @click="removeAttachment">移除</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>

    <!-- 详情 -->
    <el-dialog v-model="detailVisible" title="资料详情" width="900px" destroy-on-close>
      <el-descriptions v-if="currentMaterial" :column="2" border>
        <el-descriptions-item label="资料标题" :span="2">{{ currentMaterial.title }}</el-descriptions-item>
        <el-descriptions-item label="章节" :span="2">
          {{ placementSummary(currentMaterial) }}
        </el-descriptions-item>
        <el-descriptions-item label="课程">{{ currentMaterial.subject_name || selectedCourse?.name }}</el-descriptions-item>
        <el-descriptions-item label="发布人">{{ currentMaterial.creator_name }}</el-descriptions-item>
        <el-descriptions-item label="发布时间">{{ formatDate(currentMaterial.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="资料说明" :span="2">
          <PlainOrMarkdownBlock
            :text="currentMaterial.content"
            :format="currentMaterial.content_format"
            variant="student"
            empty-text="暂无说明"
          />
        </el-descriptions-item>
        <el-descriptions-item label="附件" :span="2">
          <el-button v-if="currentMaterial.attachment_url" type="primary" link @click="openAttachment(currentMaterial)">
            {{ currentMaterial.attachment_name || '下载附件' }}
          </el-button>
          <span v-else class="muted-text">无附件</span>
        </el-descriptions-item>
      </el-descriptions>
      <CourseDiscussionPanel
        v-if="currentMaterial"
        target-type="material"
        :target-id="currentMaterial.id"
        :subject-id="currentMaterial.subject_id"
        :class-id="currentMaterial.class_id"
        :discussion-requires-context="currentMaterial.discussion_requires_context"
        :is-student="userStore.isStudent"
      />
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button type="primary" @click="openMaterialReadFromDetail">阅读页</el-button>
      </template>
    </el-dialog>

    <!-- 重命名章节 -->
    <el-dialog v-model="renameChapterVisible" title="重命名章节" width="420px" destroy-on-close>
      <el-input v-model="renameChapterTitle" maxlength="120" show-word-limit />
      <template #footer>
        <el-button @click="renameChapterVisible = false">取消</el-button>
        <el-button type="primary" :loading="renameChapterSubmitting" @click="submitRenameChapter">保存</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="chapterDialogVisible" :title="chapterParentId ? '新增子章节' : '新增根章节'" width="420px" destroy-on-close>
      <el-input v-model="newChapterTitle" placeholder="章节名称" maxlength="120" show-word-limit />
      <template #footer>
        <el-button @click="chapterDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="chapterSubmitting" @click="submitNewChapter">确定</el-button>
      </template>
    </el-dialog>

    <!-- 附加引用 -->
    <el-dialog v-model="placementDialogVisible" title="附加到其他章节" width="480px" destroy-on-close>
      <p class="muted-text">同一资料可出现在多个章节；此处为新增引用，不影响原有章节中的条目。</p>
      <el-select v-model="extraChapterId" placeholder="选择章节" filterable style="width: 100%">
        <el-option
          v-for="opt in placementExtraOptions"
          :key="opt.id"
          :label="opt.label"
          :value="opt.id"
        />
      </el-select>
      <template #footer>
        <el-button @click="placementDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="placementSubmitting" @click="submitExtraPlacement">添加引用</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="homeworkLinkDialogVisible"
      title="添加作业链接"
      width="min(720px, calc(100vw - 28px))"
      destroy-on-close
    >
      <div class="homework-link-picker">
        <el-input
          v-model="homeworkSearchText"
          clearable
          placeholder="按作业标题搜索"
          data-testid="materials-homework-link-search"
        />
        <div v-loading="homeworkPickerLoading" class="homework-link-picker__results">
          <el-empty v-if="!homeworkPickerLoading && !homeworkPickerRows.length" description="没有找到可关联的作业" />
          <div
            v-for="item in homeworkPickerRows"
            :key="item.target_id"
            class="homework-link-picker__row"
            data-testid="materials-homework-link-option"
          >
            <div class="homework-link-picker__meta">
              <strong>{{ item.title }}</strong>
              <span>{{ item.secondary_text || selectedCourse?.name || '课程作业' }}</span>
            </div>
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="linkedHomeworkIds.has(Number(item.target_id))"
              @click="addHomeworkLink(item)"
            >
              {{ linkedHomeworkIds.has(Number(item.target_id)) ? '已关联' : '关联' }}
            </el-button>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="homeworkLinkDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Expand, Fold, Minus, Plus } from '@element-plus/icons-vue'

import api from '@/api'
import CourseDiscussionPanel from '@/components/CourseDiscussionPanel.vue'
import DualHorizontalScroll from '@/components/DualHorizontalScroll.vue'
import MarkdownEditorPanel from '@/components/MarkdownEditorPanel.vue'
import PlainOrMarkdownBlock from '@/components/PlainOrMarkdownBlock.vue'
import { useUserStore } from '@/stores/user'
import { attachmentHintText, downloadAttachment, validateAttachmentFile } from '@/utils/attachments'
import { normalizeContentFormat } from '@/utils/contentFormat'
import {
  getMaterialPresentationStyle,
  MATERIAL_PRESENTATION_EVENT
} from '@/utils/materialPresentation'
import { openDiscussionLinkedTarget } from '@/utils/discussionLinkTargets'

const userStore = useUserStore()
const router = useRouter()

const loading = ref(false)
const treeLoading = ref(false)
const submitting = ref(false)
const chapterSubmitting = ref(false)
const renameChapterSubmitting = ref(false)
const placementSubmitting = ref(false)
const dialogVisible = ref(false)
const detailVisible = ref(false)
const chapterDialogVisible = ref(false)
const renameChapterVisible = ref(false)
const placementDialogVisible = ref(false)
const homeworkLinkDialogVisible = ref(false)
const currentMaterial = ref(null)
const editingMaterial = ref(null)
const materials = ref([])
const formRef = ref(null)
const attachmentFile = ref(null)
const chapterTreeNodes = ref([])
const selectedChapterId = ref(null)
const treeRef = ref(null)
const expandedChapterKeys = ref([])
const isChapterSidebarCollapsed = ref(false)
const isMaterialShelfCollapsed = ref(false)
const materialPresentationStyle = ref(getMaterialPresentationStyle())
const newChapterTitle = ref('')
const chapterParentId = ref(null)
const renameChapterId = ref(null)
const renameChapterTitle = ref('')
const placementTarget = ref(null)
const extraChapterId = ref(null)
const homeworkSearchText = ref('')
const homeworkPickerRows = ref([])
const homeworkPickerLoading = ref(false)
let homeworkPickerDebounceTimer = null

const selectedCourse = computed(() => userStore.selectedCourse)
const attachmentDisplayName = computed(() => attachmentFile.value?.name || form.attachment_name || '')
const expandedStorageKey = computed(() =>
  selectedCourse.value?.id ? `courseeval-materials-expanded-chapters:${selectedCourse.value.id}` : null
)
const currentCourseScope = computed(() => {
  if (!selectedCourse.value) {
    return {}
  }
  return {
    subject_id: selectedCourse.value.id,
    ...(selectedCourse.value.class_id != null ? { class_id: selectedCourse.value.class_id } : {})
  }
})

const isCourseInstructor = computed(() => {
  const c = selectedCourse.value
  const uid = userStore.userInfo?.id
  if (!c || uid == null) return false
  return Number(c.teacher_id) === Number(uid)
})

const canManageChapters = computed(
  () => !userStore.isStudent && selectedCourse.value && (userStore.isAdmin || isCourseInstructor.value)
)

const showPlacementColumn = computed(() => !userStore.isStudent)

const form = reactive({
  title: '',
  content: '',
  content_format: 'markdown',
  attachment_name: '',
  attachment_url: '',
  remove_attachment: false,
  chapter_ids: []
})

const rules = {
  title: [{ required: true, message: '请输入资料标题', trigger: 'blur' }],
  chapter_ids: [{ required: true, message: '请选择至少一个章节', trigger: 'change' }]
}

const flattenTree = (nodes, depth = 0, acc = []) => {
  for (const n of nodes || []) {
    acc.push({ ...n, depth })
    if (n.children?.length) flattenTree(n.children, depth + 1, acc)
  }
  return acc
}

const firstStructuredChapterId = nodes => {
  for (const n of nodes || []) {
    if (!n.is_uncategorized) return n.id
  }
  return nodes?.[0]?.id || null
}

const displayChapterTitle = data => (data?.is_uncategorized ? '资料库 / 未归档' : data?.title || '—')

const collectChapterIds = nodes => {
  const ids = []
  for (const n of nodes || []) {
    ids.push(n.id)
    ids.push(...collectChapterIds(n.children))
  }
  return ids
}

const countStructuredChapters = nodes => {
  let total = 0
  for (const n of nodes || []) {
    if (!n.is_uncategorized) {
      total += 1
    }
    total += countStructuredChapters(n.children)
  }
  return total
}

const topLevelChapterIds = nodes => (nodes || []).map(n => n.id).filter(Boolean)

const findChapterPath = (nodes, targetId, path = []) => {
  for (const n of nodes || []) {
    const nextPath = [...path, n.id]
    if (String(n.id) === String(targetId)) {
      return nextPath
    }
    const childPath = findChapterPath(n.children, targetId, nextPath)
    if (childPath.length) {
      return childPath
    }
  }
  return []
}

const persistExpandedChapterKeys = () => {
  if (!expandedStorageKey.value || typeof window === 'undefined') {
    return
  }
  window.localStorage.setItem(expandedStorageKey.value, JSON.stringify(expandedChapterKeys.value))
}

const restoreExpandedChapterKeys = nodes => {
  if (expandedStorageKey.value && typeof window !== 'undefined') {
    try {
      const raw = window.localStorage.getItem(expandedStorageKey.value)
      if (raw) {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) {
          const valid = new Set(collectChapterIds(nodes))
          return parsed.filter(id => valid.has(id))
        }
      }
    } catch (error) {
      console.warn('恢复章节展开状态失败', error)
    }
  }

  return topLevelChapterIds(nodes)
}

const syncTreeExpandedState = () => {
  const open = new Set(expandedChapterKeys.value.map(id => String(id)))
  for (const id of collectChapterIds(chapterTreeNodes.value)) {
    const node = treeRef.value?.getNode?.(id)
    if (node) {
      if (open.has(String(id))) {
        node.expand?.()
      } else {
        node.collapse?.()
      }
    }
  }
}

const ensureSelectedChapterPathExpanded = () => {
  if (!selectedChapterId.value) {
    return
  }
  const next = new Set(expandedChapterKeys.value)
  for (const id of findChapterPath(chapterTreeNodes.value, selectedChapterId.value)) {
    next.add(id)
  }
  expandedChapterKeys.value = Array.from(next)
}

const expandAllChapters = () => {
  expandedChapterKeys.value = collectChapterIds(chapterTreeNodes.value)
  syncTreeExpandedState()
  persistExpandedChapterKeys()
}

const collapseAllChapters = () => {
  expandedChapterKeys.value = []
  syncTreeExpandedState()
  persistExpandedChapterKeys()
}

const isChapterExpandable = data => Boolean(data?.children?.length)

const toggleChapterExpansion = (node, data) => {
  if (!isChapterExpandable(data)) {
    return
  }
  if (node?.expanded) {
    node.collapse?.()
  } else if (node?.expand) {
    node.expand()
  } else {
    const current = new Map(expandedChapterKeys.value.map(id => [String(id), id]))
    const key = String(data.id)
    if (current.has(key)) {
      current.delete(key)
    } else {
      current.set(key, data.id)
    }
    expandedChapterKeys.value = Array.from(current.values())
    syncTreeExpandedState()
    persistExpandedChapterKeys()
  }
}

const flatChapterOptions = computed(() => {
  const flat = flattenTree(chapterTreeNodes.value)
  return flat.map(n => ({
    id: n.id,
    label: `${'　'.repeat(n.depth)}${n.title}`
  }))
})

const currentChapterTitle = computed(() => {
  const flat = flattenTree(chapterTreeNodes.value)
  const row = flat.find(x => x.id === selectedChapterId.value)
  return row?.title || '—'
})

const currentChapter = computed(() => {
  const flat = flattenTree(chapterTreeNodes.value)
  return flat.find(x => x.id === selectedChapterId.value) || null
})

const currentChapterHomeworkLinks = computed(() => currentChapter.value?.homework_links || [])

const linkedHomeworkIds = computed(
  () => new Set(currentChapterHomeworkLinks.value.map(item => Number(item.homework_id)))
)

const chapterSummaryText = computed(() => {
  const total = countStructuredChapters(chapterTreeNodes.value)
  const expanded = expandedChapterKeys.value.length
  if (!total) {
    return '暂无章节'
  }
  return `${total} 个章节 · 已展开 ${Math.min(expanded, total)} 个`
})

const findUncategorizedId = nodes => {
  for (const n of nodes || []) {
    if (n.is_uncategorized) return n.id
    const inner = findUncategorizedId(n.children)
    if (inner) return inner
  }
  return null
}

const handleChapterClick = data => {
  selectedChapterId.value = data.id
  ensureSelectedChapterPathExpanded()
  persistExpandedChapterKeys()
}

const handleChapterExpand = data => {
  expandedChapterKeys.value = Array.from(new Set([...expandedChapterKeys.value, data.id]))
  persistExpandedChapterKeys()
}

const handleChapterCollapse = data => {
  expandedChapterKeys.value = expandedChapterKeys.value.filter(id => String(id) !== String(data.id))
  persistExpandedChapterKeys()
}

const allowChapterDrop = (draggingNode, dropNode, type) => {
  if (draggingNode.data.is_uncategorized) return false
  if (type === 'inner' && dropNode.data.is_uncategorized) return false
  return true
}

const loadChapterTree = async () => {
  if (!selectedCourse.value) {
    chapterTreeNodes.value = []
    return
  }
  treeLoading.value = true
  try {
    const res = await api.materialChapters.tree({ subject_id: selectedCourse.value.id })
    chapterTreeNodes.value = res?.nodes || []
    if (!selectedChapterId.value) {
      selectedChapterId.value =
        firstStructuredChapterId(chapterTreeNodes.value) || findUncategorizedId(chapterTreeNodes.value) || null
    }
    expandedChapterKeys.value = restoreExpandedChapterKeys(chapterTreeNodes.value)
    ensureSelectedChapterPathExpanded()
  } finally {
    treeLoading.value = false
    await nextTick()
    syncTreeExpandedState()
  }
}

const loadMaterials = async () => {
  if (!selectedCourse.value) {
    materials.value = []
    return
  }

  loading.value = true
  try {
    const result = await api.materials.list({
      ...currentCourseScope.value,
      chapter_id: selectedChapterId.value || undefined,
      page: 1,
      page_size: 100
    })
    materials.value = result?.data || []
    if (userStore.isStudent && materials.value.length && !currentMaterial.value && !detailVisible.value) {
      openMaterialRead(materials.value[0])
      return
    }
  } finally {
    loading.value = false
  }
}

const handleChapterDrop = async (draggingNode, dropNode, dropType) => {
  if (!canManageChapters.value || !selectedCourse.value) return

  let parentNode = null
  if (dropType === 'inner') {
    parentNode = dropNode
  } else {
    parentNode = draggingNode.parent
  }

  const siblings = parentNode?.childNodes || []
  const orderedIds = siblings.map(cn => cn.data).filter(d => d && !d.is_uncategorized).map(d => d.id)
  const parentId =
    parentNode?.level === 0 || parentNode?.data == null ? null : parentNode?.data?.id ?? null

  if (!orderedIds.length) return

  try {
    await api.materialChapters.reorderChapters(selectedCourse.value.id, {
      parent_id: parentId,
      ordered_chapter_ids: orderedIds
    })
    ElMessage.success('章节顺序已更新')
    await loadChapterTree()
    persistExpandedChapterKeys()
  } catch (e) {
    console.error(e)
    await loadChapterTree()
  }
}

const moveMaterial = async (row, delta) => {
  if (!canManageChapters.value || !selectedChapterId.value) return
  const idx = materials.value.findIndex(m => m.id === row.id)
  const nidx = idx + delta
  if (idx < 0 || nidx < 0 || nidx >= materials.value.length) return

  const list = [...materials.value]
  const [removed] = list.splice(idx, 1)
  list.splice(nidx, 0, removed)

  const orderedSectionIds = list
    .map(m => m.placements?.find(p => p.chapter_id === selectedChapterId.value)?.section_id)
    .filter(Boolean)
  if (orderedSectionIds.length !== list.length) {
    ElMessage.error('无法排序：缺少章节映射')
    return
  }

  try {
    await api.materialChapters.reorderSections(selectedCourse.value.id, {
      chapter_id: selectedChapterId.value,
      ordered_section_ids: orderedSectionIds
    })
    ElMessage.success('顺序已更新')
    await loadMaterials()
  } catch (e) {
    console.error(e)
    await loadMaterials()
  }
}

const placementSummary = row => {
  const ps = row?.placements || []
  if (!ps.length) return '—'
  return ps.map(p => p.chapter_title).join('、')
}

const resetForm = () => {
  form.title = ''
  form.content = ''
  form.content_format = 'markdown'
  form.attachment_name = ''
  form.attachment_url = ''
  form.remove_attachment = false
  form.chapter_ids = []
  attachmentFile.value = null
}

const openCreateDialog = () => {
  editingMaterial.value = null
  resetForm()
  const sid = selectedChapterId.value || firstStructuredChapterId(chapterTreeNodes.value) || findUncategorizedId(chapterTreeNodes.value)
  form.chapter_ids = sid ? [sid] : []
  dialogVisible.value = true
}

const openEditDialog = async row => {
  editingMaterial.value = row
  const full = await api.materials.get(row.id)
  resetForm()
  form.title = full.title
  form.content = full.content || ''
  form.content_format = normalizeContentFormat(full.content_format)
  form.attachment_name = full.attachment_name || ''
  form.attachment_url = full.attachment_url || ''
  form.chapter_ids =
    (full.chapter_ids && full.chapter_ids.length
      ? full.chapter_ids
      : full.placements?.map(p => p.chapter_id)) || []
  dialogVisible.value = true
}

const handleAttachmentChange = uploadFile => {
  const file = uploadFile.raw
  const result = validateAttachmentFile(file)
  if (!result.valid) {
    ElMessage.error(result.message)
    return false
  }
  attachmentFile.value = file
  form.attachment_name = file.name
  form.attachment_url = ''
  form.remove_attachment = false
  return false
}

const removeAttachment = () => {
  attachmentFile.value = null
  form.attachment_name = ''
  form.attachment_url = ''
  form.remove_attachment = true
}

const uploadAttachmentIfNeeded = async () => {
  if (!attachmentFile.value) {
    return {
      attachment_name: form.attachment_name || null,
      attachment_url: form.attachment_url || null,
      remove_attachment: form.remove_attachment
    }
  }
  const uploaded = await api.files.upload(attachmentFile.value)
  form.attachment_name = uploaded.attachment_name
  form.attachment_url = uploaded.attachment_url
  form.remove_attachment = false
  attachmentFile.value = null
  return {
    attachment_name: uploaded.attachment_name,
    attachment_url: uploaded.attachment_url,
    remove_attachment: false
  }
}

const submitForm = async () => {
  await formRef.value.validate()
  submitting.value = true
  try {
    const attachment = await uploadAttachmentIfNeeded()
    const base = {
      title: form.title,
      content: form.content,
      content_format: normalizeContentFormat(form.content_format),
      chapter_ids: form.chapter_ids
    }
    if (editingMaterial.value) {
      await api.materials.update(editingMaterial.value.id, {
        ...base,
        attachment_name: attachment.attachment_name,
        attachment_url: attachment.attachment_url,
        remove_attachment: attachment.remove_attachment
      })
      ElMessage.success('资料已更新')
    } else {
      await api.materials.create({
        ...base,
        attachment_name: attachment.attachment_name,
        attachment_url: attachment.attachment_url,
        class_id: selectedCourse.value.class_id,
        subject_id: selectedCourse.value.id
      })
      ElMessage.success('资料已发布')
    }
    dialogVisible.value = false
    await loadChapterTree()
    await loadMaterials()
  } finally {
    submitting.value = false
  }
}

const viewMaterial = async row => {
  currentMaterial.value = await api.materials.get(row.id)
  detailVisible.value = true
}

const openMaterialRead = row => {
  router.push({ name: 'MaterialRead', params: { id: row.id } })
}

const openMaterialReadFromDetail = () => {
  if (!currentMaterial.value) return
  detailVisible.value = false
  openMaterialRead(currentMaterial.value)
}

const openFirstMaterialReadInChapter = async () => {
  if (!selectedCourse.value) return
  if (!materials.value.length) {
    ElMessage.info('当前章节暂无资料')
    return
  }
  openMaterialRead(materials.value[0])
}

const onChapterLabelDblClick = async data => {
  if (!selectedCourse.value) return
  try {
    const res = await api.materials.list({
      class_id: selectedCourse.value.class_id,
      subject_id: selectedCourse.value.id,
      chapter_id: data.id,
      page: 1,
      page_size: 20
    })
    const rows = res?.data || []
    if (!rows.length) {
      ElMessage.info('该章节下暂无资料')
      return
    }
    openMaterialRead(rows[0])
  } catch (e) {
    console.error(e)
    ElMessage.error('无法加载章节资料')
  }
}

const openChapterRead = data => {
  selectedChapterId.value = data.id
  onChapterLabelDblClick(data)
}

const openAttachment = async row => {
  if (!row?.attachment_url) return
  await downloadAttachment(row.attachment_url, row.attachment_name)
}

const downloadFormAttachment = async () => {
  await downloadAttachment(form.attachment_url, attachmentDisplayName.value)
}

const canDeleteMaterial = row => userStore.isAdmin || row.created_by === userStore.userInfo?.id

const canEditMaterial = row => userStore.isAdmin || row.created_by === userStore.userInfo?.id

const deleteMaterial = async row => {
  try {
    await ElMessageBox.confirm(`确认删除资料“${row.title}”吗？`, '删除资料', { type: 'warning' })
    await api.materials.delete(row.id)
    ElMessage.success('资料已删除')
    await loadChapterTree()
    await loadMaterials()
  } catch (error) {
    if (error !== 'cancel') console.error('删除资料失败', error)
  }
}

const formatDate = value => {
  if (!value) return '未设置'
  return new Date(value).toLocaleString('zh-CN')
}

const openAddChapterDialog = parentId => {
  chapterParentId.value = parentId
  newChapterTitle.value = ''
  chapterDialogVisible.value = true
}

const openRenameChapterDialog = data => {
  renameChapterId.value = data.id
  renameChapterTitle.value = data.title
  renameChapterVisible.value = true
}

const submitRenameChapter = async () => {
  const t = renameChapterTitle.value.trim()
  if (!t) {
    ElMessage.warning('请输入章节名称')
    return
  }
  renameChapterSubmitting.value = true
  try {
    await api.materialChapters.update(renameChapterId.value, { title: t })
    ElMessage.success('已更新')
    renameChapterVisible.value = false
    await loadChapterTree()
    persistExpandedChapterKeys()
  } finally {
    renameChapterSubmitting.value = false
  }
}

const submitNewChapter = async () => {
  const t = newChapterTitle.value.trim()
  if (!t) {
    ElMessage.warning('请输入章节名称')
    return
  }
  chapterSubmitting.value = true
  try {
    await api.materialChapters.create(selectedCourse.value.id, {
      title: t,
      parent_id: chapterParentId.value
    })
    ElMessage.success('章节已添加')
    chapterDialogVisible.value = false
    await loadChapterTree()
    if (chapterParentId.value) {
      expandedChapterKeys.value = Array.from(new Set([...expandedChapterKeys.value, chapterParentId.value]))
      syncTreeExpandedState()
      persistExpandedChapterKeys()
    }
  } finally {
    chapterSubmitting.value = false
  }
}

const confirmDeleteChapter = async data => {
  try {
    await ElMessageBox.confirm(`删除章节「${data.title}」？资料将移至「未分类」。`, '删除章节', { type: 'warning' })
    const deletedId = data.id
    await api.materialChapters.delete(deletedId, selectedCourse.value.id)
    ElMessage.success('已删除')
    await loadChapterTree()
    if (selectedChapterId.value === deletedId) {
      selectedChapterId.value = findUncategorizedId(chapterTreeNodes.value)
    }
    expandedChapterKeys.value = expandedChapterKeys.value.filter(id => String(id) !== String(deletedId))
    persistExpandedChapterKeys()
    await loadMaterials()
  } catch (e) {
    if (e !== 'cancel') console.error(e)
  }
}

const placementExtraOptions = computed(() => {
  const row = placementTarget.value
  const existing = new Set((row?.placements || []).map(p => p.chapter_id))
  return flatChapterOptions.value.filter(o => !existing.has(o.id))
})

const openPlacementDialog = row => {
  placementTarget.value = row
  extraChapterId.value = null
  placementDialogVisible.value = true
}

const submitExtraPlacement = async () => {
  if (!extraChapterId.value || !placementTarget.value) return
  placementSubmitting.value = true
  try {
    await api.materialChapters.addPlacement(placementTarget.value.id, selectedCourse.value.id, {
      chapter_id: extraChapterId.value
    })
    ElMessage.success('已添加引用')
    placementDialogVisible.value = false
    await loadMaterials()
  } finally {
    placementSubmitting.value = false
  }
}

const loadHomeworkPickerRows = async () => {
  if (!homeworkLinkDialogVisible.value || !selectedCourse.value) return
  homeworkPickerLoading.value = true
  try {
    const result = await api.discussions.searchTargets({
      target_type: 'homework',
      q: homeworkSearchText.value || undefined,
      preferred_subject_id: selectedCourse.value.id,
      limit: 30
    })
    homeworkPickerRows.value = (result?.data || []).filter(
      item => String(item.subject_id || '') === String(selectedCourse.value.id)
    )
  } finally {
    homeworkPickerLoading.value = false
  }
}

const scheduleHomeworkPickerLoad = () => {
  if (homeworkPickerDebounceTimer) {
    window.clearTimeout(homeworkPickerDebounceTimer)
  }
  homeworkPickerDebounceTimer = window.setTimeout(loadHomeworkPickerRows, 180)
}

const openHomeworkLinkDialog = () => {
  homeworkSearchText.value = ''
  homeworkPickerRows.value = []
  homeworkLinkDialogVisible.value = true
  loadHomeworkPickerRows()
}

const addHomeworkLink = async item => {
  if (!selectedCourse.value || !selectedChapterId.value || !item?.target_id) return
  await api.materialChapters.addHomeworkLink(selectedCourse.value.id, {
    chapter_id: selectedChapterId.value,
    homework_id: item.target_id
  })
  ElMessage.success('作业链接已添加')
  await loadChapterTree()
  await loadHomeworkPickerRows()
}

const removeHomeworkLink = async link => {
  if (!selectedCourse.value || !link?.link_id) return
  await api.materialChapters.removeHomeworkLink(link.link_id, selectedCourse.value.id)
  ElMessage.success('作业链接已移除')
  await loadChapterTree()
}

const openHomeworkLink = async link => {
  await openDiscussionLinkedTarget(
    {
      target_type: 'homework',
      target_id: link.homework_id,
      subject_id: link.subject_id,
      class_id: link.class_id,
      available: true
    },
    router,
    userStore
  )
}

onMounted(async () => {
  if (typeof window !== 'undefined') {
    window.addEventListener(MATERIAL_PRESENTATION_EVENT, handleMaterialPresentationStyleChange)
  }
  await userStore.ensureSelectedCourse(true, { preserveEmptySelection: true })
  await loadChapterTree()
  await loadMaterials()
})

watch(selectedCourse, async () => {
  selectedChapterId.value = null
  expandedChapterKeys.value = []
  isMaterialShelfCollapsed.value = false
  await loadChapterTree()
  selectedChapterId.value = firstStructuredChapterId(chapterTreeNodes.value) || findUncategorizedId(chapterTreeNodes.value)
  await loadMaterials()
})

watch(selectedChapterId, () => {
  if (treeLoading.value) {
    return
  }
  ensureSelectedChapterPathExpanded()
  syncTreeExpandedState()
  persistExpandedChapterKeys()
  loadMaterials()
})

watch(homeworkSearchText, () => {
  scheduleHomeworkPickerLoad()
})

const handleMaterialPresentationStyleChange = event => {
  materialPresentationStyle.value = event?.detail || getMaterialPresentationStyle()
}

onBeforeUnmount(() => {
  if (homeworkPickerDebounceTimer) {
    window.clearTimeout(homeworkPickerDebounceTimer)
  }
  if (typeof window !== 'undefined') {
    window.removeEventListener(MATERIAL_PRESENTATION_EVENT, handleMaterialPresentationStyleChange)
  }
})
</script>

<style scoped>
.materials-page {
  padding: 24px;
  min-width: 0;
  color: var(--wa-color-text);
}

.materials-page--reader .chapter-sidebar,
.materials-page--reader .materials-shelf-card {
  border-radius: var(--wa-radius-xl);
  box-shadow: var(--wa-shadow-surface);
}

.materials-page--reader .tree-node-label {
  font-family: "Noto Serif SC", "Source Han Serif SC", "Songti SC", serif;
  font-size: 16px;
}

.materials-page--compact .materials-layout {
  gap: 14px;
}

.materials-page--compact .chapter-sidebar {
  padding: 12px 14px 10px;
}

.materials-page--compact .chapter-tree :deep(.el-tree-node__content) {
  min-height: 38px;
}

.materials-page--compact .tree-node-label {
  min-height: 34px;
  font-size: 14px;
  font-family: inherit;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 24px;
  padding: 0 4px;
}

.page-title {
  margin: 0 0 8px;
  font-size: 28px;
  color: var(--wa-color-text);
}

.page-subtitle {
  margin: 0;
  color: var(--wa-color-text-muted);
}

.header-actions {
  display: flex;
  gap: 12px;
}

.materials-course-cover {
  width: min(100%, 1180px);
  height: clamp(132px, 18vw, 220px);
  margin: 0 auto 18px;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--wa-border-subtle) 76%, transparent);
  border-radius: var(--wa-radius-xl);
  background: var(--wa-color-surface);
  box-shadow: var(--wa-shadow-object);
}

.materials-course-cover__image {
  display: block;
  width: 100%;
  height: 100%;
}

.materials-layout {
  display: flex;
  flex-direction: column;
  gap: 18px;
  align-items: stretch;
}

.materials-layout--outline-collapsed {
  gap: 12px;
}

.chapter-sidebar {
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
  padding: 16px 18px 12px;
  border: 1px solid transparent;
  box-shadow: var(--wa-shadow-object);
  width: 100%;
  max-width: none;
}

.chapter-sidebar--narrow {
  grid-template-columns: 1fr;
}

.chapter-sidebar__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  padding-bottom: 12px;
  border-bottom: 1px solid color-mix(in srgb, var(--wa-border-subtle) 78%, transparent);
}

.chapter-sidebar__heading {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.chapter-sidebar__eyebrow {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0;
  color: var(--wa-color-primary-600);
  text-transform: uppercase;
}

.chapter-sidebar__title {
  font-size: 20px;
  font-weight: 700;
  color: var(--wa-color-text);
}

.chapter-sidebar__meta {
  font-size: 12px;
  color: var(--wa-color-text-muted);
}

.chapter-sidebar__actions {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  min-width: 0;
  padding: 3px;
  border: 1px solid color-mix(in srgb, var(--wa-border-subtle) 70%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--wa-color-surface) 82%, var(--wa-color-primary-50));
}

.chapter-outline-btn {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  color: var(--wa-color-primary-600);
}

.chapter-outline-btn:hover {
  background: color-mix(in srgb, var(--wa-color-primary-50) 82%, #fff);
}

.chapter-sidebar__actions :deep(.el-button--primary.is-plain) {
  margin-left: 4px;
  border-radius: 999px;
  font-weight: 700;
  box-shadow: 0 4px 12px color-mix(in srgb, var(--wa-color-primary-600) 10%, transparent);
}

.chapter-tree :deep(.el-tree-node__content) {
  height: auto;
  min-height: 40px;
  align-items: flex-start;
  padding: 2px 0;
  font-size: 15px;
  border-radius: 12px;
  transition: background 0.16s ease;
}

.chapter-tree :deep(.el-tree-node__content:hover) {
  background: color-mix(in srgb, var(--wa-color-primary-50) 72%, transparent);
}

.chapter-tree :deep(.el-tree-node.is-current > .el-tree-node__content) {
  background: color-mix(in srgb, var(--wa-color-primary-50) 86%, #fff);
  box-shadow: inset 3px 0 0 var(--wa-color-primary-600);
}

.chapter-tree :deep(.el-tree-node__children) {
  border-left: 1px solid color-mix(in srgb, var(--wa-border-subtle) 72%, transparent);
  margin-left: 12px;
}

.chapter-tree :deep(.el-tree-node__expand-icon) {
  display: none;
}

.chapter-node-toggle,
.chapter-node-toggle-spacer {
  width: 24px;
  height: 24px;
  flex: 0 0 24px;
  margin: 4px 4px 4px 0;
}

.chapter-node-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid color-mix(in srgb, var(--wa-color-primary-500) 24%, transparent);
  border-radius: 7px;
  background: color-mix(in srgb, var(--wa-color-primary-50) 84%, #fff);
  color: var(--wa-color-primary-600);
  cursor: pointer;
  box-shadow: 0 1px 2px color-mix(in srgb, var(--wa-color-text) 8%, transparent);
  transition:
    background 0.16s ease,
    border-color 0.16s ease,
    box-shadow 0.16s ease,
    transform 0.16s ease;
}

.chapter-node-toggle:hover {
  background: color-mix(in srgb, var(--wa-color-primary-100) 82%, #fff);
  border-color: color-mix(in srgb, var(--wa-color-primary-500) 38%, transparent);
  box-shadow: 0 4px 10px color-mix(in srgb, var(--wa-color-primary-600) 16%, transparent);
  transform: scale(1.08);
}

.chapter-node-toggle:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--wa-color-primary-500) 36%, transparent);
  outline-offset: 2px;
}

.tree-node-label {
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  flex-wrap: wrap;
  flex: 1 1 auto;
  min-width: 0;
  min-height: 36px;
  max-width: 100%;
  padding: 5px 8px 5px 0;
  border: none;
  background: transparent;
  color: var(--wa-color-text);
  text-align: left;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.55;
  cursor: pointer;
  font-family: "Noto Serif SC", "Source Han Serif SC", "Songti SC", "STSong", serif;
}

.tree-node-label__title {
  display: inline-block;
  max-width: 100%;
  overflow-wrap: anywhere;
}

.tree-node-label:hover .tree-node-label__title {
  color: var(--wa-color-primary-700);
}

.tree-node-label--uncategorized {
  font-family: inherit;
  font-weight: 500;
  color: var(--wa-color-text-soft);
}

.tree-tag {
  transform: scale(0.9);
}

.tree-node-actions {
  margin-left: auto;
  display: inline-flex;
  flex-wrap: wrap;
  flex-shrink: 0;
  gap: 2px;
  justify-content: flex-end;
  max-width: 100%;
  padding-top: 4px;
}

.materials-toolbar {
  margin-bottom: 10px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 12px;
  border: 1px solid color-mix(in srgb, var(--wa-border-subtle) 76%, transparent);
  border-radius: var(--wa-radius-lg);
  background: color-mix(in srgb, var(--wa-color-surface) 88%, var(--wa-color-bg-soft));
  box-shadow: 0 4px 14px color-mix(in srgb, var(--wa-color-text) 4%, transparent);
}

.materials-toolbar__summary {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--wa-color-text);
}

.materials-toolbar__text {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
}

.materials-toolbar__outline-toggle {
  margin-right: 2px;
}

.materials-toolbar__eyebrow {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0;
  color: var(--wa-color-primary-600);
  text-transform: uppercase;
}

.materials-toolbar__count {
  color: var(--wa-color-text-muted);
  font-size: 13px;
}

.materials-toolbar__actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.materials-shelf-card {
  border-radius: var(--wa-radius-lg);
  border: 1px solid color-mix(in srgb, var(--wa-border-subtle) 86%, transparent);
  box-shadow: var(--wa-shadow-surface);
}

.chapter-homework-panel {
  margin-bottom: 12px;
  padding: 14px 16px;
  border: 1px solid color-mix(in srgb, var(--wa-border-subtle) 82%, transparent);
  border-radius: var(--wa-radius-lg);
  background: color-mix(in srgb, var(--wa-color-surface) 92%, var(--wa-color-bg-soft));
  box-shadow: 0 4px 14px color-mix(in srgb, var(--wa-color-text) 4%, transparent);
}

.chapter-homework-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.chapter-homework-panel__head > div {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.chapter-homework-list {
  display: grid;
  gap: 8px;
}

.chapter-homework-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid color-mix(in srgb, var(--wa-border-subtle) 78%, transparent);
  border-radius: var(--wa-radius-md);
  background: var(--wa-color-surface);
  cursor: pointer;
  transition:
    border-color 0.16s ease,
    box-shadow 0.16s ease,
    transform 0.16s ease;
}

.chapter-homework-card:hover {
  border-color: color-mix(in srgb, var(--wa-color-primary-500) 36%, transparent);
  box-shadow: 0 8px 18px color-mix(in srgb, var(--wa-color-primary-600) 10%, transparent);
  transform: translateY(-1px);
}

.chapter-homework-card__main {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.chapter-homework-card__main strong {
  color: var(--wa-color-text);
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.chapter-homework-card__type {
  color: var(--wa-color-primary-600);
  font-size: 12px;
  font-weight: 700;
}

.chapter-homework-card__meta {
  color: var(--wa-color-text-muted);
  font-size: 12px;
  line-height: 1.4;
}

.chapter-homework-card__actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
}

.homework-link-picker {
  display: grid;
  gap: 12px;
}

.homework-link-picker__results {
  min-height: 180px;
  max-height: min(52vh, 430px);
  overflow: auto;
  padding-right: 4px;
}

.homework-link-picker__row {
  display: flex;
  gap: 14px;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.homework-link-picker__row:last-child {
  border-bottom: none;
}

.homework-link-picker__meta {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.homework-link-picker__meta strong {
  color: var(--wa-color-text);
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.homework-link-picker__meta span {
  color: var(--wa-color-text-muted);
  font-size: 12px;
}

.materials-shelf-card__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 12px;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid color-mix(in srgb, var(--wa-border-subtle) 78%, transparent);
}

.materials-shelf-card__head > div {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.materials-shelf-card__head strong {
  font-size: 17px;
  color: var(--wa-color-text);
}

.materials-shelf-card__head > span {
  flex: 0 0 auto;
  color: var(--wa-color-text-muted);
  font-size: 13px;
}

.materials-table-scroll {
  overflow-x: auto;
  max-width: 100%;
}

.materials-table-scroll :deep(.el-table) {
  min-width: 1160px;
}

.wa-table-actions {
  display: inline-flex;
  flex-wrap: wrap;
  justify-content: center;
  align-items: center;
  gap: 4px;
  width: 100%;
}

.materials-table-scroll :deep(.el-table__fixed-right) {
  box-shadow: -10px 0 18px rgba(15, 23, 42, 0.06);
}

.materials-main :deep(.el-table__row) {
  cursor: pointer;
}

.muted-text {
  color: var(--wa-color-text-muted);
  font-size: 13px;
}

.attachment-help {
  margin-top: 8px;
}

.attachment-preview {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
  flex-wrap: wrap;
}

@media (max-width: 960px) {
  .materials-page {
    padding: 16px;
  }

  .chapter-sidebar__head {
    align-items: flex-start;
    flex-direction: column;
  }

  .chapter-sidebar__actions {
    flex-wrap: wrap;
    justify-content: flex-start;
  }

  .chapter-homework-panel__head,
  .chapter-homework-card,
  .homework-link-picker__row {
    align-items: stretch;
    flex-direction: column;
  }

  .chapter-homework-card__actions,
  .chapter-homework-panel__head :deep(.el-button),
  .homework-link-picker__row :deep(.el-button) {
    width: 100%;
  }

  .chapter-homework-card__actions {
    justify-content: stretch;
  }
}

@media (max-width: 640px) {
  .chapter-tree :deep(.el-tree-node__content) {
    flex-wrap: wrap;
    align-items: flex-start;
  }

  .tree-node-label {
    flex: 1 1 calc(100% - 32px);
    padding-right: 0;
  }

  .tree-node-actions {
    flex: 1 1 calc(100% - 32px);
    margin-left: 32px;
    padding: 0 0 6px;
    justify-content: flex-start;
    gap: 8px;
  }

  .tree-node-actions :deep(.el-button + .el-button) {
    margin-left: 0;
  }
}
</style>
