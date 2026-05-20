<template>
  <div class="submission-page" v-loading="loading">
    <div class="page-header">
      <div>
        <h1 class="page-title">提交作业</h1>
        <p class="page-subtitle">
          {{ homework ? `${homework.title} · ${homework.subject_name || selectedCourse?.name || '当前课程'}` : '查看作业要求并提交附件或说明。' }}
        </p>
      </div>
      <el-button @click="router.push('/homework')">返回作业列表</el-button>
    </div>

    <el-empty v-if="!homework && !loading" description="未找到作业信息" />

    <template v-else-if="homework">
      <el-card shadow="never" class="info-card">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="作业标题" :span="2">{{ homework.title }}</el-descriptions-item>
          <el-descriptions-item label="课程">{{ homework.subject_name || selectedCourse?.name || '未设置' }}</el-descriptions-item>
          <el-descriptions-item label="截止时间">{{ formatDate(homework.due_date) }}</el-descriptions-item>
          <el-descriptions-item label="发布时间">{{ formatDate(homework.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="发布人">{{ homework.creator_name || '未设置' }}</el-descriptions-item>
          <el-descriptions-item label="满分">{{ formatScore(homework.max_score) }}</el-descriptions-item>
          <el-descriptions-item label="自动评分">{{ homework.auto_grading_enabled ? '已启用' : '未启用' }}</el-descriptions-item>
          <el-descriptions-item label="提交次数">
            <template v-if="homework.max_submissions != null">
              已用 {{ homework.attempt_count || 0 }} / 上限 {{ homework.max_submissions }}，
              还可提交 {{ homework.submissions_remaining ?? 0 }} 次
            </template>
            <template v-else>不限制（{{ homework.attempt_count || 0 }} 次已提交）</template>
          </el-descriptions-item>
          <el-descriptions-item label="评分规则" :span="2">{{ homework.grading_rule_hint }}</el-descriptions-item>
          <el-descriptions-item label="作业内容" :span="2">
            <PlainOrMarkdownBlock
              :text="homework.content"
              :format="homework.content_format"
              variant="student"
            />
          </el-descriptions-item>
          <el-descriptions-item label="评分要点（学生可见）" :span="2">
            <RichMarkdownDisplay :markdown="homework.rubric_text" variant="student" empty-text="未设置" />
          </el-descriptions-item>
          <el-descriptions-item label="作业附件" :span="2">
            <el-button v-if="homework.attachment_url" type="primary" link @click="openAttachment(homework.attachment_url, homework.attachment_name)">
              {{ homework.attachment_name || '下载附件' }}
            </el-button>
            <span v-else class="muted-text">暂无附件</span>
          </el-descriptions-item>
          <el-descriptions-item label="有效成绩与评语（截止前/计入总评取最高）" :span="2">
            <div v-if="summaryReviewText" class="feedback-panel feedback-panel--hero">
              <div class="feedback-panel__head">
                <el-tag
                  v-if="historySummary?.review_score !== null && historySummary?.review_score !== undefined"
                  :type="scoreTag(historySummary.review_score)"
                  size="small"
                  effect="dark"
                  round
                >
                  {{ formatScore(historySummary.review_score) }}
                </el-tag>
                <el-tag v-if="historySummary?.used_llm_assist" type="warning" size="small" effect="plain">
                  最近一次提交申报使用大模型辅助
                </el-tag>
              </div>
              <FeedbackRichText class="feedback-panel__body" :text="summaryReviewText" variant="student" />
            </div>
            <span v-else class="muted-text">暂无评分</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="appealStatusLabel" label="申诉" :span="2">
            <el-tag
              v-if="historySummary?.appeal_status"
              :type="getAppealStatusTagType(historySummary.appeal_status)"
              size="small"
            >
              {{ getAppealStatusLabel(historySummary.appeal_status, { verbose: true }) }}
            </el-tag>
            <span v-else class="muted-text">—</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="historySummary?.appeal_reason_text" label="申诉理由" :span="2">
            <span class="appeal-text">{{ historySummary.appeal_reason_text }}</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="historySummary?.appeal_teacher_response" label="教师回复" :span="2">
            <span class="appeal-text">{{ historySummary.appeal_teacher_response }}</span>
          </el-descriptions-item>
        </el-descriptions>
        <el-alert
          v-if="historySummary?.effective_score_note_zh"
          type="info"
          :closable="false"
          show-icon
          class="effective-score-banner"
        >
          {{ historySummary.effective_score_note_zh }}
        </el-alert>
      </el-card>

      <CourseDiscussionPanel
        target-type="homework"
        :target-id="homework.id"
        :subject-id="homework.subject_id"
        :class-id="homework.class_id"
        :discussion-requires-context="homework.discussion_requires_context"
        :is-student="userStore.isStudent"
      />

      <el-card shadow="never" class="info-card">
        <template #header>
          <div class="card-header">
            <span>我的提交</span>
            <div class="card-header-tags">
              <el-tag v-if="hasExistingSubmission" type="success">已提交 {{ attempts.length }} 次</el-tag>
              <el-tag v-else type="info">未提交</el-tag>
              <el-tag v-if="latestTaskStatus" :type="taskTagType(latestTaskStatus)">{{ formatTaskStatus(latestTaskStatus) }}</el-tag>
            </div>
          </div>
        </template>

        <div class="submission-alerts">
          <el-steps
            v-if="showSubmitFlowSteps"
            class="submit-flow-steps"
            :active="submitFlowActive"
            align-center
            finish-status="success"
          >
            <el-step title="完善本轮" description="说明、附件与申报" />
            <el-step title="保存提交" description="写入并参与自动评分" />
          </el-steps>
          <el-alert
            v-if="latestTaskStatus === 'failed' && historySummary?.latest_task_error"
            type="error"
            :closable="false"
            :title="`自动评分失败：${historySummary.latest_task_error}`"
          />
          <el-alert
            v-else-if="latestTaskStatus && latestTaskStatus !== 'success'"
            type="info"
            :closable="false"
            :title="`自动评分任务状态：${formatTaskStatus(latestTaskStatus)}`"
          />
          <el-alert
            v-if="isPastDue && homework.allow_late_submission"
            type="warning"
            :closable="false"
            title="当前提交将被标记为迟交。默认是否影响评分由作业规则决定。"
          />
          <el-alert
            v-if="isSubmissionLocked"
            type="error"
            :closable="false"
            title="已超过截止时间且该作业不允许补交。"
          />
          <el-alert
            v-else-if="isMaxSubmissionsReached"
            type="warning"
            :closable="false"
            title="已达到该作业允许的最大提交次数，无法再提交。"
          />
        </div>

        <div v-if="userStore.isStudent && canShowAppealCta" class="appeal-bar">
          <el-button type="warning" plain data-testid="homework-submit-open-appeal" :disabled="appealSubmitting" @click="appealDialogVisible = true">
            向教师申诉
          </el-button>
          <span class="attachment-help">如对分数或评语有异议，请说明自动评分或评语中不合理之处（至少 10 字）。每名每项作业仅可申诉一次。</span>
        </div>

        <el-form label-position="top" @submit.prevent>
          <el-form-item
            v-if="historySummary?.allow_feedback_followup && attempts.length"
            label="提交方式"
          >
            <el-radio-group v-model="form.submission_mode" data-testid="homework-submit-mode" :disabled="isSubmitDisabled">
              <el-radio label="full">完整提交</el-radio>
              <el-radio label="feedback_followup">按反馈补充</el-radio>
            </el-radio-group>
            <div class="attachment-help">
              选择「按反馈补充」时，系统会把<strong>上一轮</strong>的说明与附件一并交给评分模型，本轮说明只需针对评语中的不足做补充或修订，无需全文重写。
              若不重新上传附件，将自动沿用上一轮的附件。
            </div>
          </el-form-item>

          <el-form-item label="正文">
            <MarkdownEditorPanel
              v-model="form.content"
              v-model:content-format="form.content_format"
              :min-rows="6"
              :max-rows="22"
              :disabled="isSubmitDisabled"
              :placeholder="contentPlaceholder"
              hint="可选 Markdown / LaTeX；也可切换为纯文本（字面保存，不解析排版符号）。"
              :show-format-toggle="true"
              :enable-image-upload="!isSubmitDisabled"
              data-testid="homework-submit-content"
            />
          </el-form-item>

          <el-form-item label="诚信申报">
            <div class="integrity-declaration">
              <el-switch
                v-model="form.used_llm_assist"
                data-testid="homework-submit-used-llm-assist"
                :disabled="isSubmitDisabled"
                active-text="本次作答曾使用大语言模型辅助"
                inactive-text="未使用大语言模型辅助作答"
              />
              <p class="integrity-declaration__hint">
                请如实选择。若选择「曾使用」，自动评分将更关注思路与知识功底，弱化措辞与排版细节。
              </p>
            </div>
          </el-form-item>

          <el-form-item label="附件">
            <el-upload
              :auto-upload="false"
              :show-file-list="false"
              :limit="1"
              :disabled="isSubmitDisabled"
              :on-change="handleAttachmentChange"
            >
              <el-button data-testid="homework-submit-attachment-trigger" :disabled="isSubmitDisabled">选择附件</el-button>
            </el-upload>
            <div class="attachment-help">{{ attachmentHintText }}</div>
            <div v-if="attachmentDisplayName" class="attachment-preview">
              <el-button
                v-if="!attachmentFile && form.attachment_url"
                type="primary"
                link
                @click="openAttachment(form.attachment_url, attachmentDisplayName)"
              >
                {{ attachmentDisplayName }}
              </el-button>
              <span v-else>{{ attachmentDisplayName }}</span>
                <el-button link type="danger" :disabled="isSubmitDisabled" @click="removeAttachment">移除</el-button>
            </div>
          </el-form-item>

          <div class="form-actions">
            <el-button
              type="primary"
              data-testid="homework-submit-save"
              :loading="submitting"
              :disabled="isSubmitDisabled"
              @click="submitForm"
            >
              保存提交
            </el-button>
          </div>
        </el-form>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div class="card-header">
            <span>提交历史</span>
            <span class="muted-text">点击可下载历史附件，主界面始终显示最高分对应评语。</span>
          </div>
        </template>

        <el-empty v-if="!attempts.length" description="暂无提交历史" />

        <el-timeline v-else>
          <el-timeline-item
            v-for="attempt in attempts"
            :key="attempt.id"
            :timestamp="formatDate(attempt.submitted_at)"
            placement="top"
          >
            <div class="attempt-card">
              <div class="attempt-tags">
                <el-tag size="small" type="primary">第 {{ getAttemptLabel(attempt) }} 次提交</el-tag>
                <el-tag v-if="attempt.is_late" size="small" type="warning">迟交</el-tag>
                <el-tag v-if="attempt.used_llm_assist" size="small" type="warning" effect="plain">申报大模型辅助</el-tag>
                <el-tag v-if="attempt.submission_mode === 'feedback_followup'" size="small" type="info" effect="plain">
                  按反馈补充
                </el-tag>
                <el-tag
                  v-if="attempt.review_score !== null && attempt.review_score !== undefined"
                  :type="scoreTag(attempt.review_score)"
                  size="small"
                >
                  {{ formatScore(attempt.review_score) }}
                </el-tag>
                <el-tag v-if="attempt.task_status" :type="taskTagType(attempt.task_status)" size="small">
                  {{ formatTaskStatus(attempt.task_status) }}
                </el-tag>
              </div>
              <div class="attempt-body">
                <div class="attempt-note-label">正文</div>
                <PlainOrMarkdownBlock
                  class="attempt-body-md"
                  :text="attempt.content || ''"
                  :format="attempt.content_format"
                  variant="student"
                />
                <div v-if="attempt.attachment_url" class="attempt-link">
                  <el-button type="primary" link @click="openAttachment(attempt.attachment_url, attempt.attachment_name)">
                    {{ attempt.attachment_name || '下载附件' }}
                  </el-button>
                </div>
                <template v-if="attempt.review_comment">
                  <div class="attempt-note-label">评语（支持 Markdown / LaTeX）</div>
                  <div class="feedback-panel feedback-panel--compact">
                    <FeedbackRichText :text="attempt.review_comment" variant="student" />
                  </div>
                </template>
                <div v-if="attempt.task_error" class="attempt-error">{{ attempt.task_error }}</div>
              </div>
            </div>
          </el-timeline-item>
        </el-timeline>
      </el-card>
    </template>

    <el-dialog v-model="appealDialogVisible" data-testid="homework-submit-appeal-dialog" title="向教师申诉" width="560px" destroy-on-close @closed="appealReason = ''">
      <el-input
        v-model="appealReason"
        data-testid="homework-submit-appeal-reason"
        type="textarea"
        :rows="8"
        maxlength="8000"
        show-word-limit
        placeholder="请说明您认为评分或评语不合理之处（例如：自动评分忽略了哪些要点、哪条评语与您的作答不符等），至少 10 字。"
      />
      <template #footer>
        <el-button @click="appealDialogVisible = false">取消</el-button>
        <el-button type="primary" data-testid="homework-submit-appeal-confirm" :loading="appealSubmitting" @click="submitAppeal">提交申诉</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import api from '@/api'
import CourseDiscussionPanel from '@/components/CourseDiscussionPanel.vue'
import FeedbackRichText from '@/components/FeedbackRichText.vue'
import MarkdownEditorPanel from '@/components/MarkdownEditorPanel.vue'
import PlainOrMarkdownBlock from '@/components/PlainOrMarkdownBlock.vue'
import RichMarkdownDisplay from '@/components/RichMarkdownDisplay.vue'
import { useUserStore } from '@/stores/user'
import { getAppealStatusLabel, getAppealStatusTagType } from '@/utils/appealNotificationActions'
import { attachmentHintText, downloadAttachment, validateAttachmentFile } from '@/utils/attachments'
import { normalizeContentFormat } from '@/utils/contentFormat'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const submitting = ref(false)
let gradePollTimer = null
const appealDialogVisible = ref(false)
const appealReason = ref('')
const appealSubmitting = ref(false)
const homework = ref(null)
const attachmentFile = ref(null)
const hasExistingSubmission = ref(false)
const historySummary = ref(null)
const attempts = ref([])
const currentTime = ref(Date.now())
let clockTimer = null

const selectedCourse = computed(() => userStore.selectedCourse)
const attachmentDisplayName = computed(() => attachmentFile.value?.name || form.attachment_name || '')
const latestTaskStatus = computed(() => historySummary.value?.latest_task_status || '')
const summaryReviewText = computed(() => historySummary.value?.review_comment || '')
const appealStatusLabel = computed(() => Boolean(historySummary.value?.appeal_status))

const hasGradeResult = computed(() => {
  const h = historySummary.value
  if (!h) return false
  if (h.review_score !== null && h.review_score !== undefined) return true
  if (h.review_comment && String(h.review_comment).trim()) return true
  return h.latest_task_status === 'success' || h.latest_task_status === 'failed'
})

const canShowAppealCta = computed(
  () =>
    userStore.isStudent &&
    hasExistingSubmission.value &&
    historySummary.value?.id &&
    !historySummary.value?.appeal_status &&
    hasGradeResult.value
)
const isPastDue = computed(() => {
  if (!homework.value?.due_date) {
    return false
  }
  const dueTime = new Date(homework.value.due_date).getTime()
  return Number.isFinite(dueTime) && currentTime.value > dueTime
})
const isSubmissionLocked = computed(() => {
  return isPastDue.value && !homework.value?.allow_late_submission
})

const isMaxSubmissionsReached = computed(() => {
  const cap = homework.value?.max_submissions
  if (cap == null) {
    return false
  }
  const rem = homework.value?.submissions_remaining
  if (rem != null) {
    return rem <= 0
  }
  return (homework.value?.attempt_count || 0) >= Number(cap)
})

const isSubmitDisabled = computed(() => isSubmissionLocked.value || isMaxSubmissionsReached.value)

const showSubmitFlowSteps = computed(() => Boolean(homework.value?.auto_grading_enabled))

const submitFlowActive = computed(() => {
  if (!showSubmitFlowSteps.value || isSubmitDisabled.value) {
    return 0
  }
  const ready = Boolean(
    (form.content || '').trim() || form.attachment_url || attachmentFile.value
  )
  return ready ? 1 : 0
})

const contentPlaceholder = computed(() => {
  if (form.submission_mode === 'feedback_followup') {
    return '本轮可只写针对上一轮评语要改进的点、补充推导或修订说明；上一轮正文与附件会一并送给评分模型。'
  }
  return '可填写作业说明、答题思路或补充信息。'
})

const form = reactive({
  content: '',
  content_format: 'markdown',
  attachment_name: '',
  attachment_url: '',
  remove_attachment: false,
  used_llm_assist: false,
  submission_mode: 'full'
})

const applySubmission = submission => {
  hasExistingSubmission.value = Boolean(submission)
  form.content = submission?.content || ''
  form.content_format = normalizeContentFormat(submission?.content_format)
  form.attachment_name = submission?.attachment_name || ''
  form.attachment_url = submission?.attachment_url || ''
  form.remove_attachment = false
  form.used_llm_assist = Boolean(submission?.used_llm_assist)
  form.submission_mode = 'full'
  attachmentFile.value = null
}

const applyHistory = history => {
  historySummary.value = history?.summary || null
  attempts.value = history?.attempts || []
}

const stopGradePolling = () => {
  if (gradePollTimer) {
    window.clearInterval(gradePollTimer)
    gradePollTimer = null
  }
}

const maybeStartGradePolling = () => {
  stopGradePolling()
  if (!userStore.isStudent) {
    return
  }
  const st = historySummary.value?.latest_task_status
  if (st !== 'queued' && st !== 'processing') {
    return
  }
  gradePollTimer = window.setInterval(() => {
    loadPage({ silent: true })
  }, 8000)
}

const loadPage = async (opts = {}) => {
  const silent = Boolean(opts?.silent)
  if (!silent) {
    loading.value = true
  }
  try {
    const [homeworkDetail, submission, history] = await Promise.all([
      api.homework.get(route.params.id),
      api.homework.getMySubmission(route.params.id),
      api.homework.getMySubmissionHistory(route.params.id)
    ])
    homework.value = homeworkDetail
    applySubmission(submission)
    applyHistory(history)
    maybeStartGradePolling()
  } finally {
    if (!silent) {
      loading.value = false
    }
  }
}

const handleAttachmentChange = uploadFile => {
  if (isSubmitDisabled.value) {
    return false
  }

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
  if (isSubmitDisabled.value) {
    return
  }

  attachmentFile.value = null
  if (form.attachment_url) {
    form.remove_attachment = true
  }
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
  attachmentFile.value = null
  form.attachment_name = uploaded.attachment_name
  form.attachment_url = uploaded.attachment_url
  form.remove_attachment = false

  return {
    attachment_name: uploaded.attachment_name,
    attachment_url: uploaded.attachment_url
  }
}

const submitAppeal = async () => {
  const text = (appealReason.value || '').trim()
  if (text.length < 10) {
    ElMessage.warning('申诉理由至少 10 个字')
    return
  }
  const sid = historySummary.value?.id
  if (!sid) {
    ElMessage.error('找不到提交记录')
    return
  }
  appealSubmitting.value = true
  try {
    await api.homework.submitAppeal(route.params.id, sid, { reason_text: text })
    ElMessage.success('申诉已提交，教师将收到通知')
    appealDialogVisible.value = false
    appealReason.value = ''
    await loadPage()
  } finally {
    appealSubmitting.value = false
  }
}

const submitForm = async () => {
  if (isSubmissionLocked.value) {
    ElMessage.warning('已超过截止时间且当前作业不允许补交。')
    return
  }

  submitting.value = true
  try {
    const attachment = await uploadAttachmentIfNeeded()
    const priorId =
      form.submission_mode === 'feedback_followup' && attempts.value.length ? attempts.value[0].id : undefined
    await api.homework.submit(route.params.id, {
      content: form.content?.trim() || null,
      content_format: normalizeContentFormat(form.content_format),
      attachment_name: attachment.attachment_name,
      attachment_url: attachment.attachment_url,
      remove_attachment: form.remove_attachment,
      used_llm_assist: Boolean(form.used_llm_assist),
      submission_mode: form.submission_mode,
      prior_attempt_id: priorId
    })
    ElMessage.success('作业已提交')
    await loadPage()
  } finally {
    submitting.value = false
  }
}

const openAttachment = async (url, attachmentName) => {
  if (!url) {
    return
  }
  await downloadAttachment(url, attachmentName)
}

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

const getAttemptLabel = attempt => {
  const index = attempts.value.findIndex(item => item.id === attempt.id)
  return index >= 0 ? attempts.value.length - index : '-'
}

const formatDate = value => {
  if (!value) {
    return '未设置'
  }
  return new Date(value).toLocaleString('zh-CN')
}

onMounted(() => {
  currentTime.value = Date.now()
  clockTimer = window.setInterval(() => {
    currentTime.value = Date.now()
  }, 30000)
  loadPage()
})

onBeforeUnmount(() => {
  if (clockTimer) {
    window.clearInterval(clockTimer)
    clockTimer = null
  }
  stopGradePolling()
})

watch(
  () => route.params.id,
  () => {
    stopGradePolling()
    loadPage()
  }
)
</script>

<style scoped>
.submission-page {
  padding: 24px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 24px;
}

.page-title {
  margin: 0 0 8px;
  font-size: 28px;
  color: #0f172a;
}

.page-subtitle {
  margin: 0;
  color: #64748b;
}

.info-card {
  margin-bottom: 20px;
}

.effective-score-banner {
  margin-top: 12px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.attachment-help,
.muted-text {
  color: #64748b;
  font-size: 13px;
}

.attachment-help {
  margin-top: 8px;
}

.integrity-declaration {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  column-gap: 28px;
  row-gap: 14px;
}

.integrity-declaration__hint {
  margin: 0;
  flex: 1 1 220px;
  min-width: 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.55;
}

.submission-alerts {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 18px;
}

.appeal-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding: 12px 14px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 10px;
}

.appeal-text {
  white-space: pre-wrap;
  line-height: 1.6;
}

.submit-flow-steps {
  padding: 8px 12px 4px;
  background: #f8fafc;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
}

.submit-flow-steps :deep(.el-step__title) {
  font-size: 13px;
}

.submit-flow-steps :deep(.el-step__description) {
  font-size: 12px;
}

.deadline-warning {
  margin-top: 8px;
  color: #dc2626;
  font-size: 13px;
}

.attachment-preview {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.card-header-tags,
.attempt-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.feedback-panel {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: linear-gradient(165deg, #f8fafc 0%, #ffffff 55%);
  padding: 14px 16px;
}

.feedback-panel--hero {
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
}

.feedback-panel--compact {
  padding: 10px 12px;
  margin-top: 4px;
}

.feedback-panel__head {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}

.feedback-panel__body :deep(.feedback-rich) {
  font-size: 15px;
}

.attempt-note-label {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-top: 6px;
}

.attempt-plain {
  white-space: pre-wrap;
  color: #475569;
}

.attempt-card {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 14px;
  background: #fff;
}

.attempt-body {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: #475569;
  white-space: pre-wrap;
}

.attempt-link {
  margin-top: 2px;
}


.attempt-error {
  color: #dc2626;
  font-size: 13px;
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
  }

  .form-actions {
    width: 100%;
  }

  .form-actions :deep(.el-button) {
    flex: 1;
  }
}
</style>
