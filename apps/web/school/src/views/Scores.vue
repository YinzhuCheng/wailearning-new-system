<template>
  <div class="scores-page">
    <div class="page-header">
      <el-button class="back-button" plain @click="router.push('/students')">
        返回学生管理
      </el-button>
      <div>
        <h1 class="page-title">成绩管理</h1>
        <p class="page-subtitle">
          {{
            selectedCourse
              ? `${selectedCourse.name} · ${selectedCourse.class_name || '未分配班级'}`
              : '请先选择课程后查看成绩。'
          }}
        </p>
      </div>
      <div class="header-actions">
        <el-button v-if="selectedCourse" @click="openSchemeDialog">平时分占比</el-button>
        <el-button v-if="selectedCourse" @click="openWeightDialog">各次考试占比</el-button>
        <el-button v-if="selectedCourse" :loading="compositionLoading" @click="loadClassCompositions">
          刷新成绩构成
        </el-button>
        <el-button v-if="selectedCourse" type="primary" @click="openCreateDialog">录入成绩</el-button>
      </div>
    </div>

    <el-alert
      v-if="missingAppealCourseNotice"
      data-testid="scores-appeal-course-missing"
      type="warning"
      :closable="false"
      class="appeal-missing-course-alert"
      :title="missingAppealCourseNotice.title"
      :description="missingAppealCourseNotice.description"
    />
    <div v-if="missingAppealCourseNotice && selectedCourseRaw" class="appeal-missing-course-actions">
      <el-button
        data-testid="scores-appeal-use-current-course"
        size="small"
        type="primary"
        plain
        @click="recoverWithCurrentCourse"
      >
        继续使用当前课程
      </el-button>
    </div>

    <el-alert
      v-if="missingAppealTargetNotice"
      data-testid="scores-appeal-target-missing"
      type="info"
      :closable="false"
      class="appeal-target-missing-alert"
      :title="missingAppealTargetNotice.title"
      :description="missingAppealTargetNotice.description"
    />

    <el-empty v-if="!selectedCourse" :description="emptyStateDescription" />

    <template v-else>
      <el-card shadow="never" class="stats-card">
        <el-row :gutter="20">
          <el-col :span="6">
            <el-statistic title="成绩记录" :value="scores.length" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="平均分" :value="averageScore" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="最高分" :value="maxScore" />
          </el-col>
          <el-col :span="6">
            <el-statistic title="及格率" :value="passRate" suffix="%" />
          </el-col>
        </el-row>
      </el-card>

      <el-card shadow="never" class="weights-card">
        <template #header>
          <div class="card-header-inline">
            <strong>成绩构成说明</strong>
            <span class="weight-total">三部分之和须为 100%</span>
          </div>
        </template>
        <p class="scheme-hint">
          作业平时分由系统根据各次作业批改得分折算；「{{ OTHER_DAILY }}」与各次考试成绩由教师在本页录入；加权总成绩 =
          作业均分×作业占比 + 其他平时分×其占比 + 各次考试×对应占比。
        </p>
        <div class="scheme-tags">
          <el-tag type="success" size="large">作业平时分 {{ gradeScheme.homework_weight }}%</el-tag>
          <el-tag type="warning" size="large">{{ OTHER_DAILY }} {{ gradeScheme.extra_daily_weight }}%</el-tag>
          <el-tag v-for="item in examWeights" :key="item.exam_type" type="info" size="large">
            {{ item.exam_type }} {{ Number(item.weight).toFixed(0) }}%
          </el-tag>
        </div>
        <p class="scheme-sum" :class="{ invalid: !partsSumValid }">
          当前合计：作业 {{ gradeScheme.homework_weight }}% + 其他平时 {{ gradeScheme.extra_daily_weight }}% + 考试
          {{ totalExamWeight }}% = {{ partsSum }}%
          <template v-if="!partsSumValid">（须等于 100% 才能计算总成绩）</template>
        </p>
      </el-card>

      <el-card shadow="never" class="totals-card">
        <template #header>
          <div class="card-header-inline">
            <strong>学生成绩构成（加权总成绩）</strong>
            <div class="toolbar-inline">
              <el-select
                v-model="compositionSemester"
                placeholder="学期"
                style="width: 200px"
                @change="loadClassCompositions"
              >
                <el-option v-for="item in semesters" :key="item.id" :label="item.name" :value="item.name" />
              </el-select>
            </div>
          </div>
        </template>
        <DualHorizontalScroll target-selector=".scores-composition-scroll">
          <div class="scores-composition-scroll dual-scroll-target">
            <el-table
              v-loading="compositionLoading"
              :data="classCompositions"
              empty-text="请选择学期并点击「刷新成绩构成」。"
            >
          <el-table-column prop="student_name" label="学生" min-width="120" />
          <el-table-column prop="student_no" label="学号" width="120" />
          <el-table-column label="作业平时(折算%)" width="130">
            <template #default="{ row }">{{ row.homework_average_percent ?? '—' }}</template>
          </el-table-column>
          <el-table-column :label="OTHER_DAILY" width="100">
            <template #default="{ row }">{{ row.other_daily_score ?? '—' }}</template>
          </el-table-column>
          <el-table-column
            v-for="w in examWeights"
            :key="w.exam_type"
            :label="w.exam_type"
            width="100"
          >
            <template #default="{ row }">{{ row.exam_scores?.[w.exam_type] ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="总成绩" width="110">
            <template #default="{ row }">
              <el-tag v-if="row.weighted_total != null" :type="scoreTag(row.weighted_total)">
                {{ row.weighted_total }}
              </el-tag>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column prop="missing_for_total" label="缺项" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">
              {{ (row.missing_for_total || []).length ? row.missing_for_total.join('、') : '—' }}
            </template>
          </el-table-column>
            </el-table>
          </div>
        </DualHorizontalScroll>
      </el-card>

      <el-card shadow="never" class="appeals-card">
        <template #header>
          <div class="card-header-inline">
            <strong>成绩申诉</strong>
            <el-button size="small" @click="refreshAppeals">刷新</el-button>
          </div>
        </template>
        <el-alert
          v-if="focusedAppealStatus && isTerminalAppealStatus(focusedAppealStatus)"
          type="info"
          :closable="false"
          class="appeal-focus-banner"
          :title="appealFocusBannerTitle"
        />
        <el-table :data="appeals" empty-text="暂无申诉">
          <el-table-column prop="id" label="编号" width="70">
            <template #default="{ row }">
              <span
                :data-testid="`score-appeal-row-${row.id}`"
                :class="{ 'appeal-row-focus': Number(route.query.appeal_id || 0) === Number(row.id) }"
              >
                {{ row.id }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="student_name" label="学生" width="100" />
          <el-table-column prop="semester" label="学期" width="120" />
          <el-table-column label="申诉对象" min-width="160">
            <template #default="{ row }">
              {{ formatAppealTarget(row) }}
            </template>
          </el-table-column>
          <el-table-column prop="reason_text" label="理由" min-width="160" show-overflow-tooltip />
          <el-table-column prop="status" label="状态" width="100" />
          <el-table-column prop="teacher_response" label="教师回复" min-width="180" show-overflow-tooltip />
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button
                v-if="isActionableAppealStatus(row.status)"
                type="primary"
                link
                @click="openAppealDialog(row)"
              >
                回复
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card shadow="never">
        <div class="toolbar">
          <el-select v-model="filterSemester" placeholder="选择学期" clearable style="width: 200px" @change="loadScores">
            <el-option v-for="item in semesters" :key="item.id" :label="item.name" :value="item.name" />
          </el-select>
        </div>

        <DualHorizontalScroll target-selector=".scores-list-scroll">
          <div class="scores-list-scroll dual-scroll-target">
            <el-table :data="scores" v-loading="loading">
          <el-table-column prop="student_name" label="学生" min-width="180" />
          <el-table-column prop="score" label="成绩" width="100">
            <template #default="{ row }">
              <el-tag :type="scoreTag(row.score)">{{ row.score }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="exam_type" label="类型" width="140" />
          <el-table-column prop="semester" label="学期" width="140" />
          <el-table-column prop="exam_date" label="考试时间" width="180">
            <template #default="{ row }">
              {{ formatDate(row.exam_date) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180">
            <template #default="{ row }">
              <el-button type="primary" size="small" @click="openEditDialog(row)">编辑</el-button>
              <el-button type="danger" size="small" @click="deleteScore(row)">删除</el-button>
            </template>
          </el-table-column>
            </el-table>
          </div>
        </DualHorizontalScroll>
      </el-card>
    </template>

    <el-dialog
      v-model="dialogVisible"
      :title="editingScore ? '编辑成绩' : batchEntryStep === 1 ? '录入成绩' : '批量录入成绩'"
      :width="editingScore ? '560px' : batchEntryStep === 1 ? '560px' : '760px'"
      destroy-on-close
    >
      <el-form
        v-if="editingScore || batchEntryStep === 1"
        ref="formRef"
        :model="form"
        :rules="editingScore ? rules : batchRules"
        label-width="90px"
      >
        <template v-if="editingScore">
          <el-form-item label="学生" prop="student_id">
            <el-select v-model="form.student_id" filterable style="width: 100%">
              <el-option
                v-for="item in students"
                :key="item.student_id"
                :label="`${item.student_name} (${item.student_no || '无学号'})`"
                :value="item.student_id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="成绩" prop="score">
            <el-input-number v-model="form.score" :min="0" :max="100" :step="0.5" />
          </el-form-item>
          <el-form-item label="类型" prop="exam_type">
            <el-input v-model="form.exam_type" placeholder="各次考试 或 其他平时分" />
          </el-form-item>
          <el-form-item label="考试时间" prop="exam_date">
            <el-date-picker v-model="form.exam_date" type="datetime" style="width: 100%" />
          </el-form-item>
          <el-form-item label="所属学期" prop="semester">
            <el-select v-model="form.semester" style="width: 100%">
              <el-option v-for="item in semesters" :key="item.id" :label="item.name" :value="item.name" />
            </el-select>
          </el-form-item>
        </template>

        <template v-else>
          <el-form-item label="类型" prop="exam_type">
            <el-input v-model="form.exam_type" placeholder="期中考试、期末考试 或 其他平时分" />
          </el-form-item>
          <el-form-item label="考试时间" prop="exam_date">
            <el-date-picker v-model="form.exam_date" type="datetime" style="width: 100%" clearable />
          </el-form-item>
        </template>
      </el-form>

      <div v-else class="batch-entry-panel">
        <div class="batch-entry-summary">
          <div class="summary-item">
            <strong>类型：</strong>{{ form.exam_type }}
          </div>
          <div class="summary-item">
            <strong>考试时间：</strong>{{ formatDate(form.exam_date) }}
          </div>
          <div class="summary-item">
            <strong>课程：</strong>{{ selectedCourse?.name }}
          </div>
        </div>

        <el-alert
          title="输入一个成绩后按回车，会自动跳到下一个学生的成绩框。"
          type="info"
          :closable="false"
          class="batch-entry-alert"
        />

        <div class="batch-fill-tools">
          <el-input
            v-model="bulkScore"
            type="number"
            min="0"
            max="100"
            step="0.5"
            placeholder="输入统一分数"
            style="width: 180px"
          />
          <el-button @click="fillAllScores">一键录入</el-button>
        </div>

        <DualHorizontalScroll target-selector=".scores-batch-scroll">
          <div class="scores-batch-scroll dual-scroll-target">
            <el-table :data="batchStudents" max-height="420">
          <el-table-column prop="student_name" label="学生姓名" min-width="180" />
          <el-table-column prop="student_no" label="学号" width="180" />
          <el-table-column label="成绩" width="180">
            <template #default="{ row, $index }">
              <el-input
                :ref="element => setScoreInputRef(element, $index)"
                v-model="row.score"
                type="number"
                min="0"
                max="100"
                step="0.5"
                placeholder="请输入成绩"
                @keydown.enter.prevent="focusNextScoreInput($index)"
              />
            </template>
          </el-table-column>
            </el-table>
          </div>
        </DualHorizontalScroll>
      </div>

      <template #footer>
        <template v-if="editingScore">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="submitting" @click="submitForm">保存</el-button>
        </template>
        <template v-else-if="batchEntryStep === 1">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="goToBatchEntry">确认</el-button>
        </template>
        <template v-else>
          <el-button @click="batchEntryStep = 1">返回</el-button>
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="submitting" @click="submitBatchScores">提交成绩</el-button>
        </template>
      </template>
    </el-dialog>

    <el-dialog
      v-model="weightDialogVisible"
      title="各次考试占比（与作业、其他平时分之和为 100%）"
      width="640px"
      destroy-on-close
    >
      <el-alert
        type="info"
        :closable="false"
        class="mb-12"
        title="此处仅配置「各次考试」占比。作业平时分与其他平时分占比在「平时分占比」中设置。"
      />
      <div class="weight-dialog-tools">
        <el-button @click="addWeightRow">新增考试</el-button>
        <span class="weight-total">考试合计 {{ totalWeight }}%</span>
      </div>
      <DualHorizontalScroll target-selector=".scores-weight-scroll">
        <div class="scores-weight-scroll dual-scroll-target">
          <el-table :data="weightForm.items" empty-text="请新增考试并填写占比">
        <el-table-column label="考试名称" min-width="220">
          <template #default="{ row }">
            <el-input v-model="row.exam_type" placeholder="例如：期中考试" />
          </template>
        </el-table-column>
        <el-table-column label="占比(%)" width="160">
          <template #default="{ row }">
            <el-input-number v-model="row.weight" :min="0" :max="100" :precision="2" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ $index }">
            <el-button type="danger" size="small" @click="removeWeightRow($index)">删除</el-button>
          </template>
        </el-table-column>
          </el-table>
        </div>
      </DualHorizontalScroll>
      <template #footer>
        <el-button @click="weightDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingWeights" @click="saveWeights">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="schemeDialogVisible" title="平时分占比" width="480px" destroy-on-close>
      <el-form label-width="140px">
        <el-form-item label="作业平时分占比(%)">
          <el-input-number v-model="schemeForm.homework_weight" :min="0" :max="100" :precision="2" />
        </el-form-item>
        <el-form-item :label="`${OTHER_DAILY}占比(%)`">
          <el-input-number v-model="schemeForm.extra_daily_weight" :min="0" :max="100" :precision="2" />
        </el-form-item>
      </el-form>
      <p class="muted small">与下方「各次考试占比」之和须为 100%。</p>
      <template #footer>
        <el-button @click="schemeDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingScheme" @click="saveScheme">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="appealDialogVisible" title="回复成绩申诉" width="560px" destroy-on-close>
      <el-input v-model="appealResolve.response" type="textarea" :rows="5" placeholder="教师回复" />
      <template #footer>
        <el-button @click="appealDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="appealResolve.loading" @click="submitAppealResolve">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import api from '@/api'
import DualHorizontalScroll from '@/components/DualHorizontalScroll.vue'
import { useUserStore } from '@/stores/user'
import {
  getAppealStatusLabel,
  isActionableAppealStatus,
  isTerminalAppealStatus
} from '@/utils/appealNotificationActions'

const OTHER_DAILY = '其他平时分'

const userStore = useUserStore()
const router = useRouter()
const route = useRoute()

const loading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)
const weightDialogVisible = ref(false)
const schemeDialogVisible = ref(false)
const appealDialogVisible = ref(false)
const editingScore = ref(null)
const batchEntryStep = ref(1)
const formRef = ref(null)
const scoreInputRefs = ref([])
const savingWeights = ref(false)
const savingScheme = ref(false)
const bulkScore = ref('')

const scores = ref([])
const semesters = ref([])
const students = ref([])
const batchStudents = ref([])
const examWeights = ref([])
const filterSemester = ref('')
const gradeScheme = ref({ homework_weight: 30, extra_daily_weight: 20 })
const schemeForm = reactive({ homework_weight: 30, extra_daily_weight: 20 })
const compositionSemester = ref('')
const compositionLoading = ref(false)
const classCompositions = ref([])
const appeals = ref([])
const appealResolve = reactive({ appealId: null, response: '', loading: false })
const focusedAppealStatus = ref('')
const focusedAppealResponse = ref('')
const appealRouteState = ref(null)

const selectedCourseRaw = computed(() => userStore.selectedCourse)
const routeStateKind = computed(() => appealRouteState.value?.kind || null)
const routeStateBlockedSubjectId = computed(() => Number(appealRouteState.value?.subjectId || 0))
const routeStateSnapshotCourseId = computed(() => Number(appealRouteState.value?.selectedCourseSnapshotId || 0))
const hasRecoveredMissingAppealContext = computed(() => {
  if (routeStateKind.value !== 'missing-course') return false
  const selectedCourseId = Number(selectedCourseRaw.value?.id || 0)
  if (!selectedCourseId || selectedCourseId === routeStateBlockedSubjectId.value) {
    return false
  }
  if (!routeStateSnapshotCourseId.value) {
    return true
  }
  return selectedCourseId !== routeStateSnapshotCourseId.value
})
const selectedCourse = computed(() =>
  routeStateKind.value === 'missing-course' &&
  !appealRouteState.value?.recovered &&
  !hasRecoveredMissingAppealContext.value
    ? null
    : selectedCourseRaw.value
)

const form = reactive({
  student_id: null,
  score: 0,
  exam_type: '期中考试',
  exam_date: null,
  semester: ''
})

const weightForm = reactive({
  items: []
})

const rules = {
  student_id: [{ required: true, message: '请选择学生', trigger: 'change' }],
  score: [{ required: true, message: '请输入成绩', trigger: 'blur' }],
  semester: [{ required: true, message: '请选择学期', trigger: 'change' }]
}

const batchRules = {
  exam_type: [{ required: true, message: '请输入类型', trigger: 'blur' }]
}

const averageScore = computed(() => {
  if (!scores.value.length) return 0
  return Number(
    (scores.value.reduce((sum, item) => sum + Number(item.score || 0), 0) / scores.value.length).toFixed(1)
  )
})

const maxScore = computed(() =>
  scores.value.length ? Math.max(...scores.value.map(item => Number(item.score || 0))) : 0
)
const passRate = computed(() => {
  if (!scores.value.length) return 0
  const passed = scores.value.filter(item => Number(item.score || 0) >= 60).length
  return Number(((passed / scores.value.length) * 100).toFixed(1))
})

const totalWeight = computed(() =>
  Number(weightForm.items.reduce((sum, item) => sum + Number(item.weight || 0), 0).toFixed(2))
)

const totalExamWeight = computed(() =>
  examWeights.value.reduce((s, item) => s + Number(item.weight || 0), 0)
)

const partsSum = computed(() =>
  Number(
    (
      Number(gradeScheme.value.homework_weight || 0) +
      Number(gradeScheme.value.extra_daily_weight || 0) +
      totalExamWeight.value
    ).toFixed(2)
  )
)

const partsSumValid = computed(() => partsSum.value === 100)

const DEFAULT_EMPTY_STATE_DESCRIPTION = '请先选择一门课程。'

const missingAppealCourseNotice = computed(() => {
  const context = appealRouteState.value
  if (!context || context.kind !== 'missing-course' || context.recovered || hasRecoveredMissingAppealContext.value) {
    return null
  }
  const routeLabel = context.appealId ? `申诉 ID ${context.appealId}` : '该申诉深链'
  return {
    title: '无法恢复该申诉对应的课程上下文',
    description:
      `${routeLabel} 指向的课程已不在当前可用课程列表中，页面已停止自动定位，` +
      '以免误将其他课程的成绩申诉当作目标。'
  }
})

const missingAppealTargetNotice = computed(() => {
  const context = appealRouteState.value
  if (!context || context.kind !== 'missing-target') return null
  return {
    title: '未找到目标成绩申诉',
    description: `申诉 ID ${context.appealId} 不存在，或已不在当前课程范围内。页面保留在当前课程，但不会把普通列表误当作目标申诉。`
  }
})

const emptyStateDescription = computed(() =>
  missingAppealCourseNotice.value
    ? '请返回通知列表，或重新选择一门仍然可用的课程后再继续。'
    : DEFAULT_EMPTY_STATE_DESCRIPTION
)

const getAppealRouteKey = () => `${route.query.subject_id || ''}:${route.query.appeal_id || ''}`

const loadSemesters = async () => {
  semesters.value = await api.semesters.list()
  if (!form.semester && semesters.value.length) {
    form.semester = semesters.value[0].name
  }
  if (!compositionSemester.value && semesters.value.length) {
    compositionSemester.value = semesters.value[0].name
  }
}

const loadStudents = async () => {
  if (!selectedCourse.value) {
    students.value = []
    return
  }
  students.value = await api.courses.getStudents(selectedCourse.value.id)
}

const loadWeights = async () => {
  if (!selectedCourse.value) {
    examWeights.value = []
    weightForm.items = []
    return
  }

  examWeights.value = await api.scores.getWeights(selectedCourse.value.id)
  weightForm.items = examWeights.value.map(item => ({
    exam_type: item.exam_type,
    weight: Number(item.weight)
  }))
}

const loadGradeScheme = async () => {
  if (!selectedCourse.value) {
    gradeScheme.value = { homework_weight: 30, extra_daily_weight: 20 }
    return
  }
  const s = await api.scores.getGradeScheme(selectedCourse.value.id)
  gradeScheme.value = {
    homework_weight: Number(s.homework_weight),
    extra_daily_weight: Number(s.extra_daily_weight)
  }
}

const loadScores = async () => {
  if (!selectedCourse.value) {
    scores.value = []
    return
  }
  loading.value = true
  try {
    const result = await api.scores.list({
      class_id: selectedCourse.value.class_id,
      subject_id: selectedCourse.value.id,
      semester: filterSemester.value || undefined,
      page: 1,
      page_size: 500
    })
    scores.value = result?.data || []
  } finally {
    loading.value = false
  }
}

const loadClassCompositions = async () => {
  if (!selectedCourse.value || !compositionSemester.value) {
    classCompositions.value = []
    return
  }
  compositionLoading.value = true
  try {
    classCompositions.value = await api.scores.listClassComposition({
      subject_id: selectedCourse.value.id,
      semester: compositionSemester.value
    })
  } finally {
    compositionLoading.value = false
  }
}

const resetFocusedAppealState = () => {
  focusedAppealStatus.value = ''
  focusedAppealResponse.value = ''
}

const syncAppealRouteCourseContext = async () => {
  const routeSubjectId = Number(route.query.subject_id || 0)
  const appealId = Number(route.query.appeal_id || 0)
  const routeKey = getAppealRouteKey()

  if (!routeSubjectId) {
    appealRouteState.value = null
    return
  }

  const courses = await userStore.fetchTeachingCourses(true)
  const matchedCourse = courses.find(row => Number(row.id) === routeSubjectId)

  if (!matchedCourse) {
    const previousState = appealRouteState.value
    appealRouteState.value = {
      kind: 'missing-course',
      routeKey,
      subjectId: routeSubjectId,
      appealId: appealId || null,
      recovered: previousState?.kind === 'missing-course' && previousState.routeKey === routeKey
        ? Boolean(previousState.recovered)
        : false,
      selectedCourseSnapshotId:
        previousState?.kind === 'missing-course' && previousState.routeKey === routeKey
          ? previousState.selectedCourseSnapshotId
          : Number(selectedCourseRaw.value?.id || 0) || null
    }
    return
  }

  appealRouteState.value = null

  if (
    !selectedCourseRaw.value ||
    Number(selectedCourseRaw.value.id) !== routeSubjectId ||
    selectedCourseRaw.value !== matchedCourse
  ) {
    userStore.setSelectedCourse(matchedCourse)
  }
}

const loadAppeals = async () => {
  if (!selectedCourse.value) {
    appeals.value = []
    resetFocusedAppealState()
    if (appealRouteState.value?.kind === 'missing-target') {
      appealRouteState.value = null
    }
    return
  }
  appeals.value = await api.scores.listAppeals({ subject_id: selectedCourse.value.id })
  const appealId = Number(route.query.appeal_id || 0)
  resetFocusedAppealState()
  if (appealRouteState.value?.kind === 'missing-target') {
    appealRouteState.value = null
  }
  if (appealId) {
    const target = appeals.value.find(row => Number(row.id) === appealId)
    if (target) {
      await nextTick()
      const node = document.querySelector(`[data-testid="score-appeal-row-${appealId}"]`)
      node?.scrollIntoView({ block: 'center', behavior: 'auto' })
      focusedAppealStatus.value = String(target.status || '')
      focusedAppealResponse.value = String(target.teacher_response || '')
      if (isActionableAppealStatus(target.status)) {
        openAppealDialog(target)
      }
    } else {
      appealRouteState.value = {
        kind: 'missing-target',
        routeKey: getAppealRouteKey(),
        subjectId: Number(selectedCourse.value?.id || 0) || null,
        appealId
      }
    }
  }
}

const refreshAppeals = async () => {
  await syncAppealRouteCourseContext()
  await loadAppeals()
}

const recoverWithCurrentCourse = async () => {
  if (!selectedCourseRaw.value) {
    return
  }
  if (appealRouteState.value?.kind === 'missing-course') {
    appealRouteState.value = {
      ...appealRouteState.value,
      recovered: true
    }
  }
  await clearStaleAppealRouteContext()
}

const clearStaleAppealRouteContext = async () => {
  if (!route.query.subject_id && !route.query.appeal_id) {
    return
  }
  const nextQuery = { ...route.query }
  delete nextQuery.subject_id
  delete nextQuery.appeal_id
  await router.replace({
    path: route.path,
    query: nextQuery
  })
}

const loadScoresPageData = async () => {
  await syncAppealRouteCourseContext()
  await Promise.all([loadStudents(), loadScores(), loadWeights(), loadGradeScheme(), loadAppeals()])
  await loadClassCompositions()
}

const appealFocusBannerTitle = computed(() => {
  if (!focusedAppealStatus.value || !isTerminalAppealStatus(focusedAppealStatus.value)) return ''
  const response = focusedAppealResponse.value.trim()
  const statusLabel = getAppealStatusLabel(focusedAppealStatus.value, { verbose: true }) || focusedAppealStatus.value
  return response
    ? `已定位到目标申诉；当前状态：${statusLabel}；教师回复：${response}`
    : `已定位到目标申诉；当前状态：${statusLabel}`
})

const formatAppealTarget = row => {
  if (row?.target_component === 'homework') {
    return row?.homework_title ? `作业：${row.homework_title}` : '作业'
  }
  if (row?.target_component === 'homework_avg') {
    return '作业平时分（均分）'
  }
  return row?.target_component || '—'
}

const resetForm = () => {
  form.student_id = null
  form.score = 0
  form.exam_type = '期中考试'
  form.exam_date = null
  form.semester = semesters.value[0]?.name || ''
  batchStudents.value = []
  scoreInputRefs.value = []
  bulkScore.value = ''
  batchEntryStep.value = 1
}

const openCreateDialog = () => {
  editingScore.value = null
  resetForm()
  batchStudents.value = students.value.map(item => ({
    student_id: item.student_id,
    student_name: item.student_name,
    student_no: item.student_no,
    score: ''
  }))
  dialogVisible.value = true
}

const openWeightDialog = async () => {
  await loadWeights()
  weightDialogVisible.value = true
}

const openSchemeDialog = async () => {
  await loadGradeScheme()
  schemeForm.homework_weight = gradeScheme.value.homework_weight
  schemeForm.extra_daily_weight = gradeScheme.value.extra_daily_weight
  schemeDialogVisible.value = true
}

const openEditDialog = score => {
  editingScore.value = score
  Object.assign(form, {
    student_id: score.student_id,
    score: score.score,
    exam_type: score.exam_type,
    exam_date: score.exam_date ? new Date(score.exam_date) : null,
    semester: score.semester
  })
  dialogVisible.value = true
}

const setScoreInputRef = (element, index) => {
  scoreInputRefs.value[index] = element
}

const focusScoreInput = index => {
  const component = scoreInputRefs.value[index]
  const input = component?.input || component?.$el?.querySelector?.('input')
  input?.focus()
  input?.select?.()
}

const focusNextScoreInput = index => {
  const nextIndex = index + 1
  if (nextIndex < batchStudents.value.length) {
    focusScoreInput(nextIndex)
  }
}

const goToBatchEntry = async () => {
  await formRef.value.validate()
  batchEntryStep.value = 2
  await nextTick()
  focusScoreInput(0)
}

const submitForm = async () => {
  await formRef.value.validate()
  submitting.value = true
  try {
    const payload = {
      student_id: form.student_id,
      subject_id: selectedCourse.value.id,
      class_id: selectedCourse.value.class_id,
      score: form.score,
      exam_type: form.exam_type,
      exam_date: form.exam_date,
      semester: form.semester
    }
    if (editingScore.value) {
      await api.scores.update(editingScore.value.id, payload)
      ElMessage.success('成绩已更新')
    } else {
      await api.scores.create(payload)
      ElMessage.success('成绩已录入')
    }
    dialogVisible.value = false
    await loadScores()
    await loadClassCompositions()
  } finally {
    submitting.value = false
  }
}

const submitBatchScores = async () => {
  const filledScores = batchStudents.value.filter(item => `${item.score}`.trim() !== '')

  if (!filledScores.length) {
    ElMessage.warning('请至少录入一名学生的成绩')
    return
  }

  const invalidStudent = filledScores.find(item => {
    const value = Number(item.score)
    return Number.isNaN(value) || value < 0 || value > 100
  })
  if (invalidStudent) {
    ElMessage.error(`请检查 ${invalidStudent.student_name} 的成绩，需在 0 到 100 之间`)
    return
  }

  submitting.value = true
  try {
    await api.scores.batchCreate({
      scores: filledScores.map(item => ({
        student_id: item.student_id,
        student_no: item.student_no,
        subject_id: selectedCourse.value.id,
        class_id: selectedCourse.value.class_id,
        score: Number(item.score),
        exam_type: form.exam_type,
        exam_date: form.exam_date,
        semester: form.semester
      }))
    })
    ElMessage.success('成绩已录入')
    dialogVisible.value = false
    await loadScores()
    await loadClassCompositions()
  } finally {
    submitting.value = false
  }
}

const fillAllScores = () => {
  const value = Number(bulkScore.value)
  if (Number.isNaN(value) || value < 0 || value > 100) {
    ElMessage.error('请输入 0 到 100 之间的分数')
    return
  }

  batchStudents.value = batchStudents.value.map(item => ({
    ...item,
    score: String(value)
  }))
  ElMessage.success('已为所有学生填入统一分数')
}

const addWeightRow = () => {
  weightForm.items.push({
    exam_type: '',
    weight: 0
  })
}

const removeWeightRow = index => {
  weightForm.items.splice(index, 1)
}

const saveWeights = async () => {
  if (!selectedCourse.value) {
    return
  }

  const normalizedItems = weightForm.items
    .map(item => ({
      exam_type: `${item.exam_type || ''}`.trim(),
      weight: Number(item.weight || 0)
    }))
    .filter(item => item.exam_type)

  if (!normalizedItems.length) {
    ElMessage.error('请至少配置一次考试占比')
    return
  }

  const examSum = Number(normalizedItems.reduce((sum, item) => sum + item.weight, 0).toFixed(2))
  const hw = Number(gradeScheme.value.homework_weight || 0)
  const ex = Number(gradeScheme.value.extra_daily_weight || 0)
  if (examSum + hw + ex > 100) {
    ElMessage.error('考试占比与平时分占比之和不能超过 100%，请下调考试或平时分占比')
    return
  }

  savingWeights.value = true
  try {
    examWeights.value = await api.scores.updateWeights(selectedCourse.value.id, {
      items: normalizedItems
    })
    weightForm.items = examWeights.value.map(item => ({
      exam_type: item.exam_type,
      weight: Number(item.weight)
    }))
    weightDialogVisible.value = false
    ElMessage.success('考试占比已保存')
    await loadClassCompositions()
  } finally {
    savingWeights.value = false
  }
}

const saveScheme = async () => {
  if (!selectedCourse.value) return
  savingScheme.value = true
  try {
    const s = await api.scores.updateGradeScheme(selectedCourse.value.id, {
      homework_weight: schemeForm.homework_weight,
      extra_daily_weight: schemeForm.extra_daily_weight
    })
    gradeScheme.value = {
      homework_weight: Number(s.homework_weight),
      extra_daily_weight: Number(s.extra_daily_weight)
    }
    schemeDialogVisible.value = false
    ElMessage.success('平时分占比已保存')
    await loadClassCompositions()
  } finally {
    savingScheme.value = false
  }
}

const deleteScore = async score => {
  try {
    await ElMessageBox.confirm(`确认删除 ${score.student_name} 的成绩记录吗？`, '删除成绩', { type: 'warning' })
    await api.scores.delete(score.id)
    ElMessage.success('成绩已删除')
    await loadScores()
    await loadClassCompositions()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除成绩失败', error)
    }
  }
}

const openAppealDialog = row => {
  appealResolve.appealId = row.id
  appealResolve.response = ''
  appealDialogVisible.value = true
}

const submitAppealResolve = async () => {
  if (!appealResolve.response.trim()) {
    ElMessage.warning('请填写回复')
    return
  }
  appealResolve.loading = true
  try {
    await api.scores.updateAppeal(appealResolve.appealId, {
      teacher_response: appealResolve.response.trim(),
      status: 'resolved'
    })
    ElMessage.success('已回复')
    appealDialogVisible.value = false
    await loadAppeals()
  } finally {
    appealResolve.loading = false
  }
}

const scoreTag = score => {
  if (score >= 90) return 'success'
  if (score >= 60) return 'warning'
  return 'danger'
}

const formatDate = value => {
  if (!value) return '未设置'
  return new Date(value).toLocaleString('zh-CN')
}

onMounted(async () => {
  await loadSemesters()
  await loadScoresPageData()
})

watch(
  () => [selectedCourseRaw.value?.id || null, route.query.subject_id || '', route.query.appeal_id || ''],
  async () => {
    await loadScoresPageData()
  }
)

watch(
  () => userStore.selectedCourseSelectionEvent,
  async (nextEvent, previousEvent) => {
    if (!nextEvent || nextEvent.sequence === previousEvent?.sequence || nextEvent.reason !== 'user') {
      return
    }
    const nextCourseId = Number(nextEvent.courseId || 0)
    const blockedSubjectId = routeStateBlockedSubjectId.value
    if (!blockedSubjectId || !nextCourseId || nextCourseId === blockedSubjectId) {
      return
    }
    if (appealRouteState.value?.kind === 'missing-course') {
      appealRouteState.value = {
        ...appealRouteState.value,
        recovered: true
      }
    }
    await clearStaleAppealRouteContext()
  }
)
</script>

<style scoped>
.scores-page {
  padding: 24px;
  min-width: 0;
  overflow-x: hidden;
  width: min(100%, 1180px);
  margin: 0 auto;
}

.scores-page :deep(.el-card) {
  min-width: 0;
  border-radius: var(--wa-radius-lg);
  border: 1px solid color-mix(in srgb, var(--wa-border-subtle) 86%, transparent);
  box-shadow: var(--wa-shadow-surface);
}

.scores-page :deep(.el-card__body) {
  overflow-x: hidden;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
}

.back-button {
  order: 2;
  flex: 0 0 auto;
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
  order: 1;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 12px;
  min-width: 0;
  flex: 0 0 auto;
}

.stats-card {
  margin-bottom: 20px;
}

.scores-composition-scroll,
.scores-list-scroll,
.scores-batch-scroll,
.scores-weight-scroll {
  overflow-x: auto;
  max-width: 100%;
}

.scores-composition-scroll :deep(.el-table) {
  min-width: 1100px;
}

.scores-list-scroll :deep(.el-table) {
  min-width: 900px;
}

.scores-batch-scroll :deep(.el-table) {
  min-width: 560px;
}

.scores-weight-scroll :deep(.el-table) {
  min-width: 520px;
}

.weights-card,
.totals-card,
.appeals-card {
  margin-bottom: 20px;
}

.appeal-focus-banner {
  margin-bottom: 12px;
}

.appeal-missing-course-alert {
  margin-bottom: 12px;
}

.appeal-missing-course-actions {
  margin: -4px 0 16px;
}

.appeal-target-missing-alert {
  margin: -4px 0 16px;
}

.appeal-row-focus {
  font-weight: 700;
  color: var(--el-color-primary);
}

.scheme-hint {
  margin: 0 0 12px;
  color: #64748b;
  font-size: var(--wa-font-size-md);
  line-height: 1.5;
  text-align: center;
}

.scheme-tags {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
}

.scheme-sum {
  margin: 12px 0 0;
  font-size: var(--wa-font-size-md);
  color: #0f172a;
  text-align: center;
}

.scheme-sum.invalid {
  color: #b45309;
}

.toolbar {
  display: flex;
  justify-content: center;
  margin-bottom: 16px;
}

.toolbar-inline {
  display: flex;
  justify-content: center;
  gap: 8px;
  min-width: 0;
  flex-wrap: wrap;
}

.card-header-inline {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-direction: row;
  gap: 16px;
  flex-wrap: wrap;
}

.weight-total {
  color: #64748b;
  font-size: var(--wa-font-size-md);
}

.weight-dialog-tools {
  display: flex;
  justify-content: center;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.mb-12 {
  margin-bottom: 12px;
}

.muted {
  color: #94a3b8;
}

.small {
  font-size: var(--wa-font-size-sm);
}

.batch-entry-panel {
  display: grid;
  gap: 16px;
}

.batch-entry-summary {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  justify-content: center;
  padding: 14px 16px;
  background: #f8fafc;
  border-radius: 12px;
  text-align: center;
}

.summary-item {
  color: #475569;
}

.batch-entry-alert {
  margin-bottom: 4px;
}

.batch-fill-tools {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .scores-page {
    padding: 18px 14px;
  }

  .page-header {
    flex-direction: column;
    align-items: stretch;
  }

  .back-button {
    align-self: flex-start;
  }

  .header-actions {
    justify-content: stretch;
  }

  .header-actions :deep(.el-button) {
    flex: 1 1 160px;
  }
}
</style>
