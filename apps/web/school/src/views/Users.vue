<template>
  <div class="users-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">用户管理</h1>
        <p class="page-subtitle">
          支持管理员、班主任、任课老师和学生四类用户。学生账号会绑定到学生档案；可先创建未分班学生，再通过<strong>批量调班</strong> / <strong>加入课程…</strong>完成班级和选课调整。
        </p>
      </div>
      <div class="page-actions">
        <el-button
          v-if="isAdmin"
          type="primary"
          plain
          data-testid="users-open-add-course"
          :disabled="!batchSelectedStudents.length"
          @click="openAddToCourseDialog"
        >
          加入课程…
        </el-button>
        <el-button type="warning" plain data-testid="users-open-batch-class" @click="openBatchClassDialog">
          批量调班
        </el-button>
        <el-button type="primary" data-testid="users-open-create" @click="openCreateDialog">新建用户</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <DualHorizontalScroll target-selector=".users-table-scroll">
        <div class="users-table-scroll dual-scroll-target">
          <el-table
            ref="usersTableRef"
            :data="users"
            v-loading="loading"
            row-key="id"
            @selection-change="handleUserSelectionChange"
          >
        <el-table-column type="selection" width="48" :selectable="row => row.role === 'student'" />
        <el-table-column prop="username" label="用户名" min-width="160" />
        <el-table-column prop="real_name" label="姓名" min-width="140" />
        <el-table-column label="角色" width="140">
          <template #default="{ row }">
            <el-tag :type="roleTag(row.role)">{{ roleText(row.role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="所属班级" min-width="160">
          <template #default="{ row }">
            {{ classNameById(row.class_id) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <div class="users-table-actions">
              <el-button type="primary" size="small" @click="openEditDialog(row)">编辑</el-button>
              <el-button size="small" @click="router.push({ name: 'RecentPostsUser', params: { userId: String(row.id) } })">
                近期发表
              </el-button>
              <el-button
                v-if="isAdmin"
                type="warning"
                size="small"
                data-testid="users-reset-password"
                :disabled="row.id === userStore.userInfo?.id"
                @click="openResetPasswordDialog(row)"
              >
                重置密码
              </el-button>
              <el-button
                type="danger"
                size="small"
                :disabled="isDeleteDisabled(row)"
                @click="deleteUser(row)"
              >
                删除
              </el-button>
            </div>
          </template>
        </el-table-column>
          </el-table>
        </div>
      </DualHorizontalScroll>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingUser ? '编辑用户' : '新建用户'"
      width="520px"
      destroy-on-close
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" :disabled="Boolean(editingUser)" />
        </el-form-item>
        <el-form-item v-if="!editingUser" label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="姓名" prop="real_name">
          <el-input v-model="form.real_name" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-radio-group v-model="form.role">
            <el-radio label="admin">管理员</el-radio>
            <el-radio label="class_teacher">班主任</el-radio>
            <el-radio label="teacher">任课老师</el-radio>
            <el-radio label="student">学生</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="showClassAssignmentField" label="所属班级" prop="class_id">
          <el-select
            v-model="form.class_id"
            data-testid="user-form-class-select"
            :placeholder="form.role === 'student' ? '可选，留空为未分班' : '可选'"
            style="width: 100%"
            filterable
            clearable
          >
            <el-option v-for="item in classes" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="editingUser" label="是否启用">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="batchClassDialogVisible"
      data-testid="dialog-batch-class"
      title="批量调班（学生账号）"
      width="560px"
      destroy-on-close
      @closed="resetBatchClassDialog"
    >
      <el-alert type="info" :closable="false" class="batch-class-alert">
        <template #title>说明</template>
        <p class="batch-class-alert-body">
          仅支持<strong>学生</strong>角色。将把所选账号的「所属班级」统一改到下方班级，并自动同步它们绑定的花名册记录（含选课同步）。
        </p>
      </el-alert>

      <el-form label-width="100px" class="batch-class-form">
        <el-form-item label="目标班级" required>
          <el-select
            v-model="batchTargetClassId"
            placeholder="请选择班级"
            style="width: 100%"
            filterable
            data-testid="batch-class-target-select"
          >
            <el-option v-for="c in classes" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="已选学生">
          <span>{{ batchSelectedStudents.length }} 人</span>
          <el-button link type="primary" class="batch-clear-link" @click="clearUserTableSelection">
            清空表格勾选
          </el-button>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="batchClassDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          data-testid="batch-class-confirm"
          :loading="batchClassSubmitting"
          :disabled="!batchSelectedStudents.length || !batchTargetClassId"
          @click="submitBatchClass"
        >
          确认调班
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="addToCourseDialogVisible"
      data-testid="dialog-users-add-course"
      title="将所选学生加入课程选课"
      width="560px"
      destroy-on-close
      @closed="resetAddToCourseDialog"
    >
      <el-alert type="info" :closable="false" class="batch-class-alert">
        <template #title>说明</template>
        <p class="batch-class-alert-body">
          仅处理已勾选且角色为<strong>学生</strong>的账号。将优先按已绑定的学生档案进课，未绑定时再按学号匹配花名册；最终仍需落到本班花名册中。
        </p>
      </el-alert>
      <el-form label-width="100px" class="batch-class-form">
        <el-form-item label="目标课程" required>
          <el-select
            v-model="addToCourseSubjectId"
            placeholder="请选择课程"
            style="width: 100%"
            filterable
            data-testid="users-add-course-select"
          >
            <el-option
              v-for="c in coursesWithClass"
              :key="c.id"
              :label="`${c.name}（${c.class_name || '班'}）`"
              :value="c.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="已选学生">
          <span>{{ batchSelectedStudents.length }} 人</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addToCourseDialogVisible = false">取消</el-button>
        <el-button
          type="primary"
          data-testid="users-add-course-confirm"
          :loading="addToCourseSubmitting"
          :disabled="!addToCourseSubjectId || !batchSelectedStudents.length"
          @click="submitAddToCourse"
        >
          确认加入
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="resetPwdVisible"
      data-testid="dialog-reset-password"
      title="重置密码"
      width="480px"
      destroy-on-close
      @closed="resetPwdFormState"
    >
      <el-alert v-if="resetPwdTarget" type="info" :closable="false" class="reset-pwd-alert">
        <template #title>规则说明</template>
        <p v-if="resetPwdTarget.role === 'student'" class="reset-pwd-alert-body">
          学生默认新密码优先使用<strong>用户名</strong>；历史学生账号若仍与学号一致也会沿用该值。也可在下方填写自定义密码。
        </p>
        <p v-else-if="resetPwdTarget.role === 'admin'" class="reset-pwd-alert-body">
          重置<strong>管理员</strong>密码必须填写新密码。
        </p>
        <p v-else class="reset-pwd-alert-body">
          教师/班主任默认新密码为 <strong>111111</strong>；也可在下方填写自定义密码。
        </p>
      </el-alert>
      <el-form ref="resetPwdFormRef" :model="resetPwdForm" :rules="resetPwdRules" label-width="100px" class="reset-pwd-form">
        <el-form-item label="新密码" prop="new_password">
          <el-input
            v-model="resetPwdForm.new_password"
            type="password"
            show-password
            :placeholder="resetPwdPlaceholder"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetPwdVisible = false">取消</el-button>
        <el-button type="primary" :loading="resetPwdSubmitting" @click="submitResetPassword">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import api from '@/api'
import DualHorizontalScroll from '@/components/DualHorizontalScroll.vue'
import { useUserStore } from '@/stores/user'
import { loadAllPages } from '@/utils/pagedFetch'

const userStore = useUserStore()
const route = useRoute()
const router = useRouter()
const isAdmin = computed(() => userStore.isAdmin)

const loading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)
const batchClassDialogVisible = ref(false)
const batchTargetClassId = ref(null)
const batchClassSubmitting = ref(false)
const editingUser = ref(null)
const formRef = ref(null)
const usersTableRef = ref(null)
const users = ref([])
const classes = ref([])
const batchSelectedStudents = ref([])
const addToCourseDialogVisible = ref(false)
const addToCourseSubjectId = ref(null)
const addToCourseSubmitting = ref(false)
const allSubjects = ref([])

const resetPwdVisible = ref(false)
const resetPwdSubmitting = ref(false)
const resetPwdTarget = ref(null)
const resetPwdFormRef = ref(null)
const resetPwdForm = reactive({ new_password: '' })

const form = reactive({
  username: '',
  password: '',
  real_name: '',
  role: 'teacher',
  class_id: null,
  is_active: true
})

const rules = computed(() => {
  const base = {
    username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
    password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
    real_name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
    role: [{ required: true, message: '请选择角色', trigger: 'change' }]
  }
  return base
})

const roleText = role => ({
  admin: '管理员',
  class_teacher: '班主任',
  teacher: '任课老师',
  student: '学生'
}[role] || role)

const roleTag = role => ({
  admin: 'danger',
  class_teacher: 'warning',
  teacher: 'success',
  student: 'info'
}[role] || '')

const isDeleteDisabled = user => user.role === 'admin'

const resetPwdPlaceholder = computed(() => {
  const r = resetPwdTarget.value?.role
  if (r === 'student') return '留空则使用用户名作为新密码'
  if (r === 'admin') return '必填'
  return '留空则使用默认 111111'
})

const resetPwdRules = computed(() => {
  if (resetPwdTarget.value?.role === 'admin') {
    return {
      new_password: [{ required: true, message: '重置管理员密码必须填写新密码', trigger: 'blur' }]
    }
  }
  return { new_password: [] }
})

const showClassAssignmentField = computed(() => form.role !== 'teacher')

watch(
  () => form.role,
  role => {
    if (role === 'teacher') {
      form.class_id = null
    }
    if (role !== 'student') {
      formRef.value?.clearValidate?.(['class_id'])
    }
  }
)

const resetForm = () => {
  Object.assign(form, {
    username: '',
    password: '',
    real_name: '',
    role: 'teacher',
    class_id: null,
    is_active: true
  })
}

const loadUsers = async () => {
  loading.value = true
  try {
    users.value = await api.users.list()
  } finally {
    loading.value = false
  }
}

const loadClasses = async () => {
  classes.value = await api.classes.list()
}

const coursesWithClass = computed(() =>
  (allSubjects.value || []).filter(c => c.class_id)
)

const loadSubjectsIfAdmin = async () => {
  if (!isAdmin.value) {
    allSubjects.value = []
    return
  }
  try {
    allSubjects.value = await api.subjects.list()
  } catch (e) {
    console.error(e)
    allSubjects.value = []
  }
}

const classNameById = classId => {
  if (classId == null) {
    return '—'
  }
  const row = classes.value.find(c => c.id === classId)
  return row ? row.name : `班级 #${classId}`
}

const handleUserSelectionChange = rows => {
  batchSelectedStudents.value = (rows || []).filter(r => r.role === 'student')
}

const clearUserTableSelection = () => {
  batchSelectedStudents.value = []
  usersTableRef.value?.clearSelection()
}

const openBatchClassDialog = () => {
  if (!batchSelectedStudents.value.length) {
    ElMessage.warning('请先在表格中勾选需要调班的学生账号')
    return
  }
  batchTargetClassId.value = null
  batchClassDialogVisible.value = true
}

const resetAddToCourseDialog = () => {
  addToCourseSubjectId.value = null
}

const openAddToCourseDialog = async () => {
  if (!batchSelectedStudents.value.length) {
    ElMessage.warning('请先勾选学生账号')
    return
  }
  await loadSubjectsIfAdmin()
  if (!coursesWithClass.value.length) {
    ElMessage.warning('暂无可选课程（课程须绑定班级）')
    return
  }
  addToCourseSubjectId.value = null
  addToCourseDialogVisible.value = true
}

const submitAddToCourse = async () => {
  if (!addToCourseSubjectId.value || !batchSelectedStudents.value.length) {
    return
  }
  const courseId = addToCourseSubjectId.value
  const course = (allSubjects.value || []).find(c => c.id === courseId)
  if (!course?.class_id) {
    ElMessage.error('所选课程未绑定班级')
    return
  }
  addToCourseSubmitting.value = true
  try {
    const rosterRows = await loadAllPages(params =>
      api.students.list({
        ...params,
        class_id: course.class_id,
        page_size: 500
      })
    )
    const rosterById = new Map((rosterRows || []).map(r => [r.id, r.id]))
    const noToId = new Map((rosterRows || []).map(r => [`${(r.student_no || '').trim()}`, r.id]).filter(([k]) => k))
    const studentIds = []
    const missingNames = []
    for (const u of batchSelectedStudents.value) {
      const sid = u.student_id && rosterById.has(u.student_id) ? u.student_id : noToId.get(`${(u.username || '').trim()}`)
      if (sid) {
        studentIds.push(sid)
      } else if (u.real_name || u.username) {
        missingNames.push(u.real_name || u.username)
      }
    }
    if (missingNames.length) {
      await ElMessageBox.alert(
        `以下学生账号在课程所属班级的花名册中仍未找到，无法进课：\n${missingNames.slice(0, 15).join('、')}${
          missingNames.length > 15 ? '…' : ''
        }`,
        '无法匹配花名册',
        { confirmButtonText: '知道了' }
      )
    }
    if (!studentIds.length) {
      addToCourseDialogVisible.value = false
      clearUserTableSelection()
      return
    }

    const enrollRes = await api.subjects.rosterEnroll(courseId, {
      student_ids: [...new Set(studentIds)]
    })
    const msgParts = []
    if (enrollRes?.created > 0) msgParts.push(`新增选课 ${enrollRes.created} 人`)
    if (enrollRes?.skipped_already_enrolled > 0) {
      msgParts.push(`已在课 ${enrollRes.skipped_already_enrolled} 人`)
    }
    if (enrollRes?.skipped_not_in_class_roster > 0) {
      msgParts.push(`非课程班级花名册 ${enrollRes.skipped_not_in_class_roster} 人`)
    }
    ElMessage.success(msgParts.length ? msgParts.join('；') : '选课无变更')
    addToCourseDialogVisible.value = false
    clearUserTableSelection()
  } catch (e) {
    console.error(e)
  } finally {
    addToCourseSubmitting.value = false
  }
}

const resetBatchClassDialog = () => {
  batchTargetClassId.value = null
}

const submitBatchClass = async () => {
  if (!batchSelectedStudents.value.length || !batchTargetClassId.value) {
    return
  }

  try {
    await ElMessageBox.confirm(
      `确认将 ${batchSelectedStudents.value.length} 名学生账号调至「${classNameById(batchTargetClassId.value)}」吗？`,
      '批量调班',
      { type: 'warning', distinguishCancelAndClose: true }
    )
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') {
      console.error(e)
    }
    return
  }

  batchClassSubmitting.value = true
  try {
    const result = await api.users.batchSetClass({
      user_ids: batchSelectedStudents.value.map(u => u.id),
      class_id: batchTargetClassId.value
    })
    const updated = result?.updated ?? 0
    const errors = result?.errors || []
    if (errors.length) {
      const lines = errors.slice(0, 12).map(e => `用户 #${e.user_id}：${e.reason}`)
      await ElMessageBox.alert(['部分未处理：', ...lines].join('\n'), '调班结果', {
        confirmButtonText: '知道了'
      })
    }
    ElMessage.success(`已更新 ${updated} 个学生账号的班级`)
    batchClassDialogVisible.value = false
    clearUserTableSelection()
    await loadUsers()
  } catch (e) {
    console.error('批量调班失败', e)
  } finally {
    batchClassSubmitting.value = false
  }
}

const openCreateDialog = () => {
  editingUser.value = null
  resetForm()
  dialogVisible.value = true
}

const openEditDialog = user => {
  editingUser.value = user
  Object.assign(form, {
    username: user.username,
    password: '',
    real_name: user.real_name,
    role: user.role,
    class_id: user.role === 'teacher' ? null : user.class_id,
    is_active: user.is_active
  })
  dialogVisible.value = true
}

const openResetPasswordDialog = row => {
  resetPwdTarget.value = row
  resetPwdForm.new_password = ''
  resetPwdVisible.value = true
}

const resetPwdFormState = () => {
  resetPwdTarget.value = null
  resetPwdForm.new_password = ''
  resetPwdFormRef.value?.clearValidate?.()
}

const submitResetPassword = async () => {
  await resetPwdFormRef.value?.validate?.()
  resetPwdSubmitting.value = true
  try {
    const trimmed = resetPwdForm.new_password?.trim()
    const payload = trimmed ? { new_password: trimmed } : {}
    await api.users.resetPassword(resetPwdTarget.value.id, payload)
    ElMessage.success('密码已重置')
    resetPwdVisible.value = false
    await loadUsers()
  } catch (e) {
    console.error(e)
  } finally {
    resetPwdSubmitting.value = false
  }
}

const maybeOpenResetFromQuery = async () => {
  const raw = route.query.open_reset_password_user_id
  if (!raw || !isAdmin.value) return
  const id = Number(raw)
  if (!id || Number.isNaN(id)) return
  if (!users.value.length) {
    await loadUsers()
  }
  const u = users.value.find(x => Number(x.id) === id)
  if (u) {
    openResetPasswordDialog(u)
  }
}

const buildPayload = () => ({
  ...form,
  class_id: form.role === 'teacher' ? null : form.class_id
})

const submitForm = async () => {
  await formRef.value.validate()
  submitting.value = true
  try {
    const payload = buildPayload()
    if (editingUser.value) {
      await api.users.update(editingUser.value.id, {
        real_name: payload.real_name,
        role: payload.role,
        class_id: payload.class_id,
        is_active: payload.is_active
      })
      ElMessage.success('用户已更新')
    } else {
      await api.users.create(payload)
      ElMessage.success('用户已创建')
    }
    dialogVisible.value = false
    await loadUsers()
  } finally {
    submitting.value = false
  }
}

const deleteUser = async user => {
  try {
    await ElMessageBox.confirm(
      `确认删除用户“${user.real_name}”（账号：${user.username}）吗？此操作不可恢复。`,
      '删除用户',
      {
        type: 'warning',
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        distinguishCancelAndClose: true
      }
    )
    await api.users.delete(user.id)
    ElMessage.success('用户已删除')
    await loadUsers()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      console.error('删除用户失败', error)
    }
  }
}

onMounted(async () => {
  await Promise.all([loadUsers(), loadClasses(), loadSubjectsIfAdmin()])
  await maybeOpenResetFromQuery()
})

watch(
  () => route.query.open_reset_password_user_id,
  async () => {
    await maybeOpenResetFromQuery()
  }
)
</script>

<style scoped>
.users-page {
  padding: 24px;
  min-width: 0;
  overflow-x: hidden;
  width: min(100%, 1180px);
  margin: 0 auto;
}

.users-page :deep(.el-card) {
  min-width: 0;
  border-radius: var(--wa-radius-lg);
  border: 1px solid color-mix(in srgb, var(--wa-border-subtle) 86%, transparent);
  box-shadow: var(--wa-shadow-surface);
}

.users-page :deep(.el-card__body) {
  overflow-x: hidden;
}

.users-table-scroll {
  overflow-x: auto;
}

.users-table-scroll :deep(.el-table) {
  min-width: 1120px;
}

.users-table-scroll :deep(.el-table__fixed-right) {
  box-shadow: -10px 0 18px rgba(15, 23, 42, 0.06);
}

.users-table-actions {
  display: inline-flex;
  flex-wrap: wrap;
  justify-content: center;
  align-items: center;
  gap: 6px;
  width: 100%;
}

.users-table-actions :deep(.el-button) {
  margin-left: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 24px;
}

.page-actions {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  flex-shrink: 0;
  min-width: 0;
}

.page-title {
  margin: 0 0 8px;
  font-size: 28px;
  color: var(--wa-color-text);
}

.page-subtitle {
  margin: 0;
  color: var(--wa-color-text-muted);
  line-height: 1.6;
}

.batch-class-alert {
  margin-bottom: 16px;
  border-radius: var(--wa-radius-lg);
}

.batch-class-alert-body {
  margin: 0;
  line-height: 1.65;
  color: #334155;
}

.batch-class-form {
  margin-top: 8px;
}

.batch-clear-link {
  margin-left: 12px;
}

@media (max-width: 768px) {
  .users-page {
    padding: 18px 14px;
  }

  .page-header {
    flex-direction: column;
    align-items: stretch;
  }

  .page-actions {
    flex-wrap: wrap;
    justify-content: stretch;
  }
}
</style>
