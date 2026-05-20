<template>
  <div class="students-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ pageTitle }}</h1>
        <p class="page-subtitle">{{ pageSubtitle }}</p>
      </div>
      <div v-if="showStudentWorkflowActions" class="page-header-actions">
        <el-button type="primary" plain @click="router.push('/scores')">
          成绩管理
        </el-button>
        <el-button type="primary" plain @click="router.push('/attendance')">
          考勤管理
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="isAdminView && adminFilterClassId"
      type="info"
      :closable="false"
      class="admin-class-filter-alert"
      data-testid="students-admin-class-filter-banner"
    >
      <template #title>班级筛选</template>
      <p>
        当前仅显示「<strong>{{ adminFilterClassName }}</strong>」的花名册。
        <el-button link type="primary" data-testid="students-clear-class-filter" @click="clearAdminClassFilter">
          查看全校名单
        </el-button>
      </p>
    </el-alert>

    <el-empty
      v-if="showEmpty"
      :description="emptyText"
    />

    <template v-else>
      <el-alert
        v-if="showTeacherAlert"
        type="info"
        :closable="false"
        class="info-alert"
      >
        <template #title>课程花名册与选课</template>
        <p class="alert-body">
          选课名单与<strong>行政班花名册必须一致</strong>：只能给「本课程所属班级」里已有的学生加选课；请在<strong>课程管理</strong>中打开「从花名册进课」，使用「全班加入选课」或勾选后进课。
          学生账号会与花名册学生档案绑定后用于交作业。可在此维护花名册：支持<strong>文件导入</strong>或<strong>粘贴批量导入</strong>；导入时「所属班级」可留空，将默认填入当前课程班级，学号可留空并由系统自动生成。
          若人数为 0 或新生进班后未出现在选课中，请先确认花名册中已有该生，再在课程管理中同步选课。
        </p>
      </el-alert>

      <el-card shadow="never">
        <template #header>
          <div class="card-header-block">
            <div class="card-header">
              <div>
                <strong>{{ cardTitle }}</strong>
                <span class="header-count">共 {{ students.length }} 人</span>
              </div>

              <div v-if="isAdminView" class="card-actions">
                <el-button type="primary" @click="openFileImportDialog">文件导入名单</el-button>
                <el-button type="primary" plain data-testid="students-open-paste-import" @click="openPasteImportDialog">
                  粘贴批量导入
                </el-button>
                <el-button @click="router.push('/students/new')">新增学生</el-button>
                <input
                  ref="fileInputRef"
                  class="hidden-file-input"
                  type="file"
                  accept=".xlsx,.xls,.csv"
                  @change="handleFileChange"
                />
              </div>

              <div v-else-if="canManageRoster" class="card-actions">
                <el-button type="primary" @click="openFileImportDialog">文件导入花名册</el-button>
                <el-button type="primary" plain data-testid="students-open-paste-import" @click="openPasteImportDialog">
                  粘贴批量导入
                </el-button>
                <el-button @click="goRosterNew">新增花名册学生</el-button>
                <input
                  ref="fileInputRef"
                  class="hidden-file-input"
                  type="file"
                  accept=".xlsx,.xls,.csv"
                  @change="handleFileChange"
                />
              </div>
            </div>

            <p v-if="isAdminView" class="import-tip">
              批量导入请使用「文件导入」（内含模板下载）或「粘贴批量导入」。
            </p>
            <p v-else-if="canManageRoster" class="import-tip">
              花名册可「文件导入」或「粘贴批量导入」；详细说明在「文件导入」对话框内。
            </p>
          </div>
        </template>

        <el-table :data="students" v-loading="loading || importing">
          <template v-if="isAdminView">
            <el-table-column prop="name" label="姓名" min-width="160" />
            <el-table-column label="性别" width="120">
              <template #default="{ row }">
                {{ genderText(row.gender) }}
              </template>
            </el-table-column>
            <el-table-column prop="student_no" label="学号" min-width="180" />
            <el-table-column label="所属班级" min-width="180">
              <template #default="{ row }">
                {{ row.class_name || '未分班' }}
              </template>
            </el-table-column>
            <el-table-column label="账号状态" width="120">
              <template #default="{ row }">
                <el-tag :type="row.has_user ? 'success' : 'info'">
                  {{ row.has_user ? '已生成' : '未生成' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="220" fixed="right">
              <template #default="{ row }">
                <StudentActionMenu :user-id="row.bound_user_id" :student-id="row.id" />
                <el-button type="primary" size="small" @click="router.push(`/students/${row.id}/edit`)">
                  编辑
                </el-button>
                <el-button type="danger" size="small" @click="deleteStudent(row)">
                  删除
                </el-button>
              </template>
            </el-table-column>
          </template>

          <template v-else-if="isClassTeacherView">
            <el-table-column prop="name" label="姓名" min-width="140" />
            <el-table-column label="性别" width="100">
              <template #default="{ row }">
                {{ genderText(row.gender) }}
              </template>
            </el-table-column>
            <el-table-column prop="student_no" label="学号" min-width="160" />
            <el-table-column prop="class_name" label="班级" min-width="160">
              <template #default="{ row }">{{ emptyCell(row.class_name) }}</template>
            </el-table-column>
            <el-table-column label="联系电话" min-width="150">
              <template #default="{ row }">{{ emptyCell(row.phone) }}</template>
            </el-table-column>
            <el-table-column label="家长电话" min-width="150">
              <template #default="{ row }">{{ emptyCell(row.parent_phone) }}</template>
            </el-table-column>
            <el-table-column label="家庭住址" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">{{ emptyCell(row.address) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="90" fixed="right">
              <template #default="{ row }">
                <StudentActionMenu :user-id="row.bound_user_id" :student-id="row.id" />
              </template>
            </el-table-column>
          </template>

          <template v-else>
            <el-table-column prop="student_name" label="学生姓名" min-width="160" />
            <el-table-column prop="student_no" label="学号" width="160" />
            <el-table-column prop="class_name" label="所属班级" width="180">
              <template #default="{ row }">{{ emptyCell(row.class_name) }}</template>
            </el-table-column>
            <el-table-column label="选课方式" width="120">
              <template #default="{ row }">
                <el-select
                  v-if="canManageRoster"
                  :model-value="row.enrollment_type || 'required'"
                  size="small"
                  style="width: 100%"
                  @change="value => updateEnrollmentType(row, value)"
                >
                  <el-option label="必修" value="required" />
                  <el-option label="选修" value="elective" />
                </el-select>
                <el-tag v-else :type="(row.enrollment_type || 'required') === 'elective' ? 'warning' : 'success'">
                  {{ (row.enrollment_type || 'required') === 'elective' ? '选修' : '必修' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column v-if="canManageRoster" label="操作" width="260" fixed="right">
              <template #default="{ row }">
                <StudentActionMenu
                  :user-id="row.student_user_id"
                  :student-id="row.student_id"
                  :course="selectedCourse"
                />
                <el-button type="primary" link size="small" @click="goRosterEdit(row.student_id)">
                  编辑花名册
                </el-button>
                <el-button type="danger" size="small" @click="removeStudent(row)">
                  移除选课
                </el-button>
              </template>
            </el-table-column>
          </template>
        </el-table>
      </el-card>

      <el-dialog
        v-model="fileImportDialogVisible"
        data-testid="dialog-file-import-students"
        :title="isAdminView ? '文件导入名单' : '文件导入花名册'"
        width="560px"
        destroy-on-close
        @closed="resetFileImportDialog"
      >
        <el-alert type="info" :closable="false" class="file-import-alert">
          <template #title>格式说明</template>
          <p v-if="isAdminView" class="alert-body">
            支持 <strong>Excel（.xlsx / .xls）</strong> 或 <strong>CSV</strong>。表头须包含列：<strong>姓名、性别、学号、所属班级</strong>（与模板一致）；其中学号可留空，系统会自动生成。导入时若发现新班级，仅管理员可自动创建班级。
          </p>
          <p v-else class="alert-body">
            支持 <strong>Excel</strong> 或 <strong>CSV</strong>；列为：姓名、性别、学号、所属班级（可留空，将使用当前课程班级）；学号也可留空，系统会自动生成。仅管理员可创建登录账号；进课请在课程管理中打开「从花名册进课」。
          </p>
        </el-alert>

        <div class="file-import-actions">
          <el-button data-testid="students-download-template-xlsx" @click="downloadTemplate('xlsx')">
            下载 Excel 模板
          </el-button>
          <el-button data-testid="students-download-template-csv" @click="downloadTemplate('csv')">
            下载 CSV 模板
          </el-button>
          <el-button type="primary" data-testid="students-trigger-file-import" :loading="importing" @click="triggerImport">
            选择文件并导入
          </el-button>
        </div>
        <p class="file-import-hint muted-hint">请选择 .xlsx、.xls 或 .csv 文件；导入过程中请勿关闭窗口。</p>

        <template #footer>
          <el-button @click="fileImportDialogVisible = false">关闭</el-button>
        </template>
      </el-dialog>

      <el-dialog
        v-model="pasteDialogVisible"
        data-testid="dialog-paste-import-students"
        title="粘贴批量导入"
        width="720px"
        destroy-on-close
        @closed="resetPasteDialog"
      >
        <el-alert type="info" :closable="false" class="paste-alert">
          <template #title>格式说明</template>
          <p class="alert-body">
            每行一名学生，列为：<strong>姓名、性别、学号、所属班级</strong>，中间用 <strong>Tab</strong> 或<strong>英文逗号</strong>分隔（与 Excel 复制到记事本一致）；学号可留空。
            任课教师场景下「所属班级」可省略，将使用当前课程班级。表头行（以「姓名」开头）会自动跳过。
          </p>
        </el-alert>

        <el-input
          v-model="pasteText"
          type="textarea"
          :rows="10"
          placeholder="从 Excel 或表格中复制后粘贴到此处…"
          class="paste-textarea"
          data-testid="paste-import-textarea"
        />

        <div class="paste-actions">
          <el-button data-testid="paste-import-preview" @click="previewPasteImport">解析并预览</el-button>
        </div>

        <el-alert v-if="pasteParseErrors.length" type="error" :closable="false" class="paste-errors">
          <template #title>解析问题（最多显示 15 条）</template>
          <ul class="paste-error-list">
            <li v-for="(msg, idx) in pasteParseErrors.slice(0, 15)" :key="`pe-${idx}`">{{ msg }}</li>
          </ul>
        </el-alert>

        <div v-if="pastePreviewRows.length" class="paste-preview">
          <p class="paste-preview-title">预览（共 {{ pastePreviewRows.length }} 人，提交后将写入花名册）</p>
          <el-table :data="pastePreviewRows" max-height="280" size="small" border>
            <el-table-column prop="name" label="姓名" min-width="100" />
            <el-table-column label="性别" width="80">
              <template #default="{ row }">{{ row.gender === 'male' ? '男' : '女' }}</template>
            </el-table-column>
            <el-table-column prop="student_no" label="学号" min-width="120" />
            <el-table-column prop="class_name" label="所属班级" min-width="140" />
          </el-table>
        </div>

        <template #footer>
          <el-button @click="pasteDialogVisible = false">取消</el-button>
          <el-button
            type="primary"
            data-testid="paste-import-submit"
            :loading="pasteSubmitting"
            :disabled="!pastePreviewPayload.length"
            @click="submitPasteImport"
          >
            确认导入
          </el-button>
        </template>
      </el-dialog>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as XLSX from 'xlsx'

import api from '@/api'
import StudentActionMenu from '@/components/StudentActionMenu.vue'
import { useUserStore } from '@/stores/user'
import { resolveClassTeacherClassId, resolveClassTeacherClassName } from '@/utils/classTeacher'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const adminClasses = ref([])

const adminFilterClassId = computed(() => {
  const raw = route.query.class_id
  if (raw == null || raw === '') {
    return null
  }
  const n = Number(Array.isArray(raw) ? raw[0] : raw)
  return Number.isFinite(n) && n > 0 ? n : null
})

const adminFilterClassName = computed(() => {
  if (!adminFilterClassId.value) {
    return ''
  }
  const row = adminClasses.value.find(c => c.id === adminFilterClassId.value)
  return row?.name || `班级 #${adminFilterClassId.value}`
})

const TEMPLATE_HEADERS = ['姓名', '性别', '学号', '所属班级']
const TEMPLATE_ROWS = [
  {
    姓名: '张三',
    性别: '男',
    学号: '2026001',
    所属班级: '高一(1)班'
  }
]

const loading = ref(false)
const importing = ref(false)
const students = ref([])
const fileInputRef = ref(null)
const classTeacherCourses = ref([])

const pasteDialogVisible = ref(false)
const fileImportDialogVisible = ref(false)
const pasteText = ref('')
const pasteParseErrors = ref([])
const pastePreviewRows = ref([])
const pastePreviewPayload = ref([])
const pasteSubmitting = ref(false)

const selectedCourse = computed(() => userStore.selectedCourse)
const isAdminView = computed(() => userStore.isAdmin)
const isClassTeacherView = computed(() => userStore.isClassTeacher)
const canManageRoster = computed(() => userStore.canManageTeaching && !isAdminView.value && !isClassTeacherView.value)
const currentClassId = computed(() => resolveClassTeacherClassId(userStore.userInfo, classTeacherCourses.value))
const currentClassName = computed(() => resolveClassTeacherClassName(userStore.userInfo, classTeacherCourses.value) || '未分配班级')

const pageTitle = computed(() => {
  if (isClassTeacherView.value) {
    return '学生信息'
  }

  return isAdminView.value ? '学生管理' : '学生信息'
})

const pageSubtitle = computed(() => {
  if (isAdminView.value) {
    return adminFilterClassId.value
      ? `当前为按班级筛选视图；默认可查看全校名单，并支持新增、编辑、删除和批量导入。`
      : '查看全校学生名单，并支持新增、编辑、删除和批量导入。'
  }

  if (isClassTeacherView.value) {
    return currentClassId.value ? `${currentClassName.value} 全部学生信息` : '请先为班主任账号分配班级。'
  }

  if (selectedCourse.value) {
    return `${selectedCourse.value.name} · ${selectedCourse.value.class_name || '未分配班级'}`
  }

  return '请先选择一门课程查看课程学生名单。'
})

const showEmpty = computed(() => {
  if (isAdminView.value) {
    return false
  }

  if (isClassTeacherView.value) {
    return !currentClassId.value
  }

  return !selectedCourse.value
})

const emptyText = computed(() => (isClassTeacherView.value ? '当前班主任账号没有绑定班级。' : '请先选择一门课程。'))
const showTeacherAlert = computed(() => !isAdminView.value && !isClassTeacherView.value && Boolean(selectedCourse.value))
const showStudentWorkflowActions = computed(() => userStore.isTeacher)

const cardTitle = computed(() => {
  if (isAdminView.value) {
    return adminFilterClassId.value ? `${adminFilterClassName.value} · 花名册` : '全校学生名单'
  }

  if (isClassTeacherView.value) {
    return `${currentClassName.value} 学生名单`
  }

  return '课程学生名单'
})

const genderText = gender => {
  if (gender === 'male') {
    return '男'
  }
  if (gender === 'female') {
    return '女'
  }
  return '无'
}

/** Display placeholder for optional roster / contact fields (aligned with 用户管理表格用语). */
const emptyCell = value => {
  if (value === undefined || value === null) {
    return '无'
  }
  const s = String(value).trim()
  return s || '无'
}

const normalizeCellValue = value => {
  if (value === undefined || value === null) {
    return ''
  }
  return String(value).trim()
}

const normalizeRowKeys = row =>
  Object.fromEntries(
    Object.entries(row).map(([key, value]) => [
      String(key).replace(/^\uFEFF/, '').trim(),
      value
    ])
  )

const normalizeGenderInput = value => {
  const gender = normalizeCellValue(value).replace(/\s+/g, '').toLowerCase()
  const genderMap = {
    男: 'male',
    male: 'male',
    m: 'male',
    '1': 'male',
    女: 'female',
    female: 'female',
    f: 'female',
    '0': 'female'
  }
  return genderMap[gender] || ''
}

const resetFileInput = () => {
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

const resetFileImportDialog = () => {
  resetFileInput()
}

const openFileImportDialog = () => {
  fileImportDialogVisible.value = true
}

const triggerImport = () => {
  fileInputRef.value?.click()
}

const splitPasteLine = line => {
  const t = String(line).trim()
  if (!t) {
    return []
  }
  if (t.includes('\t')) {
    return t.split('\t').map(cell => normalizeCellValue(cell))
  }
  return t.split(/[,，]/).map(cell => normalizeCellValue(cell))
}

const parsePasteTableLines = raw => {
  const lines = String(raw || '')
    .split(/\r?\n/)
    .map(l => l.trim())
    .filter(Boolean)

  const rows = []
  for (const line of lines) {
    const cells = splitPasteLine(line)
    if (!cells.length) {
      continue
    }
    const first = cells[0]
    if (first === '姓名' || /^name$/i.test(first)) {
      continue
    }
    const classDefault = !isAdminView.value ? defaultTeacherImportClassName.value : ''
    if (cells.length >= 4) {
      rows.push({
        姓名: cells[0],
        性别: cells[1],
        学号: cells[2],
        所属班级: cells[3]
      })
    } else if (cells.length === 3 && classDefault) {
      rows.push({
        姓名: cells[0],
        性别: cells[1],
        学号: cells[2],
        所属班级: classDefault
      })
    } else {
      rows.push({
        姓名: cells[0] || '',
        性别: cells[1] || '',
        学号: cells[2] || '',
        所属班级: cells[3] || ''
      })
    }
  }
  return rows
}

const openPasteImportDialog = () => {
  pasteParseErrors.value = []
  pastePreviewRows.value = []
  pastePreviewPayload.value = []
  pasteText.value = ''
  pasteDialogVisible.value = true
}

const resetPasteDialog = () => {
  pasteText.value = ''
  pasteParseErrors.value = []
  pastePreviewRows.value = []
  pastePreviewPayload.value = []
}

const previewPasteImport = () => {
  const tableRows = parsePasteTableLines(pasteText.value)
  if (!tableRows.length) {
    pasteParseErrors.value = ['未识别到任何数据行，请检查是否包含姓名、性别、学号等列。']
    pastePreviewRows.value = []
    pastePreviewPayload.value = []
    return
  }

  const defaultClassName = isAdminView.value ? '' : defaultTeacherImportClassName.value
  const { errors, payload } = parseImportRows(tableRows, { defaultClassName })
  pasteParseErrors.value = errors
  pastePreviewRows.value = payload.map(p => ({
    name: p.name,
    gender: p.gender,
    student_no: p.student_no,
    class_name: p.class_name
  }))
  pastePreviewPayload.value = payload
}

const submitPasteImport = async () => {
  if (!pastePreviewPayload.value.length) {
    ElMessage.warning('请先点击「解析并预览」且确保无错误')
    return
  }

  if (pasteParseErrors.value.length) {
    ElMessage.error('请先修正解析错误后再导入')
    return
  }

  pasteSubmitting.value = true
  try {
    const result = await api.students.batchCreate({ students: pastePreviewPayload.value })
    const createdClasses = result?.created_classes || []
    const successCount = result?.success || 0
    const failedCount = result?.failed || 0

    if (successCount > 0) {
      ElMessage({
        type: failedCount > 0 ? 'warning' : 'success',
        message: [
          `成功导入 ${successCount} 名学生`,
          createdClasses.length ? `自动创建 ${createdClasses.length} 个班级` : '',
          failedCount > 0 ? `失败 ${failedCount} 条` : ''
        ]
          .filter(Boolean)
          .join('，'),
        duration: 5000
      })
    }

    if (failedCount > 0) {
      const detailLines = [`成功：${successCount} 人`, `失败：${failedCount} 条`]
      const errorLines = (result?.errors || []).slice(0, 15)
      if (errorLines.length) {
        detailLines.push('', '失败明细：', ...errorLines)
      }
      await ElMessageBox.alert(detailLines.join('\n'), '导入结果', { confirmButtonText: '知道了' })
    }

    pasteDialogVisible.value = false
    await loadStudents()
  } catch (error) {
    console.error('粘贴导入失败', error)
  } finally {
    pasteSubmitting.value = false
  }
}

const downloadBlob = (blob, filename) => {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  window.URL.revokeObjectURL(url)
}

const downloadTemplate = format => {
  const worksheet = XLSX.utils.json_to_sheet(TEMPLATE_ROWS, { header: TEMPLATE_HEADERS })

  if (format === 'csv') {
    const csv = XLSX.utils.sheet_to_csv(worksheet)
    downloadBlob(new Blob(['\uFEFF', csv], { type: 'text/csv;charset=utf-8;' }), '学生导入模板.csv')
    return
  }

  const workbook = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(workbook, worksheet, '学生名单')
  XLSX.writeFile(workbook, '学生导入模板.xlsx')
}

const readWorkbook = async file => {
  const buffer = await file.arrayBuffer()
  const lowerName = file.name.toLowerCase()

  if (lowerName.endsWith('.csv')) {
    let content = new TextDecoder('utf-8').decode(buffer)

    if (content.includes('\uFFFD')) {
      try {
        content = new TextDecoder('gbk').decode(buffer)
      } catch (error) {
        console.warn('CSV GBK decode failed, fallback to UTF-8', error)
      }
    }

    return XLSX.read(content, { type: 'string' })
  }

  return XLSX.read(buffer, { type: 'array' })
}

const defaultTeacherImportClassName = computed(() => {
  const name = selectedCourse.value?.class_name
  return name ? String(name).trim() : ''
})

const parseImportRows = (rows, options = {}) => {
  const { defaultClassName = '' } = options
  const errors = []
  const payload = []

  rows.forEach((rawRow, index) => {
    const rowNumber = index + 2
    const row = normalizeRowKeys(rawRow)
    const name = normalizeCellValue(row.姓名 || row.学生姓名 || row.name)
    const gender = normalizeGenderInput(row.性别 || row.gender)
    const studentNo = normalizeCellValue(row.学号 || row.student_no || row.studentNo)
    let className = normalizeCellValue(row.所属班级 || row.班级 || row.class_name)
    if (!className && defaultClassName) {
      className = defaultClassName
    }

    const isEmptyRow = [name, studentNo, className, normalizeCellValue(row.性别 || row.gender)].every(
      value => !value
    )
    if (isEmptyRow) {
      return
    }

    if (!name) {
      errors.push(`第 ${rowNumber} 行缺少“姓名”`)
      return
    }

    if (!gender) {
      errors.push(`第 ${rowNumber} 行“性别”仅支持 男/女`)
      return
    }

    if (!className && !isAdminView.value) {
      errors.push(`第 ${rowNumber} 行缺少“所属班级”`)
      return
    }

    payload.push({
      name,
      gender,
      student_no: studentNo,
      class_name: className
    })
  })

  return { errors, payload }
}

const clearAdminClassFilter = () => {
  router.replace({ path: '/students', query: {} })
}

const loadAllStudents = async () => {
  const allStudents = []
  const pageSize = 1000
  let page = 1
  let total = 0

  do {
    const result = await api.students.list({ page, page_size: pageSize })
    const pageData = result?.data || []
    total = result?.total || pageData.length
    allStudents.push(...pageData)

    if (pageData.length < pageSize) {
      break
    }

    page += 1
  } while (allStudents.length < total)

  return allStudents
}

const ensureClassTeacherCourses = async () => {
  if (!isClassTeacherView.value) {
    return
  }

  classTeacherCourses.value = await userStore.fetchTeachingCourses(true)
}

const goRosterNew = () => {
  if (!selectedCourse.value?.class_id) {
    ElMessage.warning('当前课程未绑定班级，无法新增花名册学生')
    return
  }
  router.push({
    path: '/students/roster/new',
    query: { class_id: String(selectedCourse.value.class_id) }
  })
}

const goRosterEdit = studentId => {
  if (!studentId) {
    return
  }
  router.push(`/students/${studentId}/roster-edit`)
}

const loadStudents = async () => {
  loading.value = true

  try {
    if (isAdminView.value) {
      if (adminFilterClassId.value) {
        const result = await api.students.list({
          class_id: adminFilterClassId.value,
          page: 1,
          page_size: 1000
        })
        students.value = result?.data || []
      } else {
        students.value = await loadAllStudents()
      }
      return
    }

    if (isClassTeacherView.value) {
      await ensureClassTeacherCourses()

      if (!currentClassId.value) {
        students.value = []
        return
      }

      const result = await api.students.list({
        class_id: currentClassId.value,
        page: 1,
        page_size: 1000
      })
      students.value = result?.data || []
      return
    }

    if (!selectedCourse.value) {
      students.value = []
      return
    }

    students.value = await api.courses.getStudents(selectedCourse.value.id)
  } catch (error) {
    console.error('加载学生数据失败', error)
    ElMessage.error('加载学生数据失败')
  } finally {
    loading.value = false
  }
}

const handleFileChange = async event => {
  const file = event.target.files?.[0]
  if (!file) {
    return
  }

  importing.value = true

  try {
    const workbook = await readWorkbook(file)
    const sheetName = workbook.SheetNames?.[0]
    if (!sheetName) {
      ElMessage.error('导入文件为空，请检查后重试')
      return
    }

    const worksheet = workbook.Sheets[sheetName]
    const matrix = XLSX.utils.sheet_to_json(worksheet, { header: 1, defval: '', raw: false })
    const headers = (matrix[0] || []).map(cell => normalizeCellValue(cell).replace(/^\uFEFF/, ''))
    const missingHeaders = TEMPLATE_HEADERS.filter(header => !headers.includes(header))

    if (missingHeaders.length > 0) {
      ElMessage.error(`缺少模板列：${missingHeaders.join('、')}`)
      return
    }

    const rows = XLSX.utils.sheet_to_json(worksheet, { defval: '', raw: false })
    const defaultClassName = isAdminView.value ? '' : defaultTeacherImportClassName.value
    const { errors, payload } = parseImportRows(rows, { defaultClassName })

    if (errors.length > 0) {
      await ElMessageBox.alert(errors.slice(0, 10).join('\n'), '文件校验未通过', {
        confirmButtonText: '知道了'
      })
      return
    }

    if (!payload.length) {
      ElMessage.warning('文件中没有可导入的数据')
      return
    }

    const result = await api.students.batchCreate({ students: payload })
    const createdClasses = result?.created_classes || []
    const successCount = result?.success || 0
    const failedCount = result?.failed || 0

    if (successCount > 0) {
      const successParts = [`成功导入 ${successCount} 名学生`]
      if (createdClasses.length > 0) {
        successParts.push(`自动创建 ${createdClasses.length} 个班级`)
      }
      if (failedCount > 0) {
        successParts.push(`失败 ${failedCount} 条`)
      }
      ElMessage({
        type: failedCount > 0 ? 'warning' : 'success',
        message: successParts.join('，'),
        duration: 5000
      })
    }

    if (failedCount > 0) {
      const detailLines = [
        `成功：${successCount} 人`,
        `失败：${failedCount} 条`
      ]

      if (createdClasses.length > 0) {
        detailLines.push(`自动创建班级：${createdClasses.join('、')}`)
      }

      const errorLines = (result?.errors || []).slice(0, 10)
      if (errorLines.length > 0) {
        detailLines.push('')
        detailLines.push('失败明细：')
        detailLines.push(...errorLines)
      }

      await ElMessageBox.alert(detailLines.join('\n'), '导入结果', {
        confirmButtonText: '知道了'
      })
    }

    await loadStudents()
    fileImportDialogVisible.value = false
  } catch (error) {
    console.error('导入学生名单失败', error)
  } finally {
    importing.value = false
    resetFileInput()
  }
}

const deleteStudent = async student => {
  try {
    await ElMessageBox.confirm(
      `确认删除学生“${student.name}”吗？删除后会同步移除该学生的关联成绩、考勤和课程关联数据。`,
      '删除学生',
      { type: 'warning' }
    )
    await api.students.delete(student.id)
    ElMessage.success('学生已删除')
    await loadStudents()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除学生失败', error)
    }
  }
}

const removeStudent = async row => {
  try {
    await ElMessageBox.confirm(
      `确认将 ${row.student_name} 从 ${selectedCourse.value.name} 的选课名单中移除吗？（不会删除花名册记录）`,
      '移除选课',
      { type: 'warning' }
    )
    await api.courses.removeStudent(selectedCourse.value.id, row.student_id)
    ElMessage.success('已从本课程选课名单中移除')
    await loadStudents()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('移除学生失败', error)
    }
  }
}

const updateEnrollmentType = async (row, value) => {
  if (!selectedCourse.value) {
    return
  }

  try {
    const updated = await api.courses.updateEnrollmentType(selectedCourse.value.id, row.student_id, {
      enrollment_type: value
    })
    const target = students.value.find(item => item.student_id === row.student_id)
    if (target) {
      Object.assign(target, updated)
    }
    ElMessage.success(`已切换为${value === 'elective' ? '选修' : '必修'}`)
  } catch (error) {
    console.error('更新选课方式失败', error)
    await loadStudents()
  }
}

onMounted(async () => {
  if (isAdminView.value) {
    try {
      adminClasses.value = await api.classes.list()
    } catch (e) {
      console.error(e)
    }
  }
  loadStudents()
})

watch(
  () => [selectedCourse.value?.id, userStore.userInfo?.id],
  () => {
    loadStudents()
  }
)

watch(
  () => [route.query.class_id, isAdminView.value],
  async () => {
    if (isAdminView.value && !adminClasses.value.length) {
      try {
        adminClasses.value = await api.classes.list()
      } catch (e) {
        console.error(e)
      }
    }
    loadStudents()
  }
)
</script>

<style scoped>
.students-page {
  padding: 24px;
  min-width: 0;
  overflow-x: hidden;
  width: min(100%, 1180px);
  margin: 0 auto;
}

.students-page :deep(.el-card) {
  min-width: 0;
  border-radius: var(--wa-radius-lg);
  border: 1px solid color-mix(in srgb, var(--wa-border-subtle) 86%, transparent);
  box-shadow: var(--wa-shadow-surface);
}

.students-page :deep(.el-card__body) {
  overflow-x: auto;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
}

.page-header-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
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

.info-alert {
  margin-bottom: 20px;
  border-radius: var(--wa-radius-lg);
}

.admin-class-filter-alert {
  margin-bottom: 16px;
  border-radius: var(--wa-radius-lg);
}

.card-header-block {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-width: 0;
}

.card-actions {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  min-width: 0;
}

@media (max-width: 900px) {
  .card-actions {
    flex-wrap: wrap;
  }
}

.header-count {
  margin-left: 12px;
  color: #64748b;
}

.import-tip {
  margin: 0;
  color: #64748b;
  line-height: 1.6;
}

.hidden-file-input {
  display: none;
}

.file-import-alert {
  margin-bottom: 16px;
}

.file-import-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.file-import-hint {
  margin: 12px 0 0;
  font-size: 13px;
}

.muted-hint {
  color: #94a3b8;
}

.paste-alert {
  margin-bottom: 12px;
}

.paste-textarea {
  margin-top: 8px;
}

.paste-actions {
  margin-top: 12px;
}

.paste-errors {
  margin-top: 12px;
}

.paste-error-list {
  margin: 8px 0 0;
  padding-left: 18px;
}

.paste-preview {
  margin-top: 16px;
}

.paste-preview-title {
  margin: 0 0 8px;
  color: #475569;
  font-size: 14px;
}

.alert-body {
  margin: 0;
  line-height: 1.6;
  color: #334155;
}

@media (max-width: 768px) {
  .students-page {
    padding: 18px 14px;
  }

  .page-header,
  .card-header {
    flex-direction: column;
    align-items: stretch;
  }

  .page-header-actions {
    justify-content: stretch;
  }

  .page-header-actions :deep(.el-button) {
    flex: 1 1 140px;
  }

  .card-actions {
    justify-content: stretch;
  }
}
</style>
