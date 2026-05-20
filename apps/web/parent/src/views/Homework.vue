<template>
  <div class="homework-container">
    <div class="header">
      <el-button text @click="router.push('/home')">
        <el-icon><ArrowLeft /></el-icon>
      </el-button>
      <h2>班级作业</h2>
      <span class="count">{{ total }}条</span>
    </div>

    <div class="homework-list" v-loading="loading">
      <div
        class="homework-card"
        v-for="item in homeworks"
        :key="item.id"
        @click="viewDetail(item)"
      >
        <div class="card-header">
          <h3 class="title">{{ item.title }}</h3>
          <el-tag size="small" :type="isOverdue(item.due_date) ? 'danger' : 'success'">
            {{ isOverdue(item.due_date) ? '已截止' : '进行中' }}
          </el-tag>
        </div>
        <div class="card-info">
          <span v-if="item.subject_name">
            <el-icon><Collection /></el-icon> {{ item.subject_name }}
          </span>
          <span v-if="item.due_date">
            <el-icon><Clock /></el-icon> {{ formatDate(item.due_date) }}
          </span>
        </div>
        <p class="creator">发布人：{{ item.creator_name }}</p>
      </div>

      <el-empty v-if="homeworks.length === 0 && !loading" description="暂无作业" />

      <el-pagination
        v-if="total > 0"
        v-model:current-page="page"
        :total="total"
        :page-size="pageSize"
        layout="prev, pager, next"
        @current-change="fetchHomework"
        style="margin: 20px 0; justify-content: center"
      />
    </div>

    <el-drawer v-model="detailVisible" :title="currentHomework?.title" size="100%">
      <div class="detail-content" v-if="currentHomework">
        <div class="detail-info">
          <el-tag v-if="currentHomework.subject_name" type="info">{{ currentHomework.subject_name }}</el-tag>
          <el-tag :type="isOverdue(currentHomework.due_date) ? 'danger' : 'success'">
            {{ isOverdue(currentHomework.due_date) ? '已截止' : '进行中' }}
          </el-tag>
        </div>
        <p class="detail-meta">
          <span>截止日期：{{ formatDate(currentHomework.due_date) }}</span>
          <span>发布人：{{ currentHomework.creator_name }}</span>
        </p>
        <el-divider />
        <div class="detail-body">
          <h4>作业内容：</h4>
          <p>{{ currentHomework.content || '暂无内容' }}</p>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Collection, Clock } from '@element-plus/icons-vue'
import api from '@/api'
import { handleParentApiError } from '@/session'

const router = useRouter()
const loading = ref(false)
const parentCode = localStorage.getItem('parent_code')

const homeworks = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const detailVisible = ref(false)
const currentHomework = ref(null)

const fetchHomework = async () => {
  loading.value = true
  try {
    const data = await api.getHomework(parentCode, {
      page: page.value,
      page_size: pageSize.value
    })
    homeworks.value = data.homeworks
    total.value = data.total
  } catch (e) {
    if (handleParentApiError(e)) return
    console.error('获取作业失败', e)
  } finally {
    loading.value = false
  }
}

const viewDetail = (item) => {
  currentHomework.value = item
  detailVisible.value = true
}

const isOverdue = (dueDate) => {
  if (!dueDate) return false
  return new Date(dueDate) < new Date()
}

const formatDate = (date) => {
  if (!date) return '-'
  return new Date(date).toLocaleString('zh-CN')
}

onMounted(() => {
  fetchHomework()
})
</script>

<style scoped>
.homework-container {
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
  flex: 1;
  margin: 0;
  font-size: 18px;
}

.header .count {
  font-size: 13px;
  color: #909399;
}

.homework-list {
  padding: 16px;
}

.homework-card {
  background: white;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  cursor: pointer;
  transition: transform 0.2s;
}

.homework-card:active {
  transform: scale(0.98);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 10px;
}

.title {
  margin: 0;
  font-size: 16px;
  color: #303133;
  line-height: 1.4;
  flex: 1;
  margin-right: 12px;
}

.card-info {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 13px;
  color: #606266;
  margin-bottom: 8px;
}

.card-info span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.creator {
  margin: 0;
  font-size: 13px;
  color: #909399;
}

.detail-content {
  padding: 0 16px;
}

.detail-info {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.detail-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: #909399;
  margin: 0;
}

.detail-body h4 {
  margin: 0 0 12px;
  font-size: 15px;
  color: #303133;
}

.detail-body p {
  margin: 0;
  font-size: 15px;
  line-height: 1.8;
  color: #606266;
  white-space: pre-wrap;
}
</style>
