<template>
  <div class="submission-review-page" v-loading="loading">
    <header class="review-header">
      <div class="review-header__left">
        <el-button type="primary" plain data-testid="homework-submission-review-back" @click="goBack">
          返回提交列表
        </el-button>
        <div v-if="homework" class="review-header__titles">
          <h1 class="review-title">提交详情与评分</h1>
          <p class="review-subtitle">{{ homework.title }} · {{ homework.subject_name || selectedCourse?.name || '当前课程' }}</p>
        </div>
      </div>
    </header>

    <el-empty v-if="loadError" :description="loadError" />

    <template v-else-if="homework && detailRow">
      <section class="review-section review-section--student">
        <div class="review-section__head">
          <h2 class="review-section__title">学生与提交状态</h2>
        </div>
        <div class="review-meta-grid">
          <div class="review-meta-item">
            <span class="review-meta-label">学生</span>
            <strong>{{ detailRow.student_name }}</strong>
            <span class="muted">（{{ detailRow.student_no || '无学号' }}）</span>
          </div>
          <div class="review-meta-item">
            <span class="review-meta-label">申诉</span>
            <el-tag
              v-if="detailRow.appeal_status"
              :type="getAppealStatusTagType(detailRow.appeal_status)"
              size="small"
            >
              {{ getAppealStatusLabel(detailRow.appeal_status) }}
            </el-tag>
            <span v-else class="muted">—</span>
            <el-button
              v-if="isActionableAppealStatus(detailRow.appeal_status)"
              size="small"
              type="primary"
              link
              class="review-meta-action"
              :loading="detailAckLoading"
              @click="acknowledgeAppeal"
            >
              标记已阅
            </el-button>
            <el-button
              v-if="isActionableAppealStatus(detailRow.appeal_status)"
              size="small"
              type="danger"
              link
              class="review-meta-action"
              @click="openAppealResolveDialog"
            >
              处理申诉
            </el-button>
          </div>
          <div class="review-meta-item">
            <span class="review-meta-label">任务状态</span>
            <span v-if="detailRow.latest_task_status">{{ formatTaskStatus(detailRow.latest_task_status) }}</span>
            <span v-else class="muted">—</span>
          </div>
          <div class="review-meta-item">
            <span class="review-meta-label">有效成绩</span>
            <template v-if="detailRow.review_score !== null && detailRow.review_score !== undefined">
              <el-tag :type="scoreTag(detailRow.review_score)" size="small">{{ formatScore(detailRow.review_score) }}</el-tag>
            </template>
            <span v-else class="muted">—</span>
          </div>
        </div>
        <div v-if="detailRow.appeal_reason_text" class="review-appeal-card">
          <div class="muted small-label">申诉理由</div>
          <p class="review-appeal-text">{{ detailRow.appeal_reason_text }}</p>
        </div>
        <div v-if="detailRow.appeal_teacher_response" class="review-appeal-card">
          <div class="muted small-label">教师回复</div>
          <p class="review-appeal-text">{{ detailRow.appeal_teacher_response }}</p>
        </div>
        <p v-if="detailRow.effective_score_note_zh" class="review-effective-note">{{ detailRow.effective_score_note_zh }}</p>
        <div class="review-meta-actions">
          <el-button
            v-if="detailRow.latest_task_log?.length"
            type="primary"
            link
            data-testid="btn-open-llm-log"
            @click="openTaskLog(detailRow)"
          >
            查看 LLM 日志
          </el-button>
          <el-button v-if="homework.auto_grading_enabled" :loading="detailRow.regrading" @click="regradeLatest">
            触发 LLM 重评（最新一轮）
          </el-button>
        </div>
      </section>

      <section class="review-section review-section--answer">
        <div class="review-section__head">
          <h2 class="review-section__title">学生作答</h2>
          <el-tag v-if="detailRow.latest_attempt_is_late" type="warning" size="small" effect="plain">迟交</el-tag>
          <el-tag v-if="detailRow.used_llm_assist" type="warning" size="small" effect="plain">申报大模型辅助</el-tag>
        </div>
        <div class="review-answer-card">
          <div data-testid="homework-submission-detail-body" class="review-body-markdown">
            <PlainOrMarkdownBlock
              :text="detailRow.content || ''"
              :format="detailRow.content_format"
              variant="teacher"
              empty-text="（无正文）"
            />
          </div>
          <div v-if="detailRow.attachment_url" class="review-attach">
            <el-button type="primary" link @click="openAttachment(detailRow.attachment_url, detailRow.attachment_name)">
              {{ detailRow.attachment_name || '下载附件' }}
            </el-button>
          </div>
        </div>
      </section>

      <section v-if="detailRow.review_comment" class="review-section review-section--comment-readonly">
        <h2 class="review-section__title">当前评语（汇总）</h2>
        <div class="review-comment-card feedback-inline">
          <FeedbackRichText :text="detailRow.review_comment" variant="teacher" />
        </div>
      </section>

      <section class="review-section review-section--grade">
        <h2 class="review-section__title">调整分数与评语</h2>
        <p class="review-hint muted">作用于所选提交汇总（默认对应最新一轮尝试）；保存后将刷新本页与列表。</p>
        <div class="detail-review-block">
          <div class="review-input-row">
            <span class="review-input-label">分数</span>
            <el-input
              v-model="detailRow.review_score_input"
              :placeholder="`0 ~ ${formatScore(homework?.max_score)}`"
              class="review-score-input"
            />
          </div>
          <el-input
            v-model="detailRow.review_comment_input"
            type="textarea"
            :rows="5"
            placeholder="评语（支持 Markdown / LaTeX）"
            class="review-comment-input"
          />
          <el-button type="primary" size="large" :loading="detailRow.saving_review" @click="saveReviewFromDetail">
            保存评分
          </el-button>
        </div>
      </section>

      <section class="review-section">
        <el-collapse v-model="historyOpen">
          <el-collapse-item title="提交与评分历史" name="hist">
            <el-empty v-if="!historyAttempts.length" description="暂无历史记录" />
            <el-timeline v-else>
              <el-timeline-item
                v-for="attempt in historyAttempts"
                :key="attempt.id"
                :timestamp="formatDate(attempt.submitted_at)"
                placement="top"
              >
                <div class="attempt-card" :data-testid="`homework-history-attempt-${attempt.id}`">
                  <div class="attempt-summary">
                    <button
                      class="attempt-toggle"
                      type="button"
                      :aria-expanded="isHistoryAttemptExpanded(attempt.id)"
                      :data-testid="`homework-history-attempt-toggle-${attempt.id}`"
                      @click="toggleHistoryAttempt(attempt.id)"
                    >
                      <el-icon>
                        <Minus v-if="isHistoryAttemptExpanded(attempt.id)" />
                        <Plus v-else />
                      </el-icon>
                    </button>
                    <div class="attempt-summary__main">
                      <div class="attempt-tags">
                        <el-tag size="small" type="primary">提交 #{{ attempt.id }}</el-tag>
                        <el-tag v-if="attempt.is_late" size="small" type="warning">迟交</el-tag>
                        <el-tag v-if="attempt.used_llm_assist" size="small" type="warning" effect="plain">申报大模型</el-tag>
                        <el-tag
                          v-if="attempt.review_score !== null && attempt.review_score !== undefined"
                          :type="scoreTag(attempt.review_score)"
                          size="small"
                        >
                          {{ formatScore(attempt.review_score) }}
                        </el-tag>
                        <el-tooltip
                          v-if="attempt.task_status === 'failed' && attempt.task_error"
                          :content="attemptFailureTooltip(attempt)"
                          placement="top"
                        >
                          <el-tag :type="taskTagType(attempt.task_status)" size="small">
                            {{ formatTaskStatus(attempt.task_status) }}
                          </el-tag>
                        </el-tooltip>
                        <el-tag v-else-if="attempt.task_status" :type="taskTagType(attempt.task_status)" size="small">
                          {{ formatTaskStatus(attempt.task_status) }}
                        </el-tag>
                        <el-button
                          v-if="attempt.task_log?.length"
                          type="primary"
                          link
                          size="small"
                          data-testid="btn-open-llm-log-history"
                          @click="openTaskLog(detailRow, attempt)"
                        >
                          LLM 日志
                        </el-button>
                      </div>
                      <div class="attempt-summary__preview" :data-testid="`homework-history-attempt-preview-${attempt.id}`">
                        {{ attemptPreviewLine(attempt) }}
                      </div>
                    </div>
                  </div>

                  <div
                    v-show="isHistoryAttemptExpanded(attempt.id)"
                    class="attempt-body"
                    :data-testid="`homework-history-attempt-body-${attempt.id}`"
                  >
                    <PlainOrMarkdownBlock
                      :text="attempt.content || ''"
                      :format="attempt.content_format"
                      variant="teacher"
                      empty-text="无正文"
                    />
                    <div v-if="attempt.attachment_url" class="attempt-link">
                      <el-button type="primary" link @click="openAttachment(attempt.attachment_url, attempt.attachment_name)">
                        {{ attempt.attachment_name || '下载附件' }}
                      </el-button>
                    </div>
                    <div v-if="attempt.review_comment" class="attempt-feedback">
                      <div class="muted small-label">评语</div>
                      <FeedbackRichText :text="attempt.review_comment" variant="teacher" />
                    </div>
                    <div v-if="attempt.task_error" class="attempt-error">{{ attempt.task_error }}</div>
                  </div>

                  <div v-show="isHistoryAttemptExpanded(attempt.id)" class="attempt-actions">
                    <el-input
                      v-model="attempt.review_score_input"
                      :placeholder="`分数 0-${formatScore(homework?.max_score)}`"
                      class="review-score-input"
                    />
                    <el-input
                      v-model="attempt.review_comment_input"
                      type="textarea"
                      :rows="2"
                      placeholder="该次提交的评语（支持 Markdown / LaTeX）"
                      class="review-comment-input"
                    />
                    <el-button type="primary" :loading="attempt.saving_review" @click="saveReviewForAttempt(attempt)">
                      按此提交评分
                    </el-button>
                    <el-button v-if="homework.auto_grading_enabled" :loading="attempt.regrading" @click="regradeAttempt(attempt)">
                      重评此提交
                    </el-button>
                  </div>
                </div>
              </el-timeline-item>
            </el-timeline>
          </el-collapse-item>
        </el-collapse>
      </section>
    </template>

    <el-dialog v-model="logDialogVisible" :title="logDialogTitle" width="min(720px, 92vw)" destroy-on-close>
      <pre class="llm-log-pre" data-testid="dialog-llm-log-body">{{ logDialogBody }}</pre>
    </el-dialog>

    <el-dialog
      v-model="appealResolveDialogVisible"
      title="处理作业申诉"
      width="560px"
      destroy-on-close
      @closed="resetAppealResolveDialog"
    >
      <div class="review-appeal-dialog">
        <div v-if="detailRow?.appeal_reason_text" class="review-appeal-card review-appeal-card--dialog">
          <div class="muted small-label">学生申诉理由</div>
          <p class="review-appeal-text">{{ detailRow.appeal_reason_text }}</p>
        </div>
        <el-input
          v-model="appealResolveResponse"
          type="textarea"
          :rows="5"
          maxlength="2000"
          show-word-limit
          placeholder="填写教师回复"
        />
      </div>
      <template #footer>
        <el-button @click="appealResolveDialogVisible = false">取消</el-button>
        <el-button type="danger" :loading="appealResolveLoading" @click="submitAppealResolution('rejected')">
          拒绝申诉
        </el-button>
        <el-button type="primary" :loading="appealResolveLoading" @click="submitAppealResolution('resolved')">
          设为已处理
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Minus, Plus } from '@element-plus/icons-vue'

import api from '@/api'
import FeedbackRichText from '@/components/FeedbackRichText.vue'
import PlainOrMarkdownBlock from '@/components/PlainOrMarkdownBlock.vue'
import { useUserStore } from '@/stores/user'
import {
  getAppealStatusLabel,
  getAppealStatusTagType,
  isActionableAppealStatus
} from '@/utils/appealNotificationActions'
import { downloadAttachment } from '@/utils/attachments'
import { isMarkdownFormat } from '@/utils/contentFormat'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const loadError = ref('')
const homework = ref(null)
const detailRow = ref(null)
const detailAckLoading = ref(false)
const appealResolveDialogVisible = ref(false)
const appealResolveLoading = ref(false)
const appealResolveResponse = ref('')
const historyAttempts = ref([])
const expandedHistoryAttemptIds = ref(new Set())
const historyOpen = ref(['hist'])

const logDialogVisible = ref(false)
const logDialogTitle = ref('LLM 调用日志')
const logDialogBody = ref('')

const selectedCourse = computed(() => userStore.selectedCourse)

const homeworkId = computed(() => Number(route.params.id))
const submissionId = computed(() => Number(route.params.submissionId))

const buildSubmissionRow = row => ({
  ...row,
  review_score_input: row.review_score === null || row.review_score === undefined ? '' : String(row.review_score),
  review_comment_input: row.review_comment || '',
  saving_review: false,
  regrading: false,
  latest_task_log: row.latest_task_log || [],
  latest_task_error_code: row.latest_task_error_code || null
})

const buildAttemptHistoryRow = row => ({
  ...row,
  review_score_input: row.review_score === null || row.review_score === undefined ? '' : String(row.review_score),
  review_comment_input: row.review_comment || '',
  saving_review: false,
  regrading: false,
  task_log: row.task_log || [],
  task_error_code: row.task_error_code || null
})

const attemptPreviewLine = attempt => {
  const raw = (attempt?.content || '').trim()
  if (!raw) {
    return '无正文'
  }
  if (!isMarkdownFormat(attempt?.content_format)) {
    const line = raw.split(/\r?\n/).find(Boolean) || raw
    return line.length > 120 ? `${line.slice(0, 118)}…` : line
  }
  const flat = raw.replace(/\r?\n+/g, ' ').replace(/\s+/g, ' ').trim()
  return flat.length > 120 ? `${flat.slice(0, 118)}…` : flat
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

const formatTaskStatus = status =>
  ({ queued: '排队中', processing: '处理中', success: '评分成功', failed: '评分失败' }[status] ||
    status ||
    '未知')

const taskTagType = status =>
  ({ queued: 'info', processing: 'warning', success: 'success', failed: 'danger' }[status] || 'info')

const attemptFailureTooltip = attempt => {
  const code = attempt.task_error_code ? `错误码：${attempt.task_error_code}\n` : ''
  return `${code}${attempt.task_error || ''}`.trim()
}

const goBack = () => {
  router.push({
    path: `/homework/${homeworkId.value}/submissions`,
    query: { ...route.query }
  })
}

const loadHistory = async () => {
  if (!submissionId.value || !Number.isFinite(submissionId.value)) {
    historyAttempts.value = []
    return
  }
  try {
    const history = await api.homework.getSubmissionHistory(homeworkId.value, submissionId.value)
    historyAttempts.value = (history?.attempts || []).map(buildAttemptHistoryRow)
    expandedHistoryAttemptIds.value = new Set(historyAttempts.value.slice(0, 1).map(a => String(a.id)))
  } catch (e) {
    console.error(e)
    historyAttempts.value = []
  }
}

const loadPage = async () => {
  loading.value = true
  loadError.value = ''
  try {
    if (!Number.isFinite(homeworkId.value) || !Number.isFinite(submissionId.value)) {
      loadError.value = '无效的作业或提交 ID'
      return
    }
    const [homeworkDetail, row] = await Promise.all([
      api.homework.get(homeworkId.value),
      api.homework.getSubmissionStatusRow(homeworkId.value, submissionId.value)
    ])
    homework.value = homeworkDetail
    detailRow.value = buildSubmissionRow(row)
    await loadHistory()
  } catch (e) {
    console.error(e)
    const msg = e?.response?.data?.detail
    loadError.value = typeof msg === 'string' ? msg : '加载失败，请返回列表重试。'
    homework.value = null
    detailRow.value = null
    historyAttempts.value = []
  } finally {
    loading.value = false
  }
}

const validateReviewScore = rawValue => {
  const rawScore = `${rawValue ?? ''}`.trim()
  const score = Number(rawScore)
  const maxScore = Number(homework.value?.max_score || 100)
  if (!rawScore || !Number.isFinite(score) || score < 0 || score > maxScore) {
    ElMessage.error(`请输入 0 到 ${formatScore(maxScore)} 之间的数字分数`)
    return null
  }
  return score
}

const saveReviewFromDetail = async () => {
  if (!detailRow.value?.submission_id) {
    return
  }
  const score = validateReviewScore(detailRow.value.review_score_input)
  if (score === null) {
    return
  }
  detailRow.value.saving_review = true
  try {
    await api.homework.reviewSubmission(homeworkId.value, detailRow.value.submission_id, {
      attempt_id: null,
      review_score: score,
      review_comment: detailRow.value.review_comment_input?.trim() || null
    })
    ElMessage.success('评分已保存')
    await loadPage()
  } finally {
    if (detailRow.value) {
      detailRow.value.saving_review = false
    }
  }
}

const saveReviewForAttempt = async attempt => {
  if (!detailRow.value?.submission_id) {
    return
  }
  const score = validateReviewScore(attempt.review_score_input)
  if (score === null) {
    return
  }
  attempt.saving_review = true
  try {
    await api.homework.reviewSubmission(homeworkId.value, detailRow.value.submission_id, {
      attempt_id: attempt.id,
      review_score: score,
      review_comment: attempt.review_comment_input?.trim() || null
    })
    ElMessage.success('评分已保存')
    await loadPage()
  } finally {
    attempt.saving_review = false
  }
}

const regradeLatest = async () => {
  if (!detailRow.value?.submission_id) {
    return
  }
  detailRow.value.regrading = true
  try {
    await api.homework.regradeSubmission(homeworkId.value, detailRow.value.submission_id, {
      attempt_id: null
    })
    ElMessage.success('已加入重评队列')
    await loadPage()
  } finally {
    if (detailRow.value) {
      detailRow.value.regrading = false
    }
  }
}

const regradeAttempt = async attempt => {
  if (!detailRow.value?.submission_id) {
    return
  }
  attempt.regrading = true
  try {
    await api.homework.regradeSubmission(homeworkId.value, detailRow.value.submission_id, {
      attempt_id: attempt.id
    })
    ElMessage.success('已加入重评队列')
    await loadPage()
  } finally {
    attempt.regrading = false
  }
}

const acknowledgeAppeal = async () => {
  if (!detailRow.value?.submission_id) {
    return
  }
  detailAckLoading.value = true
  try {
    await api.homework.acknowledgeAppeal(homeworkId.value, detailRow.value.submission_id)
    ElMessage.success('已标记已阅')
    await loadPage()
  } finally {
    detailAckLoading.value = false
  }
}

const resetAppealResolveDialog = () => {
  appealResolveResponse.value = ''
  appealResolveLoading.value = false
}

const openAppealResolveDialog = () => {
  appealResolveResponse.value = detailRow.value?.appeal_teacher_response || ''
  appealResolveDialogVisible.value = true
}

const submitAppealResolution = async status => {
  if (!detailRow.value?.submission_id) {
    return
  }
  const response = appealResolveResponse.value.trim()
  if (!response) {
    ElMessage.warning('请填写教师回复')
    return
  }
  appealResolveLoading.value = true
  try {
    await api.homework.respondAppeal(homeworkId.value, detailRow.value.submission_id, {
      teacher_response: response,
      status
    })
    ElMessage.success(status === 'rejected' ? '申诉已拒绝' : '申诉已处理')
    appealResolveDialogVisible.value = false
    await loadPage()
  } catch (e) {
    if (e?.response?.status === 409) {
      appealResolveDialogVisible.value = false
      await loadPage()
      return
    }
    throw e
  } finally {
    appealResolveLoading.value = false
  }
}

const openTaskLog = (row, attempt = null) => {
  const log = attempt?.task_log || row?.latest_task_log
  logDialogTitle.value = attempt
    ? `LLM 日志 · ${row?.student_name || ''} · 提交 #${attempt.id}`
    : `LLM 日志 · ${row?.student_name || ''}`
  logDialogBody.value = JSON.stringify(log || [], null, 2)
  logDialogVisible.value = true
}

const isHistoryAttemptExpanded = attemptId => expandedHistoryAttemptIds.value.has(String(attemptId))

const toggleHistoryAttempt = attemptId => {
  const key = String(attemptId)
  const next = new Set(expandedHistoryAttemptIds.value)
  if (next.has(key)) {
    next.delete(key)
  } else {
    next.add(key)
  }
  expandedHistoryAttemptIds.value = next
}

const openAttachment = async (url, attachmentName) => {
  if (!url) {
    return
  }
  await downloadAttachment(url, attachmentName)
}

const formatDate = value => {
  if (!value) {
    return '未设置'
  }
  return new Date(value).toLocaleString('zh-CN')
}

onMounted(loadPage)

watch(
  () => [route.params.id, route.params.submissionId],
  () => {
    loadPage()
  }
)
</script>

<style scoped>
.submission-review-page {
  max-width: 920px;
  margin: 0 auto;
  padding: 24px 20px 48px;
}

.review-header {
  margin-bottom: 24px;
}

.review-header__left {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 16px;
}

.review-header__titles {
  min-width: 0;
}

.review-title {
  margin: 0 0 6px;
  font-size: 1.65rem;
  font-weight: 700;
  color: #0f172a;
}

.review-subtitle {
  margin: 0;
  font-size: 14px;
  color: #64748b;
}

.review-section {
  margin-bottom: 22px;
  padding: 22px 24px;
  border-radius: var(--wa-radius-lg, 16px);
  background: #fff;
  border: 1px solid #e2e8f0;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
}

.review-section__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.review-section__title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 600;
  color: #0f172a;
}

.review-meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px 20px;
}

.review-meta-item {
  font-size: 14px;
  color: #334155;
}

.review-meta-label {
  display: block;
  font-size: 12px;
  color: #64748b;
  margin-bottom: 4px;
}

.review-meta-action {
  margin-left: 8px;
}

.review-meta-actions {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.review-appeal-card {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  background: #f8fafc;
}

.review-appeal-card--dialog {
  margin-top: 0;
  margin-bottom: 12px;
}

.review-appeal-text {
  margin: 6px 0 0;
  white-space: pre-wrap;
  color: #334155;
  line-height: 1.6;
}

.review-appeal-dialog {
  display: grid;
  gap: 12px;
}

.review-effective-note {
  margin: 12px 0 0;
  font-size: 13px;
  color: #64748b;
}

.muted {
  color: #64748b;
}

.small-label {
  font-size: 12px;
  margin-bottom: 4px;
}

.review-answer-card {
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  padding: 18px 20px;
}

.review-body-markdown {
  font-size: 15px;
  line-height: 1.65;
}

.review-body-markdown :deep(.markdown-body) {
  font-size: 15px;
}

.review-attach {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px dashed #cbd5e1;
}

.review-comment-card {
  padding: 16px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.review-hint {
  margin: 0 0 14px;
  font-size: 13px;
}

.detail-review-block {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.review-input-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.review-input-label {
  flex-shrink: 0;
  font-size: 14px;
  color: #475569;
}

.review-score-input {
  max-width: 140px;
}

.review-comment-input {
  width: 100%;
}

.feedback-inline {
  margin-top: 0;
}

:deep(.el-collapse-item__header) {
  font-weight: 600;
  font-size: 15px;
}

.attempt-card {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 14px;
  background: #fff;
}

.attempt-summary {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 10px;
  align-items: flex-start;
}

.attempt-toggle {
  width: 26px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 1px solid #bfdbfe;
  border-radius: 6px;
  color: #2563eb;
  background: rgba(239, 246, 255, 0.82);
  cursor: pointer;
}

.attempt-summary__main {
  min-width: 0;
}

.attempt-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.attempt-summary__preview {
  margin-top: 8px;
  color: #64748b;
  font-size: 13px;
  line-height: 1.55;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.attempt-body {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.attempt-feedback {
  margin-top: 8px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  background: #fafbfc;
}

.attempt-error {
  color: #dc2626;
  font-size: 13px;
}

.attempt-actions {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.llm-log-pre {
  max-height: 420px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 640px) {
  .review-input-row {
    flex-direction: column;
    align-items: stretch;
  }

  .review-score-input {
    max-width: none;
  }
}
</style>
