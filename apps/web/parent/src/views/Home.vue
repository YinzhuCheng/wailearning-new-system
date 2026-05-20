<template>
  <div class="home-container">
    <div class="header">
      <div class="user-info">
        <div class="avatar">{{ studentName?.charAt(0) }}</div>
        <div class="info">
          <h2>{{ studentName }}</h2>
          <p>{{ className }}</p>
        </div>
      </div>
      <el-button text @click="handleLogout">
        <el-icon><SwitchButton /></el-icon>
      </el-button>
    </div>

    <div class="stats-grid">
      <div class="stat-card" @click="router.push('/scores')">
        <div class="stat-icon blue">
          <el-icon size="24"><TrendCharts /></el-icon>
        </div>
        <div class="stat-content">
          <p class="stat-label">平均成绩</p>
          <p class="stat-value">{{ stats.average_score || '-' }}</p>
        </div>
      </div>

      <div class="stat-card" @click="router.push('/home')">
        <div class="stat-icon green">
          <el-icon size="24"><Calendar /></el-icon>
        </div>
        <div class="stat-content">
          <p class="stat-label">出勤率</p>
          <p class="stat-value">{{ stats.attendance_rate || '-' }}%</p>
        </div>
      </div>
    </div>

    <div class="menu-grid">
      <div class="menu-card" @click="router.push('/scores')">
        <el-icon size="32" color="#409eff"><TrendCharts /></el-icon>
        <span>成绩查询</span>
      </div>
      <div class="menu-card" @click="router.push('/notifications')">
        <el-icon size="32" color="#67c23a"><Bell /></el-icon>
        <span>班级通知</span>
      </div>
      <div class="menu-card" @click="router.push('/homework')">
        <el-icon size="32" color="#e6a23c"><Document /></el-icon>
        <span>班级作业</span>
      </div>
    </div>

    <div class="recent-section">
      <div class="section-header" @click="router.push('/scores')">
        <h3>📊 最近成绩</h3>
        <span>查看全部 <el-icon><ArrowRight /></el-icon></span>
      </div>

      <div class="score-list" v-if="recentScores.length > 0">
        <div class="score-item" v-for="item in recentScores" :key="item.id">
          <div class="score-info">
            <span class="subject">{{ item.subject_name }}</span>
            <span class="exam-type">{{ getExamTypeText(item.exam_type) }}</span>
          </div>
          <div class="score-value">
            <el-tag :type="getScoreType(item.score)">{{ item.score }}</el-tag>
          </div>
        </div>
      </div>

      <el-empty v-else description="暂无成绩记录" :image-size="80" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Bell, Document, TrendCharts, Calendar, SwitchButton, ArrowRight } from '@element-plus/icons-vue'
import api from '@/api'
import { clearParentSession, handleParentApiError } from '@/session'

const router = useRouter()
const parentCode = localStorage.getItem('parent_code')
const studentName = localStorage.getItem('student_name')
const className = localStorage.getItem('class_name')
const stats = ref({})
const recentScores = ref([])

const fetchStats = async () => {
  try {
    const data = await api.getStats(parentCode)
    stats.value = data
  } catch (e) {
    if (handleParentApiError(e)) return
    console.error('获取统计失败', e)
  }
}

const fetchRecentScores = async () => {
  try {
    const data = await api.getScores(parentCode, { page: 1, page_size: 5 })
    recentScores.value = data.scores
  } catch (e) {
    if (handleParentApiError(e)) return
    console.error('获取成绩失败', e)
  }
}

const handleLogout = () => {
  clearParentSession()
  router.push('/login')
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

onMounted(() => {
  fetchStats()
  fetchRecentScores()
})
</script>

<style scoped>
.home-container {
  min-height: 100vh;
  background: #f5f7fa;
  padding-bottom: 20px;
}

.header {
  background: linear-gradient(135deg, #409eff 0%, #67c23a 100%);
  padding: 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.avatar {
  width: 48px;
  height: 48px;
  background: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: bold;
  color: #409eff;
}

.info h2 {
  color: white;
  font-size: 18px;
  margin: 0 0 4px;
}

.info p {
  color: rgba(255, 255, 255, 0.8);
  font-size: 13px;
  margin: 0;
}

.header .el-button {
  color: white;
  font-size: 20px;
}

.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  padding: 16px;
  margin-top: -20px;
}

.stat-card {
  background: white;
  border-radius: 12px;
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
}

.stat-icon.blue { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
.stat-icon.green { background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); }

.stat-content {
  flex: 1;
}

.stat-label {
  color: #909399;
  font-size: 12px;
  margin: 0 0 4px;
}

.stat-value {
  font-size: 20px;
  font-weight: bold;
  color: #303133;
  margin: 0;
}

.menu-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding: 0 16px;
}

.menu-card {
  background: white;
  border-radius: 12px;
  padding: 20px 10px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  cursor: pointer;
  transition: transform 0.2s;
}

.menu-card:active {
  transform: scale(0.95);
}

.menu-card span {
  font-size: 13px;
  color: #606266;
}

.recent-section {
  margin: 20px 16px 0;
  background: white;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header h3 {
  margin: 0;
  font-size: 16px;
  color: #303133;
}

.section-header span {
  font-size: 13px;
  color: #909399;
  display: flex;
  align-items: center;
  gap: 4px;
}

.score-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.score-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 8px;
}

.score-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.subject {
  font-size: 15px;
  color: #303133;
  font-weight: 500;
}

.exam-type {
  font-size: 12px;
  color: #909399;
}

.score-value {
  font-size: 18px;
}
</style>
