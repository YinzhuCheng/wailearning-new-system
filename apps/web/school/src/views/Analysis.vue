<template>
  <div class="analysis-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">数据分析</h1>
        <p class="page-subtitle">
          {{ selectedCourse ? `${selectedCourse.name} · ${selectedCourse.class_name || '未分配班级'}` : '请先选择课程后查看数据分析。' }}
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
        <el-col :span="12">
          <el-card shadow="never">
            <template #header>考试类型趋势</template>
            <div ref="trendChartRef" class="chart-box"></div>
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="never">
            <template #header>课程成绩摘要</template>
            <el-table :data="subjectAnalysis">
              <el-table-column prop="subject_name" label="课程" />
              <el-table-column prop="avg_score" label="平均分" width="120" />
              <el-table-column prop="max_score" label="最高分" width="120" />
              <el-table-column prop="min_score" label="最低分" width="120" />
              <el-table-column prop="count" label="记录数" width="120" />
            </el-table>
          </el-card>
        </el-col>
      </el-row>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

import api from '@/api'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()

const semester = ref('')
const semesters = ref([])
const subjectAnalysis = ref([])
const trendChartRef = ref(null)
let trendChart = null

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
    subjectAnalysis.value = []
    updateTrendChart({})
    return
  }
  const [trends, analysis] = await Promise.all([
    api.dashboard.getTrends(buildParams()),
    api.dashboard.getSubjectAnalysis(buildParams())
  ])
  subjectAnalysis.value = analysis || []
  updateTrendChart(trends || {})
}

const updateTrendChart = data => {
  if (!trendChart) return
  const examTypes = Object.keys(data)
  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: examTypes
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100
    },
    series: [{
      type: 'line',
      smooth: true,
      data: examTypes.map(key => data[key]?.avg || 0),
      areaStyle: {
        color: 'rgba(37, 99, 235, 0.12)'
      },
      lineStyle: {
        color: '#2563eb',
        width: 3
      },
      itemStyle: {
        color: '#2563eb'
      }
    }]
  })
}

onMounted(async () => {
  trendChart = echarts.init(trendChartRef.value)
  await loadSemesters()
  await loadData()
  window.addEventListener('resize', () => trendChart?.resize())
})

watch(selectedCourse, () => {
  loadData()
})
</script>

<style scoped>
.analysis-page {
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

.chart-box {
  height: 360px;
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
  }
}
</style>
