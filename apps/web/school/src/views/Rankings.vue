<template>
  <div class="rankings-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">班级排名</h1>
        <p class="page-subtitle">
          {{ selectedCourse ? `${selectedCourse.name} · ${selectedCourse.class_name || '未分配班级'}` : '请先选择课程后查看排名。' }}
        </p>
      </div>
      <div class="header-actions">
        <el-select v-model="semester" placeholder="选择学期" clearable style="width: 220px" @change="loadData">
          <el-option v-for="item in semesters" :key="item.id" :label="item.name" :value="item.name" />
        </el-select>
      </div>
    </div>

    <el-empty v-if="!selectedCourse" description="请先选择一门课程。" />

    <template v-else>
      <el-row :gutter="20">
        <el-col :span="8">
          <el-card shadow="never">
            <template #header>课程班级平均分</template>
            <el-empty v-if="!classRankings.length" description="暂无班级排名数据" />
            <el-table v-else :data="classRankings" size="small">
              <el-table-column prop="rank" label="排名" width="80" />
              <el-table-column prop="class_name" label="班级" />
              <el-table-column prop="avg_score" label="平均分" width="100" />
            </el-table>
          </el-card>
        </el-col>
        <el-col :span="16">
          <el-card shadow="never">
            <template #header>学生排名</template>
            <el-empty v-if="!studentRankings.length" description="暂无学生排名数据" />
            <el-table v-else :data="studentRankings">
              <el-table-column prop="rank" label="排名" width="80" />
              <el-table-column prop="student_name" label="学生" min-width="180" />
              <el-table-column prop="class_name" label="班级" width="180" />
              <el-table-column prop="avg_score" label="平均分" width="120" />
            </el-table>
          </el-card>
        </el-col>
      </el-row>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'

import api from '@/api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()

const semester = ref('')
const semesters = ref([])
const classRankings = ref([])
const studentRankings = ref([])

const selectedCourse = computed(() => userStore.selectedCourse)

const buildParams = () => ({
  semester: semester.value || undefined,
  subject_id: selectedCourse.value?.id
})

const loadSemesters = async () => {
  semesters.value = await api.semesters.list()
}

const loadData = async () => {
  if (!selectedCourse.value) {
    classRankings.value = []
    studentRankings.value = []
    return
  }
  const [classData, studentData] = await Promise.all([
    api.dashboard.getClassRankings(buildParams()),
    api.dashboard.getStudentRankings(buildParams())
  ])
  classRankings.value = classData || []
  studentRankings.value = studentData || []
}

onMounted(async () => {
  await loadSemesters()
  await loadData()
})

watch(selectedCourse, () => {
  loadData()
})
</script>

<style scoped>
.rankings-page {
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
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
  }
}
</style>
