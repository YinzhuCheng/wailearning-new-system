<template>
  <div class="homework-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">作业管理</h1>
        <p class="page-subtitle">
          {{ selectedCourse ? `${selectedCourse.name} · ${selectedCourse.class_name || '未分配班级'}` : '请先选择课程后查看作业。' }}
        </p>
      </div>
      <div class="header-actions">
        <el-button
          v-if="!userStore.isStudent && selectedCourse && homeworks.length"
          @click="openBatchLateDialog"
        >
          批量迟交策略
        </el-button>
        <el-button
          v-if="!userStore.isStudent && selectedCourse"
          type="primary"
          data-testid="homework-btn-create"
          @click="openCreateDialog"
        >
          发布作业
        </el-button>
      </div>
    </div>

    <el-empty v-if="!selectedCourse" description="请先选择一门课程。" />

    <template v-else>
      <el-card shadow="never" class="homework-list-card">
        <DualHorizontalScroll target-selector=".homework-table-scroll">
          <div class="homework-table-scroll dual-scroll-target">
            <el-table
              ref="homeworkTableRef"
              :data="homeworks"
              :class="userStore.isStudent ? 'homework-table--student' : 'homework-table--teacher'"
              v-loading="loading"
              row-key="id"
              @selection-change="onHomeworkSelectionChange"
            >
          <template #empty>
            <div class="homework-empty-state">
              <div class="homework-empty-state__title">
                {{ userStore.isStudent ? '暂无课程作业' : '当前课程还没有作业' }}
              </div>
              <p>
                {{ userStore.isStudent ? '老师发布作业后会显示在这里。' : '发布第一份作业后，学生提交、评分任务和批量策略会在这里汇总。' }}
              </p>
              <el-button
                v-if="!userStore.isStudent"
                type="primary"
                data-testid="homework-empty-create"
                @click="openCreateDialog"
              >
                发布作业
              </el-button>
            </div>
          </template>
          <el-table-column
            v-if="!userStore.isStudent"
            type="selection"
            width="48"
            :reserve-selection="true"
          />
          <el-table-column prop="title" label="作业标题" :width="userStore.isStudent ? 156 : 160" align="center" header-align="center" show-overflow-tooltip />
          <el-table-column v-if="!userStore.isStudent" label="提交上限" width="84" align="center" header-align="center">
            <template #default="{ row }">
              {{ row.max_submissions != null ? `${row.max_submissions} 次` : '不限' }}
            </template>
          </el-table-column>
          <el-table-column prop="subject_name" label="课程" :width="userStore.isStudent ? 128 : 128" align="center" header-align="center" />
          <el-table-column :width="userStore.isStudent ? 96 : 96" label="评分" align="center" header-align="center">
            <template #default="{ row }">
              <div class="rule-cell">
                <el-tag size="small" :type="row.auto_grading_enabled ? 'success' : 'info'">
                  {{ gradingModeLabel(row.auto_grading_enabled) }}
                </el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="附件" width="90" align="center" header-align="center">
            <template #default="{ row }">
              <el-button
                v-if="row.attachment_url"
                type="primary"
                link
                @click.stop="openAttachment(row)"
              >
                下载附件
              </el-button>
              <span v-else class="muted-text">无</span>
            </template>
          </el-table-column>
          <el-table-column prop="due_date" label="截止时间" :width="userStore.isStudent ? 144 : 146" align="center" header-align="center">
            <template #default="{ row }">
              {{ formatDate(row.due_date) }}
            </template>
          </el-table-column>
          <el-table-column v-if="userStore.isStudent" label="任务" width="96" align="center" header-align="center">
            <template #default="{ row }">
              <div v-if="resolveTaskStatus(row)" class="task-status-cell task-status-cell--student">
                <el-tag :type="taskTagType(resolveTaskStatus(row))" size="small">
                  {{ formatTaskStatus(resolveTaskStatus(row)) }}
                </el-tag>
                <span v-if="row.latest_submission_is_late" class="late-tip">已标记迟交</span>
              </div>
              <span v-else class="muted-text">{{ row.attempt_count ? '待教师评分' : '未提交' }}</span>
            </template>
          </el-table-column>
          <el-table-column
            label="操作"
            :width="userStore.isStudent ? 104 : 224"
            fixed="right"
            align="center"
            header-align="center"
            class-name="homework-actions-column"
            label-class-name="homework-actions-column__header"
          >
            <template #default="{ row }">
              <template v-if="userStore.isStudent">
                <div class="student-homework-actions">
                  <el-button size="small" type="primary" data-testid="homework-student-submit" @click="goToSubmitPage(row)">
                    {{ row.attempt_count ? '提交' : '去交' }}
                  </el-button>
                  <el-button size="small" link data-testid="homework-student-detail" @click="viewHomework(row)">说明</el-button>
                </div>
              </template>
              <template v-else>
                <div class="wa-table-actions wa-table-actions--teacher">
                  <el-button size="small" type="primary" @click="viewHomework(row)">查看</el-button>
                  <el-button size="small" @click="goToSubmissionStatus(row)">提交</el-button>
                  <el-button size="small" plain data-testid="homework-btn-edit" @click="openEditDialog(row)">
                    编辑
                  </el-button>
                  <el-button size="small" type="danger" @click="deleteHomework(row)">删除</el-button>
                </div>
              </template>
            </template>
          </el-table-column>
          <el-table-column v-if="userStore.isStudent" label="分数" width="100" align="center" header-align="center">
            <template #default="{ row }">
              <div v-if="hasHomeworkReview(row)" class="student-review-summary">
                <div class="student-review-summary__chips">
                  <el-tag
                    v-if="row.review_score !== null && row.review_score !== undefined"
                    :type="scoreTag(row.review_score)"
                    size="small"
                  >
                    {{ formatScore(row.review_score) }}
                  </el-tag>
                </div>
                <div class="review-meta">{{ reviewMetaText(row.attempt_count) }}</div>
              </div>
              <span v-else class="muted-text">未评分</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!userStore.isStudent" prop="creator_name" label="发布人" width="92" align="center" header-align="center" />
          <el-table-column v-if="!userStore.isStudent" prop="created_at" label="发布时间" width="146" align="center" header-align="center">
            <template #default="{ row }">
              {{ formatDate(row.created_at) }}
            </template>
          </el-table-column>
            </el-table>
          </div>
        </DualHorizontalScroll>
      </el-card>
    </template>

    <el-dialog v-model="batchLateDialogVisible" title="批量设置迟交策略" width="520px" destroy-on-close>
      <p class="batch-late-hint">将应用于下方勾选的作业（当前课程列表）。至少修改一项。</p>
      <el-form label-width="140px">
        <el-form-item label="允许截止后提交">
          <el-switch v-model="batchLateForm.allow_late_submission" />
        </el-form-item>
        <el-form-item label="迟交影响评分">
          <el-switch v-model="batchLateForm.late_submission_affects_score" />
        </el-form-item>
      </el-form>
      <p class="batch-late-tip">若希望补交仅作标记、尽量不纳入展示分，可开启「允许截止后提交」并关闭「迟交影响评分」（具体仍受多次提交取最高规则约束）。</p>
      <template #footer>
        <el-button @click="batchLateDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="batchLateSaving" @click="applyBatchLatePolicy">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="dialogVisible"
      :title="editingHomeworkId ? '编辑作业' : '发布作业'"
      width="900px"
      destroy-on-close
      @closed="onHomeworkDialogClosed"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="作业标题" prop="title">
          <el-input v-model="form.title" data-testid="homework-form-title" />
        </el-form-item>
        <el-form-item label="截止时间" prop="due_date">
          <el-date-picker
            v-model="form.due_date"
            type="datetime"
            placeholder="请选择截止时间"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="作业内容" prop="content">
          <MarkdownEditorPanel
            v-model="form.content"
            v-model:content-format="form.content_format"
            :min-rows="6"
            :max-rows="24"
            placeholder="支持 Markdown、LaTeX、插图（上传或 URL）"
            hint="与独立附件并存；自动评分时说明中的远程/附件图片会尽量转为模型可读格式。"
            :show-format-toggle="true"
          />
        </el-form-item>
        <el-form-item label="满分" prop="max_score">
          <el-input-number v-model="form.max_score" :min="1" :max="1000" :precision="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="分数精度">
          <el-radio-group v-model="form.grade_precision">
            <el-radio label="integer">整数</el-radio>
            <el-radio label="decimal_1">1 位小数</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="自动评分">
          <el-switch v-model="form.auto_grading_enabled" />
          <div class="attachment-help">
            启用后，学生新提交会进入异步评分队列；展示分数始终按最高分规则计算。模型会分段读取作业说明、学生文字与附件（PDF/图片/部分文本与
            ipynb 等）；过大内容可能被截断。日 token 限额、统计时区与预占估算由管理员在系统设置中统一配置。
          </div>
        </el-form-item>
        <el-form-item v-if="form.auto_grading_enabled" label="LLM 路由">
          <el-select
            v-model="form.llm_routing_mode"
            data-testid="homework-llm-routing-mode"
            placeholder="沿用课程设置"
            style="width: 100%"
            @visible-change="v => v && loadLlmPresets()"
          >
            <el-option label="沿用课程设置（课程 LLM 分组/顺序）" value="course_default" />
            <el-option label="仅使用下方勾选的课程端点预设" value="limit_presets" />
            <el-option label="优先使用「最新纯文本连通性测试通过」的全局预设" value="latest_passing" />
          </el-select>
          <div class="attachment-help">
            发布后仍可修改。限制预设时，请先在「课程设置」里把端点加入本课程；否则系统会回退为完整课程路由并给出提示。
          </div>
        </el-form-item>
        <el-form-item
          v-if="form.auto_grading_enabled && form.llm_routing_mode === 'limit_presets'"
          label="端点预设"
        >
          <el-select
            v-model="form.llm_preset_ids"
            data-testid="homework-llm-preset-multi"
            multiple
            filterable
            collapse-tags
            placeholder="选择本作业允许使用的预设"
            style="width: 100%"
            @visible-change="v => v && loadLlmPresets()"
          >
            <el-option
              v-for="p in llmPresets"
              :key="p.id"
              :label="`${p.name} (#${p.id})`"
              :value="p.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="响应语言">
          <el-input v-model="form.response_language" placeholder="例如 zh-CN / en-US，可为空" />
        </el-form-item>
        <el-form-item label="评分要点（学生可见）">
          <MarkdownEditorPanel
            v-model="form.rubric_text"
            :min-rows="4"
            :max-rows="18"
            placeholder="学生端作业页始终可见；可与下方「教师私有」要点配合使用。"
            hint="面向学生的评分导向或公开量规；请勿在此处写入仅教师掌握的细则。"
            :compact-demo="true"
          />
        </el-form-item>
        <el-form-item label="评分要点（仅教师可见）">
          <MarkdownEditorPanel
            v-model="form.rubric_staff_only"
            :min-rows="4"
            :max-rows="18"
            placeholder="内部分项、加减分细则等（学生端与智能助教讨论上下文均不可见）"
            hint="仅供教师端与 LLM 自动评分提示使用；不得要求学生复述本节原文。"
            :compact-demo="true"
          />
        </el-form-item>
        <el-form-item label="参考答案或思路（仅教师可见）">
          <MarkdownEditorPanel
            v-model="form.reference_answer"
            :min-rows="4"
            :max-rows="18"
            placeholder="参考答案、提纲或评分对齐思路（学生端不可见）"
            hint="自动评分与教师批改可参考；智能助教讨论（学生发起）不会附带本节。"
            :compact-demo="true"
          />
        </el-form-item>
        <el-form-item label="迟交规则">
          <div class="late-rules">
            <el-switch v-model="form.allow_late_submission" active-text="允许补交" inactive-text="禁止补交" />
            <el-switch
              v-model="form.late_submission_affects_score"
              active-text="迟交影响评分"
              inactive-text="迟交默认不影响评分"
            />
          </div>
        </el-form-item>
        <el-form-item label="提交次数">
          <div class="late-rules">
            <el-switch v-model="form.max_submissions_enabled" active-text="限制每人最多提交次数" inactive-text="不限制" />
            <el-input-number
              v-if="form.max_submissions_enabled"
              v-model="form.max_submissions_value"
              :min="1"
              :max="200"
              style="width: 160px; margin-left: 8px"
            />
          </div>
          <div class="attachment-help">达到上限后学生无法再提交新 attempt；教师下调上限时不能低于任一学生已提交次数。</div>
        </el-form-item>
        <el-form-item label="附件">
          <el-upload
            :auto-upload="false"
            :show-file-list="false"
            :limit="1"
            :on-change="handleAttachmentChange"
          >
            <el-button>选择附件</el-button>
          </el-upload>
          <div class="attachment-help">{{ attachmentHintText }}</div>
          <div v-if="attachmentDisplayName" class="attachment-preview">
            <span>{{ attachmentDisplayName }}</span>
            <el-button link type="danger" @click="removeAttachment">移除</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" data-testid="homework-form-save" :loading="submitting" @click="submitForm">
          保存
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailVisible" title="作业详情" width="900px" destroy-on-close>
      <el-descriptions v-if="currentHomework" :column="2" border>
        <el-descriptions-item label="作业标题" :span="2">{{ currentHomework.title }}</el-descriptions-item>
        <el-descriptions-item label="课程">{{ currentHomework.subject_name || selectedCourse?.name }}</el-descriptions-item>
        <el-descriptions-item label="截止时间">{{ formatDate(currentHomework.due_date) }}</el-descriptions-item>
        <el-descriptions-item label="发布人">{{ currentHomework.creator_name }}</el-descriptions-item>
        <el-descriptions-item label="发布时间">{{ formatDate(currentHomework.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="满分">{{ formatScore(currentHomework.max_score) }}</el-descriptions-item>
          <el-descriptions-item label="提交上限">
            {{ currentHomework.max_submissions != null ? `${currentHomework.max_submissions} 次/人` : '不限' }}
          </el-descriptions-item>
          <el-descriptions-item label="自动评分">{{ currentHomework.auto_grading_enabled ? '已启用' : '未启用' }}</el-descriptions-item>
          <el-descriptions-item label="评分规则" :span="2">{{ currentHomework.grading_rule_hint }}</el-descriptions-item>
          <el-descriptions-item label="作业内容" :span="2">
            <PlainOrMarkdownBlock
              :text="currentHomework.content"
              :format="currentHomework.content_format"
              variant="student"
              empty-text="暂无内容"
            />
          </el-descriptions-item>
          <el-descriptions-item label="评分要点（学生可见）" :span="2">
            <RichMarkdownDisplay :markdown="currentHomework.rubric_text" variant="teacher" empty-text="未设置" />
          </el-descriptions-item>
          <el-descriptions-item label="评分要点（仅教师可见）" :span="2">
            <RichMarkdownDisplay :markdown="currentHomework.rubric_staff_only" variant="teacher" empty-text="未设置" />
          </el-descriptions-item>
          <el-descriptions-item label="参考答案或思路（仅教师可见）" :span="2">
            <RichMarkdownDisplay :markdown="currentHomework.reference_answer" variant="teacher" empty-text="未设置" />
          </el-descriptions-item>
        <el-descriptions-item label="附件" :span="2">
          <el-button v-if="currentHomework.attachment_url" type="primary" link @click="openAttachment(currentHomework)">
            {{ currentHomework.attachment_name || '下载附件' }}
          </el-button>
          <span v-else class="muted-text">无附件</span>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button type="primary" @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import api from '@/api'
import DualHorizontalScroll from '@/components/DualHorizontalScroll.vue'
import MarkdownEditorPanel from '@/components/MarkdownEditorPanel.vue'
import PlainOrMarkdownBlock from '@/components/PlainOrMarkdownBlock.vue'
import RichMarkdownDisplay from '@/components/RichMarkdownDisplay.vue'
import { useUserStore } from '@/stores/user'
import { attachmentHintText, downloadAttachment, validateAttachmentFile } from '@/utils/attachments'
import { normalizeContentFormat } from '@/utils/contentFormat'

const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)
const editingHomeworkId = ref(null)
const detailVisible = ref(false)
const currentHomework = ref(null)
const homeworks = ref([])
const homeworkTableRef = ref(null)
const selectedHomeworkRows = ref([])
const batchLateDialogVisible = ref(false)
const batchLateSaving = ref(false)
const batchLateForm = reactive({
  allow_late_submission: true,
  late_submission_affects_score: false
})
const formRef = ref(null)
const attachmentFile = ref(null)
const llmPresets = ref([])

const selectedCourse = computed(() => userStore.selectedCourse)
const attachmentDisplayName = computed(() => attachmentFile.value?.name || form.attachment_name || '')

const form = reactive({
  title: '',
  content: '',
  content_format: 'markdown',
  due_date: null,
  attachment_name: '',
  attachment_url: '',
  max_score: 100,
  grade_precision: 'integer',
  auto_grading_enabled: false,
  rubric_text: '',
  rubric_staff_only: '',
  reference_answer: '',
  response_language: '',
  allow_late_submission: true,
  late_submission_affects_score: false,
  max_submissions_enabled: false,
  max_submissions_value: 3,
  llm_routing_mode: 'course_default',
  llm_preset_ids: []
})

const rules = {
  title: [{ required: true, message: '请输入作业标题', trigger: 'blur' }],
  max_score: [{ required: true, message: '请输入满分', trigger: 'change' }]
}

const buildParams = () => {
  if (!selectedCourse.value) {
    return {}
  }
  return {
    class_id: selectedCourse.value.class_id,
    subject_id: selectedCourse.value.id,
    page: 1,
    page_size: 100
  }
}

const gradingModeLabel = enabled => (enabled ? '自动评分' : '教师评分')

const reviewMetaText = attemptCount => `共 ${attemptCount || 0} 次提交`

const onHomeworkSelectionChange = rows => {
  selectedHomeworkRows.value = rows || []
}

const loadHomeworks = async () => {
  if (!selectedCourse.value) {
    homeworks.value = []
    selectedHomeworkRows.value = []
    return
  }
  loading.value = true
  try {
    const result = await api.homework.list(buildParams())
    homeworks.value = result?.data || []
    selectedHomeworkRows.value = []
    await nextTick()
    homeworkTableRef.value?.clearSelection?.()
  } finally {
    loading.value = false
  }
}

const openBatchLateDialog = () => {
  if (!selectedHomeworkRows.value.length) {
    ElMessage.warning('请先在表格中勾选要批量设置的作业')
    return
  }
  const first = selectedHomeworkRows.value[0]
  batchLateForm.allow_late_submission = Boolean(first.allow_late_submission)
  batchLateForm.late_submission_affects_score = Boolean(first.late_submission_affects_score)
  batchLateDialogVisible.value = true
}

const applyBatchLatePolicy = async () => {
  if (!selectedHomeworkRows.value.length) {
    return
  }
  batchLateSaving.value = true
  try {
    const res = await api.homework.batchLateSubmission({
      homework_ids: selectedHomeworkRows.value.map(r => r.id),
      allow_late_submission: batchLateForm.allow_late_submission,
      late_submission_affects_score: batchLateForm.late_submission_affects_score
    })
    const skipped = (res.forbidden_ids?.length || 0) + (res.missing_ids?.length || 0)
    ElMessage.success(`已更新 ${res.updated} 份作业${skipped ? `，未处理 ${skipped} 条` : ''}`)
    batchLateDialogVisible.value = false
    await loadHomeworks()
  } catch {
    /* 全局拦截器已提示 */
  } finally {
    batchLateSaving.value = false
  }
}

const loadLlmPresets = async () => {
  if (!selectedCourse.value) {
    return
  }
  try {
    const rows = await api.llmSettings.listPresets()
    llmPresets.value = Array.isArray(rows) ? rows.filter(p => p && p.is_active !== false) : []
  } catch {
    llmPresets.value = []
  }
}

const parseRoutingFromHomework = row => {
  const spec = row?.llm_routing_spec
  if (!spec || typeof spec !== 'object') {
    form.llm_routing_mode = 'course_default'
    form.llm_preset_ids = []
    return
  }
  if (spec.mode === 'latest_passing_validated') {
    form.llm_routing_mode = 'latest_passing'
    form.llm_preset_ids = []
    return
  }
  if (spec.mode === 'limit_to_preset_ids' && Array.isArray(spec.preset_ids)) {
    form.llm_routing_mode = 'limit_presets'
    form.llm_preset_ids = spec.preset_ids.map(x => Number(x)).filter(n => Number.isFinite(n))
    return
  }
  form.llm_routing_mode = 'course_default'
  form.llm_preset_ids = []
}

const buildLlmRoutingSpec = () => {
  if (!form.auto_grading_enabled) {
    return null
  }
  if (form.llm_routing_mode === 'latest_passing') {
    return { mode: 'latest_passing_validated' }
  }
  if (form.llm_routing_mode === 'limit_presets') {
    const ids = (form.llm_preset_ids || []).map(x => Number(x)).filter(n => Number.isFinite(n))
    if (!ids.length) {
      return null
    }
    return { mode: 'limit_to_preset_ids', preset_ids: ids }
  }
  return null
}

const resetHomeworkForm = () => {
  editingHomeworkId.value = null
  form.title = ''
  form.content = ''
  form.content_format = 'markdown'
  form.due_date = null
  form.attachment_name = ''
  form.attachment_url = ''
  form.max_score = 100
  form.grade_precision = 'integer'
  form.auto_grading_enabled = false
  form.rubric_text = ''
  form.rubric_staff_only = ''
  form.reference_answer = ''
  form.response_language = ''
  form.allow_late_submission = true
  form.late_submission_affects_score = false
  form.max_submissions_enabled = false
  form.max_submissions_value = 3
  form.llm_routing_mode = 'course_default'
  form.llm_preset_ids = []
  attachmentFile.value = null
}

const openCreateDialog = () => {
  resetHomeworkForm()
  void loadLlmPresets()
  dialogVisible.value = true
}

const openEditDialog = row => {
  if (!row?.id) {
    return
  }
  editingHomeworkId.value = row.id
  form.title = row.title || ''
  form.content = row.content || ''
  form.content_format = normalizeContentFormat(row.content_format)
  form.due_date = row.due_date || null
  form.attachment_name = row.attachment_name || ''
  form.attachment_url = row.attachment_url || ''
  form.max_score = row.max_score ?? 100
  form.grade_precision = row.grade_precision || 'integer'
  form.auto_grading_enabled = Boolean(row.auto_grading_enabled)
  form.rubric_text = row.rubric_text || ''
  form.rubric_staff_only = row.rubric_staff_only || ''
  form.reference_answer = row.reference_answer || ''
  form.response_language = row.response_language || ''
  form.allow_late_submission = row.allow_late_submission !== false
  form.late_submission_affects_score = Boolean(row.late_submission_affects_score)
  if (row.max_submissions != null && row.max_submissions !== '') {
    form.max_submissions_enabled = true
    form.max_submissions_value = Number(row.max_submissions) || 3
  } else {
    form.max_submissions_enabled = false
    form.max_submissions_value = 3
  }
  attachmentFile.value = null
  parseRoutingFromHomework(row)
  void loadLlmPresets()
  dialogVisible.value = true
}

const onHomeworkDialogClosed = () => {
  resetHomeworkForm()
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
  return false
}

const removeAttachment = () => {
  attachmentFile.value = null
  form.attachment_name = ''
  form.attachment_url = ''
}

const uploadAttachmentIfNeeded = async () => {
  if (!attachmentFile.value) {
    return {
      attachment_name: form.attachment_name || null,
      attachment_url: form.attachment_url || null
    }
  }

  const uploaded = await api.files.upload(attachmentFile.value)
  form.attachment_name = uploaded.attachment_name
  form.attachment_url = uploaded.attachment_url
  attachmentFile.value = null

  return {
    attachment_name: uploaded.attachment_name,
    attachment_url: uploaded.attachment_url
  }
}

const submitForm = async () => {
  await formRef.value.validate()
  submitting.value = true
  try {
    const attachment = await uploadAttachmentIfNeeded()
    const maxSubmissions = form.max_submissions_enabled ? Number(form.max_submissions_value) : null
    const payload = {
      title: form.title,
      content: form.content,
      content_format: normalizeContentFormat(form.content_format),
      attachment_name: attachment.attachment_name,
      attachment_url: attachment.attachment_url,
      due_date: form.due_date,
      max_score: form.max_score,
      grade_precision: form.grade_precision,
      auto_grading_enabled: form.auto_grading_enabled,
      rubric_text: form.rubric_text?.trim() || null,
      rubric_staff_only: form.rubric_staff_only?.trim() || null,
      reference_answer: form.reference_answer?.trim() || null,
      response_language: form.response_language?.trim() || null,
      allow_late_submission: form.allow_late_submission,
      late_submission_affects_score: form.late_submission_affects_score,
      max_submissions: maxSubmissions,
      llm_routing_spec: buildLlmRoutingSpec()
    }
    if (editingHomeworkId.value) {
      await api.homework.update(editingHomeworkId.value, payload)
      ElMessage.success('作业已更新')
    } else {
      await api.homework.create({
        ...payload,
        class_id: selectedCourse.value.class_id,
        subject_id: selectedCourse.value.id
      })
      ElMessage.success('作业已发布')
    }
    dialogVisible.value = false
    await loadHomeworks()
  } finally {
    submitting.value = false
  }
}

const viewHomework = async row => {
  currentHomework.value = await api.homework.get(row.id)
  detailVisible.value = true
}

const goToSubmitPage = row => {
  router.push(`/homework/${row.id}/submit`)
}

const goToSubmissionStatus = row => {
  router.push(`/homework/${row.id}/submissions`)
}

const openAttachment = async row => {
  if (!row?.attachment_url) {
    return
  }
  await downloadAttachment(row.attachment_url, row.attachment_name)
}

const hasHomeworkReview = row =>
  row.review_score !== null && row.review_score !== undefined || Boolean(row.review_comment)

const formatScore = value => {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) {
    return '--'
  }
  return Number.isInteger(numericValue) ? `${numericValue}` : numericValue.toFixed(1)
}

const scoreTag = score => {
  const numericScore = Number(score)
  if (numericScore >= 90) return 'success'
  if (numericScore >= 60) return 'warning'
  return 'danger'
}

const resolveTaskStatus = row => row?.latest_task_status || row?.task_status || ''

const formatTaskStatus = status => ({
  queued: '排队中',
  processing: '处理中',
  success: '评分成功',
  failed: '评分失败'
}[status] || status || '未知')

const taskTagType = status => ({
  queued: 'info',
  processing: 'warning',
  success: 'success',
  failed: 'danger'
}[status] || 'info')

const deleteHomework = async row => {
  try {
    await ElMessageBox.confirm(`确认删除作业“${row.title}”吗？`, '删除作业', { type: 'warning' })
    await api.homework.delete(row.id)
    ElMessage.success('作业已删除')
    await loadHomeworks()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除作业失败', error)
    }
  }
}

const formatDate = value => {
  if (!value) return '未设置'
  return new Date(value).toLocaleString('zh-CN')
}

onMounted(() => {
  loadHomeworks()
})

watch(selectedCourse, () => {
  loadHomeworks()
})
</script>

<style scoped>
.homework-page {
  padding: 24px;
  width: min(100%, 1280px);
  margin: 0 auto;
  min-width: 0;
  overflow-x: hidden;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
}

.page-title {
  margin: 0 0 8px;
  font-size: var(--wa-font-size-stat);
  color: var(--wa-color-text);
}

.page-subtitle {
  margin: 0;
  color: var(--wa-color-text-muted);
  font-size: var(--wa-font-size-md);
}

.header-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 12px;
  flex: 0 0 auto;
  min-width: 0;
}

.attachment-help,
.muted-text {
  color: #64748b;
  font-size: 13px;
}

.attachment-help {
  margin-top: 8px;
}

.batch-late-hint {
  margin: 0 0 12px;
  color: #64748b;
  font-size: 14px;
}

.batch-late-tip {
  margin: 12px 0 0;
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}

.attachment-preview {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.review-summary {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.review-comment-wrap {
  margin-top: 4px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
}

.review-meta,
.rule-text,
.late-tip {
  color: #64748b;
  font-size: 12px;
  line-height: 1.55;
}

.rule-cell,
.task-status-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.task-status-cell--student {
  align-items: center;
  gap: 4px;
}

.homework-list-card {
  overflow: hidden;
  border-radius: var(--wa-radius-lg);
  border: 1px solid color-mix(in srgb, var(--wa-border-subtle) 86%, transparent);
  box-shadow: var(--wa-shadow-surface);
}

.homework-list-card :deep(.el-card__body) {
  overflow-x: hidden;
}

.homework-table-scroll {
  overflow-x: auto;
}

.homework-table-scroll :deep(.el-table) {
  min-width: 1180px;
}

.homework-table-scroll :deep(.el-table__fixed-right) {
  box-shadow: -10px 0 18px rgba(15, 23, 42, 0.06);
}

.homework-table-scroll :deep(.homework-actions-column .cell),
.homework-table-scroll :deep(.homework-actions-column__header .cell) {
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding-left: 8px;
  padding-right: 8px;
}

.homework-table--student :deep(.el-table__row td) {
  padding-top: 10px;
  padding-bottom: 10px;
}

.wa-table-actions {
  display: inline-flex;
  flex-wrap: nowrap;
  justify-content: center;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.wa-table-actions :deep(.el-dropdown) {
  flex: 0 0 auto;
}

.wa-table-actions :deep(.el-button) {
  flex: 0 0 auto;
  min-width: 0;
  margin-left: 0;
  padding-left: 10px;
  padding-right: 10px;
}

.wa-table-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

.wa-table-actions--teacher {
  gap: 6px;
}

.wa-table-actions--teacher :deep(.el-button) {
  white-space: nowrap;
  padding-left: 8px;
  padding-right: 8px;
}

.student-homework-actions {
  display: inline-flex;
  flex-direction: column;
  gap: 4px;
  align-items: center;
  width: 100%;
}

.student-homework-actions :deep(.el-button) {
  margin-left: 0;
  min-width: 0;
  padding-left: 6px;
  padding-right: 6px;
}

.student-review-summary {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: center;
}

.student-review-summary__chips {
  display: inline-flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 6px;
}

.homework-empty-state {
  display: flex;
  min-height: 220px;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 12px;
  padding: 28px 16px;
  color: #64748b;
  text-align: center;
}

.homework-empty-state__title {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
}

.homework-empty-state p {
  max-width: 420px;
  margin: 0;
  line-height: 1.6;
}

.late-rules {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: stretch;
  }

  .header-actions {
    justify-content: stretch;
  }

  .header-actions :deep(.el-button) {
    flex: 1 1 160px;
  }

  .homework-page {
    overflow-x: hidden;
  }

  .homework-list-card :deep(.el-card__body) {
    padding: 12px;
  }
}
</style>
