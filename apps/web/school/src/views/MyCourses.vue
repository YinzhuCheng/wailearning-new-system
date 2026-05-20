<template>
  <div class="courses-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">我的课程</h1>
        <p class="page-subtitle">
          {{ userStore.isStudent ? '选择一门课程查看作业与通知。' : '选择一门课程进入教学工作台。' }}
        </p>
      </div>
      <el-card
        v-if="userStore.isStudent && (activeCourses.length || completedCourses.length)"
        shadow="never"
        class="quota-card"
      >
        <template #header>
          <div class="quota-card-header-row">
            <span>全站 LLM 日额度</span>
            <el-button size="small" :loading="quotasLoading" @click="loadStudentQuotasSummary">刷新</el-button>
          </div>
        </template>
        <div v-loading="quotasLoading" class="quota-body">
          <p v-if="quotasSummary?.uses_personal_override" class="quota-line quota-hint">
            当前账号使用管理员单独配置的日 token 上限；所有课程共用同一全站额度池，以下仅列出你已选课程便于对照。
          </p>
          <p v-else class="quota-line quota-hint muted">
            学生 LLM 调用统一计入全站日额度；与具体从哪门课入口触发无关。
          </p>

          <div v-if="quotaSummaryLimit > 0" class="quota-global">
            <div class="quota-global__head">
              <span class="quota-global__title">今日用量</span>
              <span class="quota-global__nums">
                <strong>{{ quotaSummaryUsed }}</strong>
                <span class="quota-global__sep">/</span>
                <span>{{ quotaSummaryLimit }}</span>
                <span v-if="quotaSummaryRemaining != null" class="quota-global__remain muted">
                  剩余 {{ quotaSummaryRemaining }}
                </span>
              </span>
            </div>
            <el-progress
              :percentage="quotaGlobalPercent"
              :stroke-width="20"
              :show-text="true"
              :color="quotaBarColors"
              striped
              class="quota-progress quota-progress--global"
            />
            <p v-if="quotasSummary?.usage_date" class="quota-meta muted">
              统计日 {{ quotasSummary.usage_date }}（{{ quotasSummary.quota_timezone || '—' }}）
              <template v-if="quotasSummary?.global_default_daily_student_tokens != null && !quotasSummary?.uses_personal_override">
                · 全校默认日限额 {{ quotasSummary.global_default_daily_student_tokens }}
              </template>
            </p>
          </div>
          <p v-else-if="!quotasLoading" class="quota-line muted">暂无额度配置或限额为 0。</p>

          <div v-if="quotasSummary?.courses?.length" class="quota-courses-note">
            <span class="quota-courses-note__label">已选课程</span>
            <div class="quota-chip-list">
              <span
                v-for="row in quotasSummary.courses"
                :key="row.subject_id"
                class="quota-chip"
                :class="{ 'quota-chip--current': isCurrentCourseId(row.subject_id) }"
              >
                {{ row.subject_name }}
              </span>
            </div>
          </div>
        </div>
      </el-card>
      <el-button
        v-if="canCreateCourse"
        type="primary"
        @click="openCreateDialog"
      >
        新建课程
      </el-button>
    </div>

    <el-card
      v-if="userStore.isStudent"
      shadow="never"
      class="elective-catalog-card"
    >
      <template #header>
        <div class="elective-header">
          <span>全校课程目录 · 选课说明</span>
          <el-button size="small" :loading="electiveLoading" @click="loadElectiveCatalog">刷新目录</el-button>
        </div>
      </template>
      <p class="elective-tip">
        展示系统中<strong>进行中</strong>的全部课程，并标明<strong>必修 / 选修</strong>与<strong>选课条件</strong>。
        <strong>选修课</strong>仅可对<strong>本班开设</strong>的课程点击选课；其他班级课程可浏览，选课按钮不可用。
        <strong>必修课</strong>由教师按班级花名册统一加入，不可在此自主选课。
      </p>
      <el-table :data="electiveCatalog" v-loading="electiveLoading" max-height="420" empty-text="暂无进行中的课程">
        <el-table-column label="封面" width="88">
          <template #default="{ row }">
            <el-image
              v-if="row.cover_image_url"
              :src="row.cover_image_url"
              fit="cover"
              class="catalog-cover-thumb"
              data-testid="course-catalog-cover-thumb"
              :preview-src-list="[row.cover_image_url]"
              preview-teleported
            />
            <span v-else class="muted-inline">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="课程" min-width="150" />
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="row.course_type === 'elective' ? 'warning' : 'success'" size="small">
              {{ row.course_type === 'elective' ? '选修' : '必修' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="class_name" label="开设班级" width="140" />
        <el-table-column prop="teacher_name" label="任课教师" width="120" />
        <el-table-column label="选课条件" min-width="220">
          <template #default="{ row }">
            <span class="hint-cell">{{ row.enrollment_hint || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.course_type === 'elective' && !row.is_enrolled"
              type="primary"
              size="small"
              :disabled="!row.can_self_enroll_elective"
              :loading="selfEnrollingId === row.id"
              @click="selfEnroll(row)"
            >
              选课
            </el-button>
            <el-button
              v-else-if="row.course_type === 'elective' && row.is_enrolled"
              type="danger"
              plain
              size="small"
              :disabled="!isElectiveEnrollment(row.id)"
              :loading="selfDroppingId === row.id"
              @click="selfDrop(row)"
            >
              退选
            </el-button>
            <span v-else class="muted-inline">—</span>
          </template>
        </el-table-column>
      </el-table>
      <div v-loading="electiveLoading" class="catalog-mobile-list">
        <el-empty v-if="!electiveCatalog.length" description="暂无进行中的课程" />
        <article v-for="row in electiveCatalog" v-else :key="row.id" class="catalog-mobile-item">
          <div class="catalog-mobile-item__main">
            <div class="catalog-mobile-item__title-row">
              <strong>{{ row.name }}</strong>
              <el-tag :type="row.course_type === 'elective' ? 'warning' : 'success'" size="small">
                {{ row.course_type === 'elective' ? '选修' : '必修' }}
              </el-tag>
            </div>
            <div class="catalog-mobile-item__meta">
              <span>{{ row.class_name || '未分配班级' }}</span>
              <span>{{ row.teacher_name || '未分配教师' }}</span>
            </div>
            <p>{{ row.enrollment_hint || '暂无选课说明' }}</p>
          </div>
          <div class="catalog-mobile-item__action">
            <el-button
              v-if="row.course_type === 'elective' && !row.is_enrolled"
              type="primary"
              size="small"
              :disabled="!row.can_self_enroll_elective"
              :loading="selfEnrollingId === row.id"
              @click="selfEnroll(row)"
            >
              选课
            </el-button>
            <el-button
              v-else-if="row.course_type === 'elective' && row.is_enrolled"
              type="danger"
              plain
              size="small"
              :disabled="!isElectiveEnrollment(row.id)"
              :loading="selfDroppingId === row.id"
              @click="selfDrop(row)"
            >
              退选
            </el-button>
            <span v-else class="muted-inline">-</span>
          </div>
        </article>
      </div>
    </el-card>

    <el-row :gutter="20" v-loading="loading">
      <el-col :span="24">
        <section class="course-section">
          <div class="section-header">
            <h2>正在进行</h2>
            <span>{{ activeCourses.length }} 门</span>
          </div>
          <el-empty v-if="!activeCourses.length" description="暂无进行中的课程" />
          <div v-else class="course-grid">
            <article
              v-for="course in activeCourses"
              :key="course.id"
              class="course-card"
              :class="{ 'course-card-selected': userStore.selectedCourse?.id === course.id }"
            >
              <div v-if="course.cover_image_url" class="course-card-cover" data-testid="course-card-cover">
                <el-image :src="course.cover_image_url" fit="cover" class="course-card-cover-img" />
              </div>
              <div class="course-card-header">
                <h3>{{ course.name }}</h3>
                <div class="course-tags">
                  <el-tag type="primary">{{ course.course_type === 'elective' ? '选修课' : '必修课' }}</el-tag>
                  <el-tag type="success">进行中</el-tag>
                </div>
              </div>
              <div class="course-meta">
                <span>班级：{{ course.class_name || '未分配' }}</span>
                <span>任课老师：{{ course.teacher_name || '未分配' }}</span>
                <span>学期：{{ course.semester || '未设置' }}</span>
                <span>课程时间：{{ formatCourseTimes(course) || '未设置' }}</span>
                <span>学生数：{{ course.student_count || 0 }}</span>
              </div>
              <p class="course-description">{{ course.description || '暂无课程简介。' }}</p>
              <div class="course-actions">
                <el-button
                  :type="isCurrentCourse(course) ? 'info' : 'primary'"
                  :plain="isCurrentCourse(course)"
                  :disabled="isCurrentCourse(course)"
                  @click.stop="selectCourse(course)"
                >
                  进入课程
                </el-button>
              </div>
            </article>
          </div>
        </section>
      </el-col>

      <el-col :span="24">
        <section class="course-section">
          <div class="section-header">
            <h2>已结束课程</h2>
            <span>{{ completedCourses.length }} 门</span>
          </div>
          <el-empty v-if="!completedCourses.length" description="暂无已结束课程" />
          <div v-else class="course-grid">
            <article
              v-for="course in completedCourses"
              :key="course.id"
              class="course-card course-card-muted"
              :class="{ 'course-card-selected': userStore.selectedCourse?.id === course.id }"
            >
              <div v-if="course.cover_image_url" class="course-card-cover course-card-cover--muted">
                <el-image :src="course.cover_image_url" fit="cover" class="course-card-cover-img" />
              </div>
              <div class="course-card-header">
                <h3>{{ course.name }}</h3>
                <div class="course-tags">
                  <el-tag type="info">{{ course.course_type === 'elective' ? '选修课' : '必修课' }}</el-tag>
                  <el-tag type="info">已结束</el-tag>
                </div>
              </div>
              <div class="course-meta">
                <span>班级：{{ course.class_name || '未分配' }}</span>
                <span>任课老师：{{ course.teacher_name || '未分配' }}</span>
                <span>学期：{{ course.semester || '未设置' }}</span>
                <span>课程时间：{{ formatCourseTimes(course) || '未设置' }}</span>
              </div>
              <div class="course-actions">
                <el-button
                  :type="isCurrentCourse(course) ? 'info' : 'default'"
                  :plain="isCurrentCourse(course)"
                  :disabled="isCurrentCourse(course)"
                  @click.stop="selectCourse(course)"
                >
                  查看课程
                </el-button>
              </div>
            </article>
          </div>
        </section>
      </el-col>
    </el-row>

    <el-dialog
      v-model="dialogVisible"
      title="新建课程"
      width="720px"
      destroy-on-close
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-form-item label="课程名称" prop="name">
          <el-input v-model="form.name" placeholder="例如：高一数学培优课" />
        </el-form-item>
        <el-form-item label="课程类型" prop="course_type">
          <el-radio-group v-model="form.course_type">
            <el-radio label="required">必修课</el-radio>
            <el-radio label="elective">选修课</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="课程状态" prop="status">
          <el-radio-group v-model="form.status">
            <el-radio label="active">进行中</el-radio>
            <el-radio label="completed">已结束</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="所属学期" prop="semester_id">
          <el-select v-model="form.semester_id" placeholder="请选择学期" style="width: 100%" clearable>
            <el-option v-for="item in semesters" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="课程时间" prop="course_times" class="course-times-form-item">
          <div class="course-times-editor">
            <div
              v-for="(courseTime, index) in form.course_times"
              :key="`course-time-${index}`"
              class="course-time-panel"
            >
              <div class="course-time-panel__header">
                <div>
                  <div class="course-time-panel__title">课程时间 {{ index + 1 }}</div>
                  <div class="course-time-panel__subtitle">
                    设置这一段时间内的起止日期和每周上课时间
                  </div>
                </div>
                <el-button
                  v-if="form.course_times.length > 1"
                  text
                  type="danger"
                  @click="removeCourseTime(index)"
                >
                  删除
                </el-button>
              </div>

              <div class="course-time-panel__fields">
                <div class="course-time-panel__field">
                  <div class="course-time-panel__field-label">开始日期</div>
                  <el-date-picker
                    v-model="courseTime.course_start_at"
                    type="date"
                    placeholder="请选择开始日期"
                    style="width: 100%"
                    value-format="YYYY-MM-DD"
                  />
                </div>

                <div class="course-time-panel__field">
                  <div class="course-time-panel__field-label">结束日期</div>
                  <el-date-picker
                    v-model="courseTime.course_end_at"
                    type="date"
                    placeholder="请选择结束日期"
                    style="width: 100%"
                    value-format="YYYY-MM-DD"
                  />
                </div>
              </div>

              <div class="course-time-panel__schedule">
                <div class="course-time-panel__field-label">每周时间</div>
                <CourseSchedulePicker v-model="courseTime.weekly_schedule" />
              </div>
            </div>

            <el-button plain class="course-times-editor__add" @click="addCourseTime">
              添加课程时间
            </el-button>
          </div>
        </el-form-item>
        <el-form-item label="课程简介">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="可选，简单说明课程内容" />
        </el-form-item>
        <el-form-item label="学生名单" prop="students">
          <div class="roster-tools">
            <div class="roster-actions">
              <el-button @click="downloadTemplate('xlsx')">Excel模板</el-button>
              <el-button @click="downloadTemplate('csv')">CSV模板</el-button>
              <el-button type="primary" @click="triggerImport">上传名单</el-button>
            </div>
            <div class="roster-summary">
              {{ rosterSummary }}
            </div>
            <input
              ref="fileInputRef"
              class="hidden-file-input"
              type="file"
              accept=".xlsx,.xls,.csv"
              @change="handleFileChange"
            />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">创建课程</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import * as XLSX from 'xlsx'

import { ElMessage } from 'element-plus'

import api from '@/api'
import CourseSchedulePicker from '@/components/CourseSchedulePicker.vue'
import { useUserStore } from '@/stores/user'
import { parseScheduleValue } from '@/utils/courseSchedule'
import {
  createEmptyCourseTime,
  formatCourseTimes,
  serializeCourseTimesPayload
} from '@/utils/courseTimes'

const router = useRouter()
const userStore = useUserStore()
const TEMPLATE_HEADERS = ['姓名', '性别', '学号', '选课方式', '手机号', '家长手机号', '地址']
const TEMPLATE_ROWS = [
  {
    姓名: '张三',
    性别: '男',
    学号: '2026001',
    选课方式: '必修',
    手机号: '13800000000',
    家长手机号: '13900000000',
    地址: '上海市浦东新区'
  }
]

const loading = ref(false)
const submitting = ref(false)
const courses = ref([])
const electiveCatalog = ref([])
const electiveLoading = ref(false)
const selfEnrollingId = ref(null)
const selfDroppingId = ref(null)
const quotasSummary = ref(null)
const quotasLoading = ref(false)
const semesters = ref([])
const dialogVisible = ref(false)
const formRef = ref(null)
const fileInputRef = ref(null)
const rosterStudents = ref([])

const form = reactive({
  name: '',
  course_type: 'required',
  status: 'active',
  semester_id: null,
  course_times: [createEmptyCourseTime()],
  description: ''
})

const activeCourses = computed(() => courses.value.filter(course => course.status !== 'completed'))
const completedCourses = computed(() => courses.value.filter(course => course.status === 'completed'))
const canCreateCourse = computed(() => userStore.isTeacher || userStore.isClassTeacher)
const quotaSummaryUsed = computed(() => quotasSummary.value?.student_used_tokens_today ?? 0)
const quotaSummaryLimit = computed(() => quotasSummary.value?.daily_student_token_limit ?? quotasSummary.value?.global_default_daily_student_tokens ?? 0)
const quotaSummaryRemaining = computed(() => quotasSummary.value?.student_remaining_tokens_today ?? Math.max(0, quotaSummaryLimit.value - quotaSummaryUsed.value))

const quotaGlobalPercent = computed(() => {
  const lim = Number(quotaSummaryLimit.value)
  const used = Number(quotaSummaryUsed.value)
  if (!lim || lim <= 0) {
    return 0
  }
  return Math.min(100, Math.round((used / lim) * 1000) / 10)
})
const rosterSummary = computed(() =>
  rosterStudents.value.length
    ? `已导入 ${rosterStudents.value.length} 名学生`
    : '请上传 Excel 或 CSV 学生名单。系统会自动识别列名，至少需要姓名和学号两列。'
)

const loadCourses = async () => {
  loading.value = true
  try {
    courses.value = await api.courses.list()
  } catch (error) {
    console.error('加载课程失败', error)
    ElMessage.error('加载课程失败')
  } finally {
    loading.value = false
  }
}

const loadElectiveCatalog = async () => {
  if (!userStore.isStudent) {
    return
  }
  electiveLoading.value = true
  try {
    electiveCatalog.value = await api.courses.courseCatalog()
  } catch (error) {
    console.error('加载课程目录失败', error)
  } finally {
    electiveLoading.value = false
  }
}

const isEnrolled = courseId =>
  (courses.value || []).some(c => String(c.id) === String(courseId))

const isElectiveEnrollment = courseId => {
  const c = (courses.value || []).find(x => String(x.id) === String(courseId))
  return Boolean(c && c.course_type === 'elective')
}

const selfEnroll = async row => {
  if (!row?.id) {
    return
  }
  selfEnrollingId.value = row.id
  try {
    const res = await api.courses.studentSelfEnroll(row.id)
    if (res?.already_enrolled) {
      ElMessage.info('已在该课程选课名单中')
    } else {
      ElMessage.success('选课成功')
    }
    await Promise.all([loadCourses(), loadElectiveCatalog()])
    if (String(userStore.selectedCourse?.id) === String(row.id)) {
      await loadStudentQuotasSummary()
    }
  } catch (error) {
    console.error('选课失败', error)
  } finally {
    selfEnrollingId.value = null
  }
}

const selfDrop = async row => {
  if (!row?.id) {
    return
  }
  selfDroppingId.value = row.id
  try {
    const res = await api.courses.studentSelfDrop(row.id)
    if (!res?.removed) {
      ElMessage.warning('未找到选课记录')
    } else {
      ElMessage.success('已退选')
    }
    await Promise.all([loadCourses(), loadElectiveCatalog()])
    if (String(userStore.selectedCourse?.id) === String(row.id)) {
      await loadStudentQuotasSummary()
    }
  } catch (error) {
    console.error('退选失败', error)
  } finally {
    selfDroppingId.value = null
  }
}

const loadStudentQuotasSummary = async () => {
  if (!userStore.isStudent) {
    quotasSummary.value = null
    return
  }
  quotasLoading.value = true
  try {
    quotasSummary.value = await api.llmSettings.getStudentQuotasSummary()
  } catch (error) {
    console.error('加载各课 LLM 额度失败', error)
    quotasSummary.value = null
  } finally {
    quotasLoading.value = false
  }
}

const isCurrentCourseId = id => String(userStore.selectedCourse?.id || '') === String(id || '')

const quotaBarColors = [
  { color: '#93c5fd', percentage: 60 },
  { color: '#3b82f6', percentage: 85 },
  { color: '#f59e0b', percentage: 95 },
  { color: '#ef4444', percentage: 100 }
]

const loadSemesters = async () => {
  semesters.value = await api.semesters.list()
}

function validateCourseTimes(_rule, value, callback) {
  if (!Array.isArray(value) || !value.length) {
    callback(new Error('请至少添加一组课程时间'))
    return
  }

  for (const item of value) {
    if (!item.course_start_at || !item.course_end_at) {
      callback(new Error('请为每组课程时间选择开始日期和结束日期'))
      return
    }

    if (new Date(item.course_end_at) < new Date(item.course_start_at)) {
      callback(new Error('课程时间的结束日期不能早于开始日期'))
      return
    }

    if (!parseScheduleValue(item.weekly_schedule).length) {
      callback(new Error('请为每组课程时间选择每周时间'))
      return
    }
  }

  callback()
}

const rules = {
  name: [{ required: true, message: '请输入课程名称', trigger: 'blur' }],
  course_times: [{ validator: validateCourseTimes, trigger: 'change' }]
}

const resetForm = () => {
  Object.assign(form, {
    name: '',
    course_type: 'required',
    status: 'active',
    semester_id: null,
    course_times: [createEmptyCourseTime()],
    description: ''
  })
  rosterStudents.value = []
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

const openCreateDialog = () => {
  resetForm()
  dialogVisible.value = true
}

const isCurrentCourse = course => String(userStore.selectedCourse?.id || '') === String(course?.id || '')

const selectCourse = course => {
  if (isCurrentCourse(course)) {
    return
  }

  userStore.setSelectedCourse(course, { reason: 'user' })
  if (userStore.isStudent) {
    router.push('/course-home')
    return
  }
  router.push('/students')
}

const normalizeCellValue = value => {
  if (value === undefined || value === null) {
    return ''
  }
  return String(value).trim()
}

const normalizeHeaderKey = value =>
  normalizeCellValue(value)
    .replace(/^\uFEFF/, '')
    .toLowerCase()
    .replace(/[\s_\-()（）[\]【】]/g, '')

const buildNormalizedRow = row =>
  Object.fromEntries(
    Object.entries(row || {}).map(([key, value]) => [normalizeHeaderKey(key), value])
  )

const pickRowValue = (row, aliases) => {
  const matchedKey = aliases.find(alias => alias in row)
  return matchedKey ? normalizeCellValue(row[matchedKey]) : ''
}

const normalizeGenderInput = value => {
  const gender = normalizeCellValue(value).replace(/\s+/g, '').toLowerCase()
  const genderMap = {
    男: 'male',
    male: 'male',
    m: 'male',
    '1': 'male',
    男性: 'male',
    女: 'female',
    female: 'female',
    f: 'female',
    '0': 'female',
    女性: 'female'
  }
  return genderMap[gender] || ''
}

const normalizeEnrollmentTypeInput = value => {
  const normalized = normalizeCellValue(value).replace(/\s+/g, '').toLowerCase()
  const enrollmentTypeMap = {
    必修: 'required',
    required: 'required',
    选修: 'elective',
    elective: 'elective'
  }
  return enrollmentTypeMap[normalized] || 'required'
}

const downloadBlob = (blob, filename) => {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  window.URL.revokeObjectURL(url)
}

const downloadTemplate = format => {
  const worksheet = XLSX.utils.json_to_sheet(TEMPLATE_ROWS, { header: TEMPLATE_HEADERS })

  if (format === 'csv') {
    const csv = XLSX.utils.sheet_to_csv(worksheet)
    downloadBlob(new Blob(['\uFEFF', csv], { type: 'text/csv;charset=utf-8;' }), '课程学生名单模板.csv')
    return
  }

  const workbook = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(workbook, worksheet, '学生名单')
  XLSX.writeFile(workbook, '课程学生名单模板.xlsx')
}

const addCourseTime = () => {
  form.course_times.push(createEmptyCourseTime())
  formRef.value?.clearValidate('course_times')
}

const removeCourseTime = index => {
  if (form.course_times.length <= 1) {
    return
  }

  form.course_times.splice(index, 1)
  formRef.value?.clearValidate('course_times')
}

const triggerImport = () => {
  fileInputRef.value?.click()
}

const readWorkbook = async file => {
  const buffer = await file.arrayBuffer()
  const lowerName = file.name.toLowerCase()

  if (lowerName.endsWith('.csv')) {
    let content = new TextDecoder('utf-8').decode(buffer)

    if (content.includes('\uFFFD')) {
      try {
        content = new TextDecoder('gbk').decode(buffer)
      } catch (error) {
        console.warn('CSV GBK decode failed, fallback to UTF-8', error)
      }
    }

    return XLSX.read(content, { type: 'string' })
  }

  return XLSX.read(buffer, { type: 'array' })
}

const parseImportRows = rows => {
  const students = []
  const errors = []

  rows.forEach((rawRow, index) => {
    const rowNumber = index + 2
    const row = buildNormalizedRow(rawRow)
    const name = pickRowValue(row, ['姓名', '学生姓名', 'name', 'studentname'].map(normalizeHeaderKey))
    const studentNo = pickRowValue(row, ['学号', '学员编号', '学生编号', 'studentno', 'student_no', 'studentid', '编号'].map(normalizeHeaderKey))
    const gender = normalizeGenderInput(pickRowValue(row, ['性别', 'gender'].map(normalizeHeaderKey)))
    const enrollmentType = normalizeEnrollmentTypeInput(
      pickRowValue(row, ['选课方式', '课程类型', '修读方式', 'enrollmenttype', 'coursetype'].map(normalizeHeaderKey))
    )
    const phone = pickRowValue(row, ['手机号', '手机号码', '联系电话', 'phone', 'mobile'].map(normalizeHeaderKey))
    const parentPhone = pickRowValue(row, ['家长手机号', '家长电话', '监护人电话', 'parentphone', 'guardianphone'].map(normalizeHeaderKey))
    const address = pickRowValue(row, ['地址', '住址', '家庭住址', 'address'].map(normalizeHeaderKey))

    if (!name || !studentNo || !gender) {
      if (!name && !studentNo && !gender && !phone && !parentPhone && !address) {
        return
      }
      if (!name) {
        errors.push(`第 ${rowNumber} 行缺少“姓名”列对应的数据`)
        return
      }
      if (!studentNo) {
        errors.push(`第 ${rowNumber} 行缺少“学号”列对应的数据`)
        return
      }
    }

    students.push({
      name,
      student_no: studentNo,
      enrollment_type: enrollmentType,
      gender: gender || null,
      phone: phone || null,
      parent_phone: parentPhone || null,
      address: address || null
    })
  })

  return { students, errors }
}

const validateRosterHeaders = rows => {
  const normalizedHeaderSet = new Set(
    Object.keys(buildNormalizedRow(rows[0] || {}))
  )

  const hasNameColumn = ['姓名', '学生姓名', 'name', 'studentname']
    .map(normalizeHeaderKey)
    .some(alias => normalizedHeaderSet.has(alias))
  const hasStudentNoColumn = ['学号', '学员编号', '学生编号', 'studentno', 'student_no', 'studentid', '编号']
    .map(normalizeHeaderKey)
    .some(alias => normalizedHeaderSet.has(alias))

  if (!hasNameColumn || !hasStudentNoColumn) {
    const missing = []
    if (!hasNameColumn) {
      missing.push('姓名')
    }
    if (!hasStudentNoColumn) {
      missing.push('学号')
    }
    return `缺少必要列：${missing.join('、')}`
  }

  return ''
}

const handleFileChange = async event => {
  const [file] = event.target.files || []
  if (!file) {
    return
  }

  try {
    const workbook = await readWorkbook(file)
    const sheetName = workbook.SheetNames[0]
    const worksheet = workbook.Sheets[sheetName]
    const rows = XLSX.utils.sheet_to_json(worksheet, { defval: '', raw: false })
    const headerError = validateRosterHeaders(rows)

    if (headerError) {
      ElMessage.error(headerError)
      return
    }

    const { students, errors } = parseImportRows(rows)

    if (errors.length) {
      ElMessage.error(errors[0])
      return
    }

    if (!students.length) {
      ElMessage.error('名单文件中没有可导入的学生数据')
      return
    }

    rosterStudents.value = students
    ElMessage.success(`已导入 ${students.length} 名学生`)
  } catch (error) {
    console.error('解析学生名单失败', error)
    ElMessage.error('解析学生名单失败')
  } finally {
    if (fileInputRef.value) {
      fileInputRef.value.value = ''
    }
  }
}

const submitForm = async () => {
  await formRef.value.validate()

  if (!rosterStudents.value.length) {
    ElMessage.error('请先上传学生名单')
    return
  }

  submitting.value = true
  try {
    const createdCourse = await api.courses.create({
      name: form.name,
      course_type: form.course_type,
      status: form.status,
      semester_id: form.semester_id || null,
      course_times: serializeCourseTimesPayload(form.course_times),
      description: form.description,
      students: rosterStudents.value
    })
    await Promise.all([loadCourses(), userStore.fetchTeachingCourses(true)])
    userStore.setSelectedCourse(createdCourse, { reason: 'user' })
    dialogVisible.value = false
    ElMessage.success('课程已创建')
    router.push('/students')
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  const tasks = [loadCourses(), loadSemesters()]
  if (userStore.isStudent) {
    tasks.push(loadElectiveCatalog(), loadStudentQuotasSummary())
  }
  Promise.all(tasks)
})

watch(
  () => [userStore.isStudent, courses.value.length],
  () => {
    if (userStore.isStudent) {
      loadStudentQuotasSummary()
    } else {
      quotasSummary.value = null
    }
  }
)
</script>

<style scoped>
.courses-page {
  padding: 24px;
  min-width: 0;
  overflow-x: hidden;
  width: min(100%, 1180px);
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 22px;
  min-width: 0;
}

.page-title {
  margin: 0 0 8px;
  font-size: 28px;
  font-weight: 700;
  color: #1f2937;
}

.page-subtitle {
  margin: 0;
  color: #64748b;
}

.quota-card {
  width: min(100%, 560px);
  margin-bottom: 0;
  min-width: 0;
  border-radius: var(--wa-radius-lg);
  border: 1px solid color-mix(in srgb, var(--wa-border-subtle) 82%, transparent);
  box-shadow: var(--wa-shadow-surface);
}

.quota-global {
  margin-top: 12px;
  padding: 16px 18px;
  border-radius: var(--wa-radius-xl, 16px);
  background: linear-gradient(145deg, #f8fafc 0%, #eef2ff 55%, #f1f5f9 100%);
  border: 1px solid #e2e8f0;
}

.quota-global__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.quota-global__title {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
  letter-spacing: 0.02em;
}

.quota-global__nums {
  font-size: 14px;
  color: #334155;
  font-variant-numeric: tabular-nums;
}

.quota-global__nums strong {
  font-size: 18px;
  font-weight: 700;
  color: #1e40af;
}

.quota-global__sep {
  margin: 0 4px;
  color: #94a3b8;
  font-weight: 500;
}

.quota-global__remain {
  margin-left: 10px;
  font-size: 13px;
}

.quota-meta {
  margin: 12px 0 0;
  font-size: 12px;
  line-height: 1.5;
}

.quota-courses-note {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px dashed #e2e8f0;
}

.quota-courses-note__label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  margin-bottom: 8px;
}

.quota-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.quota-chip {
  display: inline-block;
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 13px;
  color: #334155;
  background: #fff;
  border: 1px solid #e2e8f0;
  max-width: 100%;
  overflow-wrap: anywhere;
}

.quota-chip--current {
  border-color: #93c5fd;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  color: #1e40af;
  font-weight: 600;
}

.quota-progress--global :deep(.el-progress-bar__outer) {
  border-radius: 999px;
  overflow: hidden;
  background-color: rgba(255, 255, 255, 0.72);
  box-shadow: inset 0 1px 2px rgba(15, 23, 42, 0.06);
}

.quota-progress--global :deep(.el-progress-bar__inner) {
  border-radius: 999px;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
}

.quota-progress--global :deep(.el-progress__text) {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
  min-width: 2.75em;
}

.quota-card-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  min-width: 0;
  flex-wrap: wrap;
}

.quota-card-header-row span {
  min-width: 0;
  overflow-wrap: anywhere;
}

.quota-hint {
  font-size: 13px;
  line-height: 1.5;
}

.quota-body {
  font-size: 14px;
  color: #334155;
}

.quota-line {
  margin: 0 0 8px;
}

.quota-line.muted {
  color: #94a3b8;
}

.elective-catalog-card {
  margin-bottom: 20px;
  min-width: 0;
  overflow: hidden;
  border-radius: var(--wa-radius-lg);
  border: 1px solid color-mix(in srgb, var(--wa-border-subtle) 86%, transparent);
  box-shadow: var(--wa-shadow-surface);
}

.elective-catalog-card :deep(.el-card__body) {
  overflow-x: auto;
}

.elective-catalog-card :deep(.el-table) {
  min-width: 870px;
}

.catalog-mobile-list {
  display: none;
}

.catalog-mobile-item {
  display: flex;
  gap: 12px;
  justify-content: space-between;
  padding: 14px 0;
  border-bottom: 1px solid #e2e8f0;
}

.catalog-mobile-item:last-child {
  border-bottom: none;
}

.catalog-mobile-item__main {
  min-width: 0;
  flex: 1;
}

.catalog-mobile-item__title-row {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.catalog-mobile-item__title-row strong {
  min-width: 0;
  color: #0f172a;
  overflow-wrap: anywhere;
}

.catalog-mobile-item__meta {
  display: grid;
  gap: 4px;
  margin-top: 8px;
  color: #64748b;
  font-size: 13px;
}

.catalog-mobile-item__meta span,
.catalog-mobile-item p {
  min-width: 0;
  overflow-wrap: anywhere;
}

.catalog-mobile-item p {
  margin: 8px 0 0;
  color: #475569;
  font-size: 13px;
  line-height: 1.5;
}

.catalog-mobile-item__action {
  display: flex;
  flex: 0 0 auto;
  align-items: flex-start;
}

.elective-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  min-width: 0;
}

.elective-header span {
  min-width: 0;
  overflow-wrap: anywhere;
}

.elective-tip {
  margin: 0 0 12px;
  font-size: 13px;
  color: #64748b;
  line-height: 1.5;
}

.hint-cell {
  color: #475569;
  font-size: 13px;
  line-height: 1.45;
}

.muted-inline {
  color: #94a3b8;
  font-size: 13px;
}

.roster-tools {
  width: 100%;
}

.roster-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.roster-summary {
  margin-top: 10px;
  color: #64748b;
  line-height: 1.6;
}

.hidden-file-input {
  display: none;
}

.course-times-editor {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: 16px;
}

.course-times-editor__add {
  align-self: flex-start;
}

.course-time-panel {
  border: 1px solid #dbe4f0;
  border-radius: var(--wa-radius-lg);
  background: #f8fbff;
  padding: 16px;
}

.course-time-panel__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.course-time-panel__title {
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
}

.course-time-panel__subtitle {
  margin-top: 4px;
  font-size: 12px;
  color: #64748b;
}

.course-time-panel__fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 14px;
}

.course-time-panel__field-label {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}

.course-time-panel__schedule {
  display: flex;
  flex-direction: column;
}

.course-section {
  background: #fff;
  border: 1px solid color-mix(in srgb, var(--wa-border-subtle) 86%, transparent);
  border-radius: var(--wa-radius-lg);
  padding: 22px;
  box-shadow: var(--wa-shadow-surface);
  margin-bottom: 20px;
  min-width: 0;
  overflow: hidden;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.section-header h2 {
  margin: 0;
  font-size: 20px;
  color: #0f172a;
}

.section-header span {
  color: #64748b;
}

.course-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(280px, 100%), 1fr));
  gap: 16px;
  min-width: 0;
}

.catalog-cover-thumb {
  width: 64px;
  height: 40px;
  border-radius: var(--wa-radius-md);
  overflow: hidden;
  border: 1px solid #e2e8f0;
}

.course-card-cover {
  margin: -20px -20px 14px;
  height: 120px;
  border-radius: var(--wa-radius-xl) var(--wa-radius-xl) 0 0;
  overflow: hidden;
  background: #e2e8f0;
}

.course-card-cover--muted {
  opacity: 0.92;
}

.course-card-cover-img {
  width: 100%;
  height: 100%;
  display: block;
}

.course-card {
  border: 1px solid color-mix(in srgb, var(--wa-border-subtle) 88%, transparent);
  border-radius: var(--wa-radius-lg);
  padding: 18px;
  cursor: pointer;
  transition: all 0.2s ease;
  background:
    linear-gradient(180deg, #ffffff 0%, color-mix(in srgb, var(--wa-color-primary-50) 26%, #fff) 100%);
  min-width: 0;
  overflow: hidden;
}

.course-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 24px rgba(59, 130, 246, 0.12);
  border-color: #93c5fd;
}

.course-card-selected {
  border-color: #2563eb;
  box-shadow:
    inset 0 0 0 1px color-mix(in srgb, var(--wa-color-primary-500) 28%, transparent),
    0 12px 24px rgba(37, 99, 235, 0.15);
}

.course-card-muted {
  background: #f8fafc;
}

.course-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
  min-width: 0;
}

.course-card-header h3 {
  min-width: 0;
  margin: 0;
  font-size: 20px;
  color: #111827;
  overflow-wrap: anywhere;
}

.course-tags {
  display: flex;
  flex: 0 1 auto;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.course-meta {
  display: grid;
  gap: 6px;
  color: #475569;
  font-size: 14px;
  min-width: 0;
}

.course-meta span {
  min-width: 0;
  overflow-wrap: anywhere;
}

.course-description {
  margin: 14px 0 0;
  min-height: 42px;
  color: #64748b;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.course-actions {
  margin-top: 18px;
  display: flex;
  justify-content: flex-end;
  min-width: 0;
}

@media (max-width: 768px) {
  .courses-page {
    padding: 18px 14px;
  }

  .page-header {
    flex-direction: column;
    align-items: stretch;
    gap: 14px;
    margin-bottom: 18px;
  }

  .quota-card {
    max-width: 100%;
  }

  .page-title {
    font-size: 26px;
  }

  .quota-card,
  .elective-catalog-card {
    border-radius: var(--wa-radius-lg);
  }

  .quota-card :deep(.el-card__body),
  .elective-catalog-card :deep(.el-card__body) {
    padding: 16px;
  }

  .elective-catalog-card :deep(.el-table) {
    display: none;
  }

  .catalog-mobile-list {
    display: block;
    min-width: 0;
  }

  .catalog-mobile-item {
    min-width: 0;
  }

  .course-grid {
    grid-template-columns: repeat(auto-fill, minmax(min(280px, 100%), 1fr));
  }

  .course-grid > article.course-card {
    min-width: 0;
  }

  .course-section {
    border-radius: var(--wa-radius-xl);
    padding: 20px;
  }

  .course-card {
    border-radius: var(--wa-radius-xl);
    padding: 18px;
  }

  .course-card-cover {
    margin: -18px -18px 14px;
    border-radius: var(--wa-radius-xl) var(--wa-radius-xl) 0 0;
  }

  .course-card-header {
    flex-direction: column;
    align-items: stretch;
  }

  .course-time-panel__header,
  .course-time-panel__fields {
    grid-template-columns: 1fr;
    flex-direction: column;
  }

  .course-tags {
    justify-content: flex-start;
  }

  .course-actions {
    justify-content: stretch;
  }

  .course-actions :deep(.el-button) {
    width: 100%;
  }
}
</style>
