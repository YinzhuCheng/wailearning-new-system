<template>
  <div class="student-hw-page" v-loading="loading">
    <div class="page-header">
      <div>
        <h1 class="page-title">学生作业一览</h1>
        <p class="page-subtitle">
          {{ selectedCourse ? `${selectedCourse.name}` : '请先选择课程' }}
          <span v-if="studentLabel"> · {{ studentLabel }}</span>
        </p>
      </div>
      <div class="header-actions">
        <el-select
          v-model="studentId"
          filterable
          placeholder="选择学生"
          style="width: 260px"
          :loading="studentsLoading"
          @visible-change="v => v && loadStudents()"
        >
          <el-option
            v-for="s in students"
            :key="s.student_id"
            :label="`${s.student_name || ''} (${s.student_no || s.student_id})`"
            :value="s.student_id"
          />
        </el-select>
        <el-button @click="router.push('/homework')">返回作业管理</el-button>
      </div>
    </div>

    <el-empty v-if="!selectedCourse" description="请先选择一门课程" />

    <el-card v-else shadow="never">
      <el-table :data="rows" v-loading="loading">
        <el-table-column prop="title" label="作业" min-width="200" show-overflow-tooltip />
        <el-table-column label="截止时间" width="170">
          <template #default="{ row }">{{ formatDate(row.due_date) }}</template>
        </el-table-column>
        <el-table-column label="提交时间" width="170">
          <template #default="{ row }">{{ row.submitted_at ? formatDate(row.submitted_at) : '—' }}</template>
        </el-table-column>
        <el-table-column label="分数" width="100">
          <template #default="{ row }">
            {{ row.review_score != null ? formatScore(row.review_score) : '—' }}
          </template>
        </el-table-column>
        <el-table-column label="任务" width="120">
          <template #default="{ row }">
            <span v-if="row.latest_task_status">{{ row.latest_task_status }}</span>
            <span v-else class="muted-text">—</span>
          </template>
        </el-table-column>
        <el-table-column label="申诉" width="100">
          <template #default="{ row }">
            <el-tag
              v-if="row.appeal_status"
              :type="getAppealStatusTagType(row.appeal_status)"
              size="small"
            >
              {{ getAppealStatusLabel(row.appeal_status) }}
            </el-tag>
            <span v-else class="muted-text">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              link
              size="small"
              :disabled="!row.homework_id"
              @click="goSubmissions(row.homework_id)"
            >
              作业详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager-wrap">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="loadRows"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import api from '@/api'
import { useUserStore } from '@/stores/user'
import { getAppealStatusLabel, getAppealStatusTagType } from '@/utils/appealNotificationActions'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const loading = ref(false)
const studentsLoading = ref(false)
const students = ref([])
const studentId = ref(route.query.student_id ? Number(route.query.student_id) : null)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20

const selectedCourse = computed(() => userStore.selectedCourse)

const studentLabel = computed(() => {
  const s = students.value.find(x => x.student_id === studentId.value)
  if (!s) return ''
  return `${s.student_name || ''} ${s.student_no ? `(${s.student_no})` : ''}`.trim()
})

const formatScore = value => {
  const n = Number(value)
  if (!Number.isFinite(n)) return '--'
  return Number.isInteger(n) ? `${n}` : n.toFixed(1)
}

const formatDate = value => {
  if (!value) return '未设置'
  return new Date(value).toLocaleString('zh-CN')
}

const routeStudentId = () => {
  const id = Number(route.query.student_id)
  return Number.isFinite(id) && id > 0 ? id : null
}

const ensureDefaultStudent = () => {
  if (!students.value.length) {
    studentId.value = null
    return
  }
  const requestedStudentId = routeStudentId()
  if (requestedStudentId && students.value.some(s => Number(s.student_id) === requestedStudentId)) {
    studentId.value = requestedStudentId
    return
  }
  const currentOk = students.value.some(s => s.student_id === studentId.value)
  if (!currentOk) {
    studentId.value = students.value[0].student_id
  }
}

const loadStudents = async () => {
  if (!selectedCourse.value?.id) return
  studentsLoading.value = true
  try {
    students.value = await api.homework.listCourseStudents(selectedCourse.value.id)
    ensureDefaultStudent()
  } finally {
    studentsLoading.value = false
  }
}

const loadRows = async () => {
  if (!selectedCourse.value?.id || !studentId.value) {
    rows.value = []
    total.value = 0
    return
  }
  loading.value = true
  try {
    const res = await api.homework.listStudentHomeworks(selectedCourse.value.id, studentId.value, {
      page: page.value,
      page_size: pageSize
    })
    rows.value = res?.data || []
    total.value = Number(res?.total || 0)
  } finally {
    loading.value = false
  }
}

const goSubmissions = hid => {
  router.push({ path: `/homework/${hid}/submissions`, query: { student_id: studentId.value } })
}

onMounted(async () => {
  await loadStudents()
})

watch(
  () => selectedCourse.value?.id,
  async () => {
    studentId.value = null
    rows.value = []
    total.value = 0
    await loadStudents()
  }
)

watch(
  () => route.query.student_id,
  () => {
    ensureDefaultStudent()
  }
)

watch(studentId, () => {
  page.value = 1
  loadRows()
})

watch(page, () => loadRows())
</script>

<style scoped>
.student-hw-page {
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
.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.muted-text {
  color: #94a3b8;
  font-size: 13px;
}
.pager-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
