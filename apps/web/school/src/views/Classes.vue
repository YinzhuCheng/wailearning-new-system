<template>
  <div class="classes">
    <div class="page-header">
      <h1 class="page-title">班级管理</h1>
      <el-button type="primary" @click="handleAdd">
        <el-icon><Plus /></el-icon>
        新增班级
      </el-button>
    </div>

    <div class="table-container">
      <el-table :data="classes" style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="班级名称" />
        <el-table-column prop="grade" label="年级" />
        <el-table-column prop="student_count" label="学生人数" />
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280">
          <template #default="{ row }">
            <el-button type="success" size="small" data-testid="classes-open-roster" @click="goClassRoster(row)">
              花名册
            </el-button>
            <el-button type="primary" size="small" @click="handleEdit(row)">编辑</el-button>
            <el-button type="danger" size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑班级' : '新增班级'" width="500px">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="80px">
        <el-form-item label="班级名称" prop="name">
          <el-input v-model="form.name" placeholder="如: 高一(1)班" />
        </el-form-item>
        <el-form-item label="年级" prop="grade">
          <el-input-number v-model="grade" :min="1" :max="12" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import api from '@/api'

const router = useRouter()

const classes = ref([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const editingId = ref(null)
const formRef = ref(null)

const form = reactive({
  name: ''
})

const grade = ref(1)

const rules = {
  name: [{ required: true, message: '请输入班级名称', trigger: 'blur' }]
}

const loadClasses = async () => {
  const data = await api.classes.list()
  classes.value = data || []
}

const goClassRoster = row => {
  if (!row?.id) {
    return
  }
  router.push({ path: '/students', query: { class_id: String(row.id) } })
}

const handleAdd = () => {
  isEdit.value = false
  editingId.value = null
  form.name = ''
  grade.value = 1
  dialogVisible.value = true
}

const handleEdit = (row) => {
  isEdit.value = true
  editingId.value = row.id
  form.name = row.name
  grade.value = row.grade
  dialogVisible.value = true
}

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm('确定删除该班级吗?', '提示', { type: 'warning' })
    await api.classes.delete(row.id)
    ElMessage.success('删除成功')
    loadClasses()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

const handleSubmit = async () => {
  await formRef.value.validate()
  
  const data = {
    name: form.name,
    grade: grade.value
  }
  
  try {
    if (isEdit.value) {
      await api.classes.update(editingId.value, data)
      ElMessage.success('修改成功')
    } else {
      await api.classes.create(data)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    loadClasses()
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleDateString('zh-CN')
}

onMounted(() => {
  loadClasses()
})
</script>

<style scoped>
.classes {
  width: min(100%, 1180px);
  margin: 0 auto;
  padding: 24px;
  min-width: 0;
  overflow-x: hidden;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
}

.page-title {
  margin: 0;
  font-size: 28px;
  color: var(--wa-color-text);
}

.table-container {
  overflow-x: auto;
  border: 1px solid color-mix(in srgb, var(--wa-border-subtle) 86%, transparent);
  border-radius: var(--wa-radius-lg);
  background: var(--wa-color-surface);
  box-shadow: var(--wa-shadow-surface);
}

.table-container :deep(.el-table) {
  min-width: 900px;
}

@media (max-width: 768px) {
  .classes {
    padding: 16px;
  }

  .page-header {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
