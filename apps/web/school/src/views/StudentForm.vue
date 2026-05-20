<template>
  <div class="student-form-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ pageTitle }}</h1>
        <p class="page-subtitle">{{ pageSubtitle }}</p>
      </div>
      <el-button @click="goBack">返回</el-button>
    </div>

    <el-alert
      v-if="isRosterMode"
      type="info"
      :closable="false"
      class="roster-tip"
      title="花名册说明"
      description="维护班级花名册；保存后系统会为学生账号建立绑定，学号可留空并由系统自动生成。班主任/管理员可在用户管理中重置密码或调班。"
    />

    <el-card shadow="never" v-loading="loading">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="96px" class="student-form">
        <el-form-item label="姓名" prop="name">
          <el-input v-model="form.name" maxlength="30" show-word-limit />
        </el-form-item>

        <el-form-item label="性别" prop="gender">
          <el-radio-group v-model="form.gender">
            <el-radio label="male">男</el-radio>
            <el-radio label="female">女</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="学号（可空）" prop="student_no">
          <el-input v-model="form.student_no" maxlength="40" />
        </el-form-item>

        <el-form-item label="所属班级" prop="class_id">
          <el-select
            v-model="form.class_id"
            placeholder="未分班"
            style="width: 100%"
            clearable
            :disabled="isRosterMode && lockClassSelect"
          >
            <el-option
              v-for="item in classes"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="手机号">
          <el-input v-model="form.phone" maxlength="20" />
        </el-form-item>

        <el-form-item label="家长电话">
          <el-input v-model="form.parent_phone" maxlength="20" />
        </el-form-item>

        <el-form-item label="家庭住址">
          <el-input v-model="form.address" type="textarea" :rows="3" maxlength="200" show-word-limit />
        </el-form-item>

        <el-form-item class="form-actions">
          <el-button @click="goBack">取消</el-button>
          <el-button type="primary" :loading="submitting" @click="submitForm">
            {{ isEdit ? '保存修改' : '创建学生' }}
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import api from '@/api'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const formRef = ref(null)
const loading = ref(false)
const submitting = ref(false)
const classes = ref([])

const form = reactive({
  name: '',
  gender: 'male',
  student_no: '',
  class_id: null,
  phone: '',
  parent_phone: '',
  address: ''
})

const isRosterMode = computed(() => route.name === 'RosterStudentCreate' || route.name === 'RosterStudentEdit')
const isEdit = computed(() => Boolean(route.params.id) && route.name !== 'RosterStudentCreate')

const rosterQueryClassId = computed(() => {
  const raw = route.query.class_id
  if (raw === undefined || raw === null || raw === '') {
    return null
  }
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
})

const lockClassSelect = computed(() => rosterQueryClassId.value != null)

const pageTitle = computed(() => {
  if (isRosterMode.value) {
    return isEdit.value ? '编辑花名册学生' : '新增花名册学生'
  }
  return isEdit.value ? '编辑学生' : '新增学生'
})

const pageSubtitle = computed(() => {
  if (isRosterMode.value) {
    return isEdit.value
      ? '修改本班花名册信息；保存后已选课程将按新班级自动同步（若调班）。'
      : '向当前课程所属班级添加一名花名册学生，保存后将自动加入本班已有课程的选课名单。'
  }
  return isEdit.value ? '修改学生信息并保存到学生管理列表。' : '手动新增一名学生并关联到对应班级。'
})

const rules = {
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  gender: [{ required: true, message: '请选择性别', trigger: 'change' }],
  student_no: []
}

const fillForm = student => {
  form.name = student?.name || ''
  form.gender = student?.gender || 'male'
  form.student_no = student?.student_no || ''
  form.class_id = student?.class_id ?? null
  form.phone = student?.phone || ''
  form.parent_phone = student?.parent_phone || ''
  form.address = student?.address || ''
}

const loadClasses = async () => {
  classes.value = await api.classes.list()
}

const applyRosterDefaults = async () => {
  if (!isRosterMode.value || isEdit.value) {
    return
  }
  if (rosterQueryClassId.value != null) {
    form.class_id = rosterQueryClassId.value
    return
  }
  await userStore.ensureSelectedCourse(false, { preserveEmptySelection: true })
  const cid = userStore.selectedCourse?.class_id
  if (cid != null) {
    form.class_id = cid
  }
}

const loadStudent = async () => {
  if (!isEdit.value) {
    return
  }

  const student = await api.students.get(route.params.id)
  fillForm(student)
}

const goBack = () => {
  router.push('/students')
}

const submitForm = async () => {
  await formRef.value.validate()

  submitting.value = true
  try {
    const payload = {
      name: form.name,
      gender: form.gender,
      student_no: form.student_no,
      class_id: form.class_id,
      phone: form.phone || null,
      parent_phone: form.parent_phone || null,
      address: form.address || null
    }

    if (isEdit.value) {
      await api.students.update(route.params.id, payload)
      ElMessage.success(isRosterMode.value ? '花名册已更新' : '学生信息已更新')
    } else {
      await api.students.create(payload)
      ElMessage.success(isRosterMode.value ? '花名册学生已添加并已尝试加入本班课程选课' : '学生已创建')
    }

    if (isRosterMode.value && userStore.selectedCourse?.id) {
      try {
        await api.courses.syncEnrollments(userStore.selectedCourse.id)
      } catch {
        /* sync is best-effort after create */
      }
    }

    goBack()
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  loading.value = true
  try {
    await loadClasses()
    await applyRosterDefaults()
    await loadStudent()
    await nextTick()
    formRef.value?.clearValidate?.()
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.student-form-page {
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

.roster-tip {
  margin-bottom: 16px;
  max-width: 760px;
}

.student-form {
  max-width: 760px;
}

.form-actions :deep(.el-form-item__content) {
  justify-content: flex-end;
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
  }

  .student-form {
    max-width: 100%;
  }
}
</style>
