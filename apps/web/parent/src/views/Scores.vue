<template>
  <div class="scores-container">
    <div class="header">
      <el-button text @click="router.push('/home')">
        <el-icon><ArrowLeft /></el-icon>
      </el-button>
      <h2>成绩查询</h2>
    </div>
    <div class="filter-row">
      <el-select v-model="semester" placeholder="选择学期" @change="fetchScores" size="default" style="width: 100%;">
        <el-option label="全部学期" value="" />
        <el-option label="2025-2" value="2025-2" />
        <el-option label="2025-1" value="2025-1" />
        <el-option label="2024-2" value="2024-2" />
        <el-option label="2024-1" value="2024-1" />
      </el-select>
    </div>

    <div class="stats-row">
      <div class="stat-item">
        <span class="value">{{ totalExams }}</span>
        <span class="label">考试次数</span>
      </div>
      <div class="stat-item">
        <span class="value">{{ averageScore }}</span>
        <span class="label">平均成绩</span>
      </div>
    </div>

    <div class="score-list" v-loading="loading">
      <div class="score-card" v-for="item in scores" :key="item.id">
        <div class="score-header">
          <span class="subject">{{ item.subject_name }}</span>
          <el-tag size="small" :type="getScoreType(item.score)">{{ item.score }}</el-tag>
        </div>
        <div class="score-info">
          <span>{{ getExamTypeText(item.exam_type) }}</span>
          <span>{{ formatDate(item.exam_date) }}</span>
          <span>{{ item.semester }}</span>
        </div>
      </div>

      <el-empty v-if="scores.length === 0 && !loading" description="暂无成绩记录" />

      <el-pagination
        v-if="total > 0"
        v-model:current-page="page"
        :total="total"
        :page-size="pageSize"
        layout="prev, pager, next"
        @current-change="fetchScores"
        style="margin-top: 20px; justify-content: center"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import api from '@/api'
import { handleParentApiError } from '@/session'

const router = useRouter()
const loading = ref(false)
const parentCode = localStorage.getItem('parent_code')

const scores = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const semester = ref('')

const totalExams = computed(() => total.value)
const averageScore = computed(() => {
  if (scores.value.length === 0) return '-'
  const validScores = scores.value.filter(s => s.score)
  if (validScores.length === 0) return '-'
  const avg = validScores.reduce((sum, s) => sum + s.score, 0) / validScores.length
  return avg.toFixed(1)
})

const fetchScores = async () => {
  loading.value = true
  try {
    const data = await api.getScores(parentCode, {
      semester: semester.value,
      page: page.value,
      page_size: pageSize.value
    })
    scores.value = data.scores
    total.value = data.total
  } catch (e) {
    if (handleParentApiError(e)) return
    console.error('获取成绩失败', e)
  } finally {
    loading.value = false
  }
}

const getScoreType = (score) => {
  if (score >= 90) return 'success'
  if (score >= 80) return ''
  if (score >= 60) return 'warning'
  return 'danger'
}

const getExamTypeText = (type) => {
  const map = { midterm: '期中', final: '期末', quiz: '测验', exam: '考试' }
  return map[type] || type
}

const formatDate = (date) => {
  if (!date) return '-'
  return new Date(date).toLocaleDateString('zh-CN')
}

onMounted(() => {
  fetchScores()
})
</script>

<style scoped>
.scores-container {
  min-height: 100vh;
  background: #f5f7fa;
}

.header {
  background: white;
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  position: sticky;
  top: 0;
  z-index: 10;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.header h2 {
  margin: 0;
  font-size: 18px;
}

.filter-row {
  background: white;
  padding: 0 16px 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.stats-row {
  display: flex;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 24px 20px;
  margin-top: 0;
}

.stat-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  color: white;
  position: relative;
}

.stat-item:first-child::after {
  content: '';
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 1px;
  height: 40px;
  background: rgba(255, 255, 255, 0.3);
}

.stat-item .value {
  font-size: 32px;
  font-weight: bold;
  line-height: 1.2;
}

.stat-item .label {
  font-size: 14px;
  opacity: 0.9;
  margin-top: 6px;
}

.score-list {
  padding: 16px;
}

.score-card {
  background: white;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.score-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.score-header .subject {
  font-size: 16px;
  font-weight: 500;
  color: #303133;
}

.score-info {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: #909399;
}
</style>
