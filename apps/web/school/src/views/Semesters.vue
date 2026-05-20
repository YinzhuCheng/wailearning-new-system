<template>
  <div class="semesters">
    <div class="page-header">
      <h1 class="page-title">学期管理</h1>
      <el-button type="primary" @click="handleAdd">
        <el-icon><Plus /></el-icon>
        新增学期
      </el-button>
    </div>

    <div class="table-container">
      <el-table :data="semesters" style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="学期名称" />
        <el-table-column prop="year" label="年份" />
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" @click="handleEdit(row)">编辑</el-button>
            <el-button type="danger" size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="400px" @closed="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="学期名称" prop="name">
          <el-input v-model="form.name" placeholder="如：2025-1" />
        </el-form-item>
        <el-form-item label="年份" prop="year">
          <el-input-number v-model="form.year" :min="2020" :max="2035" />
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
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import api from '@/api'

const semesters = ref([])
const dialogVisible = ref(false)
const formRef = ref(null)
const editingSemesterId = ref(null)

const createDefaultForm = () => ({
  name: '',
  year: new Date().getFullYear()
})

const form = reactive(createDefaultForm())

const dialogTitle = computed(() => (editingSemesterId.value ? '编辑学期' : '新增学期'))

const rules = {
  name: [{ required: true, message: '请输入学期名称', trigger: 'blur' }],
  year: [{ required: true, message: '请选择年份', trigger: 'change' }]
}

const resetForm = () => {
  Object.assign(form, createDefaultForm())
  editingSemesterId.value = null
  formRef.value?.clearValidate()
}

const loadSemesters = async () => {
  semesters.value = await api.semesters.list()
}

const openDialog = async () => {
  dialogVisible.value = true
  await nextTick()
  formRef.value?.clearValidate()
}

const handleAdd = async () => {
  resetForm()
  await openDialog()
}

const handleEdit = async row => {
  form.name = row.name
  form.year = row.year
  editingSemesterId.value = row.id
  await openDialog()
}

const handleDelete = async row => {
  try {
    await ElMessageBox.confirm('确定删除该学期吗？', '提示', { type: 'warning' })
    await api.semesters.delete(row.id)
    ElMessage.success('删除成功')
    await loadSemesters()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

const handleSubmit = async () => {
  await formRef.value.validate()

  try {
    const payload = {
      name: form.name,
      year: form.year
    }

    if (editingSemesterId.value) {
      await api.semesters.update(editingSemesterId.value, payload)
      ElMessage.success('更新成功')
    } else {
      await api.semesters.create(payload)
      ElMessage.success('创建成功')
    }

    dialogVisible.value = false
    await loadSemesters()
  } catch {
    ElMessage.error('操作失败')
  }
}

onMounted(() => {
  loadSemesters()
})
</script>

<style scoped>
.semesters {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}

.page-title {
  margin: 0;
}
</style>
