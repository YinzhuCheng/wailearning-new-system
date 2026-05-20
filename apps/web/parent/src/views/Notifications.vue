<template>
  <div class="notifications-container">
    <div class="header">
      <el-button text @click="router.push('/home')">
        <el-icon><ArrowLeft /></el-icon>
      </el-button>
      <h2>班级通知</h2>
      <span class="count">{{ total }}条</span>
    </div>

    <div class="notification-list" v-loading="loading">
      <div
        class="notification-card"
        v-for="item in notifications"
        :key="item.id"
        @click="viewDetail(item)"
      >
        <div class="card-header">
          <div class="tags">
            <el-tag v-if="item.is_pinned" type="warning" size="small">置顶</el-tag>
            <el-tag size="small" :type="getPriorityType(item.priority)">
              {{ getPriorityText(item.priority) }}
            </el-tag>
          </div>
          <span class="date">{{ formatDate(item.created_at) }}</span>
        </div>
        <h3 class="title">{{ item.title }}</h3>
        <p class="creator">发布人：{{ item.creator_name }}</p>
      </div>

      <el-empty v-if="notifications.length === 0 && !loading" description="暂无通知" />

      <el-pagination
        v-if="total > 0"
        v-model:current-page="page"
        :total="total"
        :page-size="pageSize"
        layout="prev, pager, next"
        @current-change="fetchNotifications"
        style="margin: 20px 0; justify-content: center"
      />
    </div>

    <el-drawer v-model="detailVisible" :title="currentNotification?.title" size="100%">
      <div class="detail-content" v-if="currentNotification">
        <div class="detail-header">
          <div class="detail-tags">
            <el-tag v-if="currentNotification.is_pinned" type="warning">置顶</el-tag>
            <el-tag :type="getPriorityType(currentNotification.priority)">
              {{ getPriorityText(currentNotification.priority) }}
            </el-tag>
          </div>
          <p class="detail-info">
            <span>发布人：{{ currentNotification.creator_name }}</span>
            <span>{{ formatDate(currentNotification.created_at) }}</span>
          </p>
        </div>
        <el-divider />
        <div class="detail-body">
          {{ currentNotification.content || '暂无内容' }}
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import api from '@/api'
import { handleParentApiError } from '@/session'

const router = useRouter()
const loading = ref(false)
const parentCode = localStorage.getItem('parent_code')

const notifications = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const detailVisible = ref(false)
const currentNotification = ref(null)

const fetchNotifications = async () => {
  loading.value = true
  try {
    const data = await api.getNotifications(parentCode, {
      page: page.value,
      page_size: pageSize.value
    })
    notifications.value = data.notifications
    total.value = data.total
  } catch (e) {
    if (handleParentApiError(e)) return
    console.error('获取通知失败', e)
  } finally {
    loading.value = false
  }
}

const viewDetail = (item) => {
  currentNotification.value = item
  detailVisible.value = true
}

const getPriorityType = (priority) => {
  const map = { normal: 'info', important: 'warning', urgent: 'danger' }
  return map[priority] || 'info'
}

const getPriorityText = (priority) => {
  const map = { normal: '普通', important: '重要', urgent: '紧急' }
  return map[priority] || '普通'
}

const formatDate = (date) => {
  if (!date) return '-'
  return new Date(date).toLocaleDateString('zh-CN')
}

onMounted(() => {
  fetchNotifications()
})
</script>

<style scoped>
.notifications-container {
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

.notification-list {
  padding: 16px;
}

.notification-card {
  background: white;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  cursor: pointer;
  transition: transform 0.2s;
}

.notification-card:active {
  transform: scale(0.98);
}

.notification-card.is-pinned {
  border-left: 4px solid #e6a23c;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.tags {
  display: flex;
  gap: 8px;
}

.date {
  font-size: 12px;
  color: #909399;
}

.title {
  margin: 0 0 8px;
  font-size: 16px;
  color: #303133;
  line-height: 1.4;
}

.creator {
  margin: 0;
  font-size: 13px;
  color: #909399;
}

.detail-content {
  padding: 0 16px;
}

.detail-header {
  margin-bottom: 16px;
}

.detail-tags {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.detail-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: #909399;
}

.detail-body {
  font-size: 15px;
  line-height: 1.8;
  color: #606266;
  white-space: pre-wrap;
}
</style>
