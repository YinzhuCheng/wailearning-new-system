<template>
  <div class="logs-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>操作日志</span>
        </div>
      </template>

      <el-row :gutter="20" class="stats-row">
        <el-col :span="6">
          <el-statistic title="今日日志" :value="stats.today">
            <template #prefix>
              <el-icon><Calendar /></el-icon>
            </template>
          </el-statistic>
        </el-col>
        <el-col :span="6">
          <el-statistic title="总日志数" :value="stats.total">
            <template #prefix>
              <el-icon><Document /></el-icon>
            </template>
          </el-statistic>
        </el-col>
      </el-row>

      <el-divider />

      <el-form :inline="true" class="filter-form">
        <el-form-item label="操作类型">
          <el-select v-model="filters.action" placeholder="全部" clearable @change="handleFilter">
            <el-option label="登录" value="登录" />
            <el-option label="创建" value="创建" />
            <el-option label="修改" value="修改" />
            <el-option label="删除" value="删除" />
            <el-option label="导出" value="导出" />
          </el-select>
        </el-form-item>
        <el-form-item label="操作对象">
          <el-select v-model="filters.target_type" placeholder="全部" clearable @change="handleFilter">
            <el-option label="用户" value="用户" />
            <el-option label="学生" value="学生" />
            <el-option label="成绩" value="成绩" />
            <el-option label="考勤" value="考勤" />
            <el-option label="班级" value="班级" />
            <el-option label="认证" value="认证" />
          </el-select>
        </el-form-item>
        <el-form-item label="日期范围">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            @change="handleDateChange"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleFilter">查询</el-button>
          <el-button @click="resetFilter">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="logs" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column label="操作时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作人" width="120">
          <template #default="{ row }">
            <el-tag size="small">{{ row.username || '系统' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作类型" width="100">
          <template #default="{ row }">
            <el-tag :type="getActionType(row.action)" size="small">
              {{ row.action }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作对象" width="100">
          <template #default="{ row }">
            <el-tag type="info" size="small">
              {{ row.target_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作详情" min-width="200">
          <template #default="{ row }">
            <div v-if="row.target_name">
              <strong>{{ row.target_name }}</strong>
            </div>
            <div class="details-text">{{ row.details }}</div>
          </template>
        </el-table-column>
        <el-table-column label="结果" width="80">
          <template #default="{ row }">
            <el-tag :type="row.result === 'success' ? 'success' : 'danger'" size="small">
              {{ row.result === 'success' ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="IP地址" width="130">
          <template #default="{ row }">
            <span class="ip-text">{{ row.ip_address || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          :page-sizes="[10, 20, 50, 100]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Calendar, Document } from '@element-plus/icons-vue'
import axios from 'axios'

const api = axios.create({
  baseURL: '/api'
})

api.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

const logs = ref([])
const loading = ref(false)
const stats = ref({
  today: 0,
  total: 0
})
const filters = ref({
  action: '',
  target_type: '',
  start_date: '',
  end_date: ''
})
const dateRange = ref([])
const pagination = ref({
  page: 1,
  page_size: 20,
  total: 0
})

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

const getActionType = (action) => {
  const typeMap = {
    '登录': 'success',
    '创建': 'primary',
    '修改': 'warning',
    '删除': 'danger',
    '导出': 'info'
  }
  return typeMap[action] || 'info'
}

const fetchLogs = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.value.page,
      page_size: pagination.value.page_size
    }
    if (filters.value.action) params.action = filters.value.action
    if (filters.value.target_type) params.target_type = filters.value.target_type
    if (filters.value.start_date) params.start_date = filters.value.start_date
    if (filters.value.end_date) params.end_date = filters.value.end_date

    const response = await api.get('/logs', { params })
    logs.value = response.data.data
    pagination.value.total = response.data.total
  } catch (error) {
    ElMessage.error('获取日志失败')
  } finally {
    loading.value = false
  }
}

const fetchStats = async () => {
  try {
    const response = await api.get('/logs/stats/summary')
    stats.value = response.data
  } catch (error) {
    console.error('获取统计失败', error)
  }
}

const handleFilter = () => {
  pagination.value.page = 1
  fetchLogs()
}

const handleDateChange = (val) => {
  if (val && val.length === 2) {
    filters.value.start_date = val[0]
    filters.value.end_date = val[1]
  } else {
    filters.value.start_date = ''
    filters.value.end_date = ''
  }
  handleFilter()
}

const resetFilter = () => {
  filters.value = {
    action: '',
    target_type: '',
    start_date: '',
    end_date: ''
  }
  dateRange.value = []
  pagination.value.page = 1
  fetchLogs()
}

const handlePageChange = (page) => {
  pagination.value.page = page
  fetchLogs()
}

const handleSizeChange = (size) => {
  pagination.value.page_size = size
  pagination.value.page = 1
  fetchLogs()
}

onMounted(() => {
  fetchLogs()
  fetchStats()
})
</script>

<style scoped>
.logs-container {
  padding: 20px;
}

.card-header {
  font-size: 18px;
  font-weight: bold;
}

.stats-row {
  margin-bottom: 20px;
}

.filter-form {
  margin-bottom: 20px;
}

.details-text {
  color: #666;
  font-size: 12px;
  margin-top: 4px;
}

.ip-text {
  font-size: 12px;
  color: #999;
}

.pagination-wrapper {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
