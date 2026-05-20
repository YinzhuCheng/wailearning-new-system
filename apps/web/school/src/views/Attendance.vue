<template>
  <div class="attendance-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">考勤管理</h1>
        <p class="page-subtitle">
          {{
            selectedCourse
              ? `${selectedCourse.name} · ${selectedCourse.class_name || '未分配班级'}`
              : '请先选择一门课程后再进行考勤记录。'
          }}
        </p>
      </div>
      <el-button plain @click="router.push('/students')">
        返回学生管理
      </el-button>
    </div>

    <el-empty v-if="!selectedCourse" description="请先选择一门课程。" />

    <template v-else>
      <el-card shadow="never" class="control-card">
        <div class="attendance-calendar-panel">
          <TeachingCalendar
            :course="selectedCourse"
            :selected-date="sessionForm.date"
            @select-date="handleCalendarDateSelect"
          />
        </div>

        <div class="control-bar">
          <div class="control-form">
            <span class="control-label">记录为</span>
            <el-date-picker
              v-model="sessionForm.date"
              type="date"
              format="YYYYMMDD"
              value-format="YYYY-MM-DD"
              :clearable="false"
              class="date-picker"
            />
            <span class="control-label">第</span>
            <el-input-number
              v-model="sessionForm.sessionIndex"
              :min="1"
              :max="99"
              :controls="false"
              class="session-input"
            />
            <span class="control-label">次出勤</span>
          </div>

          <div class="control-actions">
            <el-input
              v-model="studentKeyword"
              clearable
              placeholder="搜索学号 / 姓名"
              class="student-search"
            />
            <el-button type="primary" :loading="saving" @click="submitAttendanceSheet">提交</el-button>
            <el-button plain type="primary" @click="handleGenerateQr">生成现场考勤二维码</el-button>
          </div>
        </div>

        <div class="control-summary">
          <span class="summary-chip">当前记录 {{ currentSessionLabel }}</span>
          <span class="summary-chip">学生人数 {{ normalizedStudents.length }}</span>
          <span class="summary-chip">显示最近 {{ visibleHistorySessions.length }} 次历史考勤</span>
        </div>
      </el-card>

      <el-card shadow="never" class="sheet-card">
        <template #header>
          <div class="sheet-header">
            <div class="sheet-header-left">
              <span class="sheet-title">出勤记录区</span>
              <el-button link type="primary" @click="refreshHistory">载入历史记录</el-button>
            </div>
            <div class="sheet-legend">
              <span v-for="item in STATUS_OPTIONS" :key="item.value" class="legend-item">
                <span class="status-dot" :class="`status-${item.value}`"></span>
                {{ item.legendLabel }}
              </span>
            </div>
          </div>
        </template>

        <div v-loading="loading" class="sheet-body">
          <el-empty
            v-if="!normalizedStudents.length"
            description="当前课程还没有学生。"
            class="sheet-empty"
          />

          <el-empty
            v-else-if="!filteredStudents.length"
            description="没有匹配到学生。"
            class="sheet-empty"
          />

          <DualHorizontalScroll v-else target-selector=".sheet-scroll">
            <div class="sheet-scroll dual-scroll-target">
              <div class="attendance-grid">
                <div class="attendance-grid-header">
                  <div>新的出勤记录</div>
                  <div>学号</div>
                  <div>姓名</div>
                  <div>班级</div>
                  <div>历次出勤记录：{{ historyRangeText }}</div>
                </div>

              <div
                v-for="student in filteredStudents"
                :key="student.student_id"
                class="attendance-grid-row"
              >
                <div class="record-cell">
                  <el-radio-group
                    :model-value="attendanceDrafts[student.student_id]"
                    class="record-radio-group"
                    @update:model-value="value => updateDraft(student.student_id, value)"
                  >
                    <el-radio
                      v-for="item in STATUS_OPTIONS"
                      :key="item.value"
                      :label="item.value"
                      class="record-radio"
                    >
                      {{ item.label }}
                    </el-radio>
                  </el-radio-group>
                </div>

                <div class="student-no">{{ student.student_no || '暂无学号' }}</div>

                <div class="student-name-cell">
                  <el-avatar :size="38" :style="{ backgroundColor: getAvatarColor(student.student_name) }">
                    {{ student.student_name?.charAt(0) || '学' }}
                  </el-avatar>
                  <span class="student-name-text">{{ student.student_name }}</span>
                </div>

                <div class="student-class">{{ student.class_name }}</div>

                <div class="history-cell">
                  <div v-if="visibleHistorySessions.length" class="history-dots">
                    <el-tooltip
                      v-for="dot in buildHistoryDots(student.student_id)"
                      :key="dot.sessionKey"
                      :content="dot.tooltip"
                      placement="top"
                    >
                      <span class="history-dot" :class="`status-${dot.status}`"></span>
                    </el-tooltip>
                  </div>
                  <span v-else class="history-empty">暂无历史记录</span>
                </div>
              </div>
            </div>
            </div>
          </DualHorizontalScroll>
        </div>
      </el-card>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import api from '@/api'
import DualHorizontalScroll from '@/components/DualHorizontalScroll.vue'
import TeachingCalendar from '@/components/TeachingCalendar.vue'
import { useUserStore } from '@/stores/user'

const STATUS_OPTIONS = [
  { value: 'present', label: '出勤', legendLabel: '出勤' },
  { value: 'leave', label: '请假', legendLabel: '请假' },
  { value: 'late', label: '迟到早退', legendLabel: '迟到早退' },
  { value: 'absent', label: '缺勤', legendLabel: '缺勤' },
  { value: 'unknown', label: '未知', legendLabel: '未知' }
]

const SESSION_REMARK_PATTERN = /^\[session=(\d+)\]\s*/i
const AVATAR_COLORS = ['#2563eb', '#0f766e', '#ea580c', '#7c3aed', '#ca8a04', '#0f766e', '#be123c']

const userStore = useUserStore()
const router = useRouter()

const loading = ref(false)
const saving = ref(false)
const students = ref([])
const attendances = ref([])
const attendanceDrafts = ref({})
const studentKeyword = ref('')

const sessionForm = reactive({
  date: formatDateInput(new Date()),
  sessionIndex: 1
})

const selectedCourse = computed(() => userStore.selectedCourse)

const normalizedStudents = computed(() =>
  students.value
    .map(item => ({
      student_id: item.student_id ?? item.id,
      student_name: item.student_name ?? item.name ?? '未命名学生',
      student_no: item.student_no ?? '',
      class_name: item.class_name || selectedCourse.value?.class_name || '未分配班级'
    }))
    .filter(item => item.student_id)
)

const filteredStudents = computed(() => {
  const keyword = studentKeyword.value.trim().toLowerCase()
  if (!keyword) {
    return normalizedStudents.value
  }

  return normalizedStudents.value.filter(student =>
    [student.student_name, student.student_no, student.class_name]
      .filter(Boolean)
      .some(value => `${value}`.toLowerCase().includes(keyword))
  )
})

const normalizedAttendances = computed(() => {
  const records = attendances.value
    .map(item => {
      const date = toValidDate(item.date)
      const dateKey = formatDateInput(date)
      if (!dateKey) {
        return null
      }

      return {
        ...item,
        date,
        dateKey,
        timeKey: formatTimeKey(date),
        parsedSessionIndex: extractSessionIndex(item.remark),
        cleanRemark: stripSessionRemark(item.remark)
      }
    })
    .filter(Boolean)

  const sessionKeyMap = new Map()

  const recordsByDate = new Map()
  records.forEach(record => {
    if (!recordsByDate.has(record.dateKey)) {
      recordsByDate.set(record.dateKey, [])
    }
    recordsByDate.get(record.dateKey).push(record)
  })

  recordsByDate.forEach((items, dateKey) => {
    const slotMap = new Map()

    items.forEach(record => {
      const slotIdentity = record.parsedSessionIndex
        ? `session:${record.parsedSessionIndex}`
        : `time:${record.timeKey}`

      if (!slotMap.has(slotIdentity)) {
        slotMap.set(slotIdentity, {
          slotIdentity,
          parsedSessionIndex: record.parsedSessionIndex,
          timestamp: record.date.getTime()
        })
      }
    })

    const usedIndexes = new Set()

    Array.from(slotMap.values())
      .filter(slot => slot.parsedSessionIndex)
      .sort((left, right) => left.parsedSessionIndex - right.parsedSessionIndex)
      .forEach(slot => {
        sessionKeyMap.set(`${dateKey}__${slot.slotIdentity}`, slot.parsedSessionIndex)
        usedIndexes.add(slot.parsedSessionIndex)
      })

    let nextIndex = 1
    Array.from(slotMap.values())
      .filter(slot => !slot.parsedSessionIndex)
      .sort((left, right) => left.timestamp - right.timestamp)
      .forEach(slot => {
        while (usedIndexes.has(nextIndex)) {
          nextIndex += 1
        }
        sessionKeyMap.set(`${dateKey}__${slot.slotIdentity}`, nextIndex)
        usedIndexes.add(nextIndex)
      })
  })

  return records.map(record => {
    const slotIdentity = record.parsedSessionIndex ? `session:${record.parsedSessionIndex}` : `time:${record.timeKey}`
    const sessionIndex = sessionKeyMap.get(`${record.dateKey}__${slotIdentity}`) || 1

    return {
      ...record,
      sessionIndex,
      sessionKey: `${record.dateKey}#${sessionIndex}`
    }
  })
})

const historySessions = computed(() => {
  const sessionMap = new Map()

  normalizedAttendances.value.forEach(record => {
    if (!sessionMap.has(record.sessionKey)) {
      sessionMap.set(record.sessionKey, {
        sessionKey: record.sessionKey,
        dateKey: record.dateKey,
        sessionIndex: record.sessionIndex,
        compactLabel: `${record.dateKey.replaceAll('-', '')}-${record.sessionIndex}`
      })
    }
  })

  return Array.from(sessionMap.values()).sort((left, right) => {
    if (left.dateKey === right.dateKey) {
      return left.sessionIndex - right.sessionIndex
    }
    return left.dateKey.localeCompare(right.dateKey)
  })
})

const currentSessionKey = computed(() => `${sessionForm.date}#${Number(sessionForm.sessionIndex || 1)}`)

const currentSessionLabel = computed(() => `${sessionForm.date.replaceAll('-', '')}-${Number(sessionForm.sessionIndex || 1)}`)

const visibleHistorySessions = computed(() =>
  historySessions.value.filter(item => item.sessionKey !== currentSessionKey.value).slice(-8)
)

const historyRangeText = computed(() => {
  if (!visibleHistorySessions.value.length) {
    return '暂无历史记录'
  }

  const first = visibleHistorySessions.value[0]
  const last = visibleHistorySessions.value[visibleHistorySessions.value.length - 1]
  return `${first.compactLabel} 至 ${last.compactLabel}`
})

const attendanceHistoryByStudent = computed(() => {
  const historyMap = new Map()

  normalizedAttendances.value.forEach(record => {
    if (!historyMap.has(record.student_id)) {
      historyMap.set(record.student_id, new Map())
    }
    historyMap.get(record.student_id).set(record.sessionKey, record)
  })

  return historyMap
})

const currentSessionRecordMap = computed(() => {
  const result = new Map()

  normalizedAttendances.value.forEach(record => {
    if (record.sessionKey === currentSessionKey.value && !result.has(record.student_id)) {
      result.set(record.student_id, record)
    }
  })

  return result
})

const loadStudents = async () => {
  if (!selectedCourse.value) {
    students.value = []
    return
  }

  students.value = await api.courses.getStudents(selectedCourse.value.id)
}

const loadAttendances = async () => {
  if (!selectedCourse.value) {
    attendances.value = []
    return
  }

  loading.value = true
  try {
    const result = await api.attendance.list({
      class_id: selectedCourse.value.class_id,
      subject_id: selectedCourse.value.id,
      page: 1,
      page_size: 1000
    })
    attendances.value = result?.data || []
  } finally {
    loading.value = false
  }
}

const syncDraftsToCurrentSession = () => {
  const nextDrafts = {}

  normalizedStudents.value.forEach(student => {
    const existing = currentSessionRecordMap.value.get(student.student_id)
    nextDrafts[student.student_id] = existing?.status || 'present'
  })

  attendanceDrafts.value = nextDrafts
}

const loadPageData = async () => {
  if (!selectedCourse.value) {
    students.value = []
    attendances.value = []
    attendanceDrafts.value = {}
    return
  }

  await Promise.all([loadStudents(), loadAttendances()])
  syncDraftsToCurrentSession()
}

const refreshHistory = async () => {
  await loadAttendances()
  syncDraftsToCurrentSession()
  ElMessage.success('历史考勤已刷新')
}

const handleCalendarDateSelect = async dateKey => {
  if (!dateKey) return
  sessionForm.date = dateKey
  sessionForm.sessionIndex = 1
  await loadAttendances()
  syncDraftsToCurrentSession()
  ElMessage.success('已切换到日历所选课程日，可查看或调整当日考勤')
}

const updateDraft = (studentId, value) => {
  attendanceDrafts.value = {
    ...attendanceDrafts.value,
    [studentId]: value
  }
}

const buildHistoryDots = studentId => {
  const studentHistory = attendanceHistoryByStudent.value.get(studentId) || new Map()

  return visibleHistorySessions.value.map(session => {
    const record = studentHistory.get(session.sessionKey)
    const status = record?.status || 'unknown'
    const remarkText = record?.cleanRemark ? `，${record.cleanRemark}` : ''

    return {
      sessionKey: session.sessionKey,
      status,
      tooltip: `${session.compactLabel} · ${statusLabel(status)}${remarkText}`
    }
  })
}

const submitAttendanceSheet = async () => {
  if (!selectedCourse.value || !normalizedStudents.value.length) {
    return
  }

  const creates = []
  const updates = []
  const deletes = []

  normalizedStudents.value.forEach(student => {
    const existing = currentSessionRecordMap.value.get(student.student_id)
    const draftStatus = attendanceDrafts.value[student.student_id] || 'present'

    if (draftStatus === 'unknown') {
      if (existing) {
        deletes.push(existing)
      }
      return
    }

    const nextRemark = buildSessionRemark(sessionForm.sessionIndex, existing?.remark)
    if (existing) {
      if (existing.status !== draftStatus || `${existing.remark || ''}` !== nextRemark) {
        updates.push({
          id: existing.id,
          status: draftStatus,
          remark: nextRemark
        })
      }
      return
    }

    creates.push({
      student_no: student.student_no,
      class_id: selectedCourse.value.class_id,
      subject_id: selectedCourse.value.id,
      date: buildSessionDateTime(sessionForm.date, sessionForm.sessionIndex),
      status: draftStatus,
      remark: nextRemark
    })
  })

  if (!creates.length && !updates.length && !deletes.length) {
    ElMessage.info('当前考勤没有变化')
    return
  }

  saving.value = true
  try {
    let createSuccess = 0
    let createFailed = 0

    if (creates.length) {
      const createResult = await api.attendance.batchCreate({
        attendances: creates
      })
      createSuccess = Number(createResult?.success || 0)
      createFailed = Number(createResult?.failed || 0)
    }

    const updateResults = await Promise.allSettled(
      updates.map(item =>
        api.attendance.update(item.id, {
          status: item.status,
          remark: item.remark
        })
      )
    )

    const deleteResults = await Promise.allSettled(
      deletes.map(item => api.attendance.delete(item.id))
    )

    const updateFailed = updateResults.filter(item => item.status === 'rejected').length
    const deleteFailed = deleteResults.filter(item => item.status === 'rejected').length

    const successCount =
      createSuccess +
      updateResults.filter(item => item.status === 'fulfilled').length +
      deleteResults.filter(item => item.status === 'fulfilled').length

    const failedCount = createFailed + updateFailed + deleteFailed

    await loadAttendances()
    syncDraftsToCurrentSession()

    if (failedCount) {
      ElMessage.warning(`考勤提交完成，成功 ${successCount} 条，失败 ${failedCount} 条`)
      return
    }

    ElMessage.success(`考勤已提交，共处理 ${successCount} 条记录`)
  } finally {
    saving.value = false
  }
}

const handleGenerateQr = () => {
  ElMessage.info('现场考勤二维码功能将在后续版本接入')
}

const getAvatarColor = name => {
  const text = `${name || ''}`
  const total = Array.from(text).reduce((sum, char) => sum + char.charCodeAt(0), 0)
  return AVATAR_COLORS[total % AVATAR_COLORS.length]
}

function statusLabel(status) {
  return (
    {
      present: '出勤',
      leave: '请假',
      late: '迟到早退',
      absent: '缺勤',
      unknown: '未知'
    }[status] || status
  )
}

function extractSessionIndex(remark) {
  const match = `${remark || ''}`.match(SESSION_REMARK_PATTERN)
  if (!match) {
    return null
  }

  const value = Number(match[1])
  return Number.isFinite(value) && value > 0 ? value : null
}

function stripSessionRemark(remark) {
  return `${remark || ''}`.replace(SESSION_REMARK_PATTERN, '').trim()
}

function buildSessionRemark(sessionIndex, remark) {
  const cleanRemark = stripSessionRemark(remark)
  return cleanRemark ? `[session=${sessionIndex}] ${cleanRemark}` : `[session=${sessionIndex}]`
}

function buildSessionDateTime(dateInput, sessionIndex) {
  const [year, month, day] = `${dateInput}`.split('-').map(Number)
  const totalMinutes = Math.max(0, Number(sessionIndex || 1) - 1)
  const hours = `${Math.floor(totalMinutes / 60)}`.padStart(2, '0')
  const minutes = `${totalMinutes % 60}`.padStart(2, '0')

  return `${year}-${`${month}`.padStart(2, '0')}-${`${day}`.padStart(2, '0')}T${hours}:${minutes}:00`
}

function toValidDate(value) {
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

function formatDateInput(value) {
  const date = toValidDate(value)
  if (!date) {
    return ''
  }

  const year = date.getFullYear()
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  const day = `${date.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

function formatTimeKey(date) {
  return [
    `${date.getHours()}`.padStart(2, '0'),
    `${date.getMinutes()}`.padStart(2, '0'),
    `${date.getSeconds()}`.padStart(2, '0')
  ].join(':')
}

onMounted(loadPageData)

watch(selectedCourse, async () => {
  sessionForm.date = formatDateInput(new Date())
  sessionForm.sessionIndex = 1
  studentKeyword.value = ''
  await loadPageData()
})

watch(
  () => `${sessionForm.date}-${sessionForm.sessionIndex}`,
  () => {
    syncDraftsToCurrentSession()
  }
)
</script>

<style scoped>
.attendance-page {
  padding: 24px;
  display: grid;
  gap: 20px;
  min-width: 0;
  overflow-x: hidden;
}

.attendance-page :deep(.el-card) {
  min-width: 0;
}

.attendance-page :deep(.el-card__body) {
  overflow-x: auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
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

.control-card :deep(.el-card__body) {
  display: grid;
  gap: 16px;
}

.attendance-calendar-panel {
  min-width: 0;
  border: 1px solid #dbe4f0;
  border-radius: var(--wa-radius-lg, 12px);
  padding: 14px;
  background: #f8fafc;
}

.control-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.control-form,
.control-actions,
.control-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.control-label {
  color: #0f172a;
  font-weight: 600;
}

.date-picker {
  width: 170px;
}

.session-input {
  width: 58px;
}

.student-search {
  width: 220px;
}

.summary-chip {
  display: inline-flex;
  align-items: center;
  padding: 8px 12px;
  border-radius: 999px;
  border: 1px solid #dbeafe;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 13px;
}

.sheet-card :deep(.el-card__header) {
  padding-bottom: 14px;
}

.sheet-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.sheet-header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.sheet-title {
  color: #2563eb;
  font-size: 20px;
  font-weight: 700;
}

.sheet-legend {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  color: #475569;
  font-size: 13px;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.status-dot,
.history-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  display: inline-block;
  flex-shrink: 0;
}

.sheet-body {
  min-height: 220px;
  min-width: 0;
}

.sheet-scroll {
  overflow-x: auto;
  max-width: 100%;
}

.attendance-grid {
  min-width: 1160px;
}

.attendance-grid-header,
.attendance-grid-row {
  display: grid;
  grid-template-columns: minmax(300px, 2.3fr) minmax(120px, 1fr) minmax(140px, 1fr) minmax(120px, 1fr) minmax(280px, 1.8fr);
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
}

.attendance-grid-header {
  background: #f8fafc;
  color: #0f172a;
  font-weight: 700;
  border-top: 1px solid #e2e8f0;
  border-bottom: 1px solid #e2e8f0;
}

.attendance-grid-row {
  border-bottom: 1px solid #e2e8f0;
  color: #334155;
}

.attendance-grid-row:hover {
  background: #f8fbff;
}

.record-cell {
  min-width: 0;
}

.record-radio-group {
  display: flex;
  align-items: center;
  gap: 10px 12px;
  flex-wrap: wrap;
}

.record-radio {
  margin-right: 0;
}

.record-radio-group :deep(.el-radio__label) {
  padding-left: 4px;
  color: #1e293b;
}

.student-no,
.student-class {
  color: #1e293b;
  font-size: 14px;
}

.student-name-cell {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.student-name-text {
  font-weight: 600;
  color: #0f172a;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-cell {
  min-width: 0;
}

.history-dots {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.history-empty {
  color: #94a3b8;
}

.status-present {
  background: #65c91f;
}

.status-leave {
  background: #38bdf8;
}

.status-late {
  background: #f59e0b;
}

.status-absent {
  background: #ef4444;
}

.status-unknown {
  background: #d1d5db;
}

.sheet-empty {
  padding: 32px 0;
}

@media (max-width: 900px) {
  .attendance-page {
    padding: 18px 14px;
  }

  .page-header {
    flex-direction: column;
  }
}
</style>
