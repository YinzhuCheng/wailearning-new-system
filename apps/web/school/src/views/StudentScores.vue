<template>
  <div class="student-scores-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">我的成绩</h1>
        <p class="page-subtitle">
          {{
            selectedCourse
              ? `${selectedCourse.name} · 成绩构成与申诉`
              : '请先选择一门课程。'
          }}
        </p>
      </div>
    </div>

    <el-empty v-if="!selectedCourse" description="请先选择一门课程。" />

    <template v-else>
      <el-card shadow="never" class="toolbar-card">
        <el-select v-model="semester" placeholder="选择学期" style="width: 220px" @change="loadComposition">
          <el-option v-for="item in semesters" :key="item.id" :label="item.name" :value="item.name" />
        </el-select>
      </el-card>

      <el-card v-loading="loading" shadow="never" class="composition-card">
        <template #header>
          <strong>成绩构成</strong>
        </template>
        <el-alert
          v-if="composition && !composition.scheme?.inner_parts_valid"
          type="warning"
          :closable="false"
          class="mb-16"
          title="当前课程的作业平时分、其他平时分与各次考试占比之和不为 100%，系统暂不计算加权总成绩。请联系任课教师调整。"
        />
        <div v-if="composition" class="scheme-row">
          <el-tag type="success">作业平时分 {{ composition.scheme.homework_weight }}%</el-tag>
          <el-tag type="warning">{{ composition.scheme.other_daily_label }} {{ composition.scheme.extra_daily_weight }}%</el-tag>
          <el-tag
            v-for="w in composition.scheme.exam_weights"
            :key="w.exam_type"
            type="info"
          >
            {{ w.exam_type }} {{ w.weight }}%
          </el-tag>
        </div>
        <el-descriptions v-if="composition" :column="1" border class="mt-16">
          <el-descriptions-item label="作业平时分（均分折算百分制）">
            {{ composition.homework_average_percent != null ? composition.homework_average_percent : '暂无已批改作业' }}
          </el-descriptions-item>
          <el-descriptions-item :label="composition.scheme.other_daily_label">
            {{ composition.other_daily_score != null ? composition.other_daily_score : '教师尚未录入' }}
          </el-descriptions-item>
          <el-descriptions-item
            v-for="w in composition.scheme.exam_weights"
            :key="w.exam_type"
            :label="w.exam_type + '（教师录入）'"
          >
            {{ composition.exam_scores[w.exam_type] != null ? composition.exam_scores[w.exam_type] : '未录入' }}
          </el-descriptions-item>
          <el-descriptions-item label="加权总成绩">
            <el-tag v-if="composition.weighted_total != null" type="primary" size="large">
              {{ composition.weighted_total }}
            </el-tag>
            <span v-else>无法计算（{{ (composition.missing_for_total || []).join('、') }}）</span>
          </el-descriptions-item>
        </el-descriptions>

        <h3 class="subsection-title">各次作业得分</h3>
        <el-table :data="composition?.homework_assignments || []" size="small" empty-text="暂无作业记录">
          <el-table-column prop="title" label="作业" min-width="160" />
          <el-table-column prop="review_score" label="得分" width="90">
            <template #default="{ row }">{{ row.review_score != null ? row.review_score : '—' }}</template>
          </el-table-column>
          <el-table-column prop="max_score" label="满分" width="80" />
          <el-table-column prop="percent_equivalent" label="折算百分制" width="120">
            <template #default="{ row }">{{ row.percent_equivalent != null ? row.percent_equivalent : '—' }}</template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <strong>成绩申诉</strong>
        </template>
        <p class="hint">可对总成绩或任一组成部分提出申诉，教师将在成绩管理中回复。</p>
        <el-form label-width="100px" class="appeal-form">
          <el-form-item label="申诉对象">
            <el-select v-model="appealForm.target_component" placeholder="选择" style="width: 100%">
              <el-option label="加权总成绩" value="total" />
              <el-option label="作业平时分（均分）" value="homework_avg" />
              <el-option label="单次作业成绩" value="homework" />
              <el-option :label="OTHER_DAILY" :value="OTHER_DAILY" />
              <el-option
                v-for="w in composition?.scheme?.exam_weights || []"
                :key="w.exam_type"
                :label="w.exam_type"
                :value="w.exam_type"
              />
            </el-select>
          </el-form-item>
          <el-form-item v-if="appealForm.target_component === 'homework'" label="选择作业">
            <el-select
              v-model="appealForm.homework_id"
              placeholder="选择要申诉的作业"
              style="width: 100%"
            >
              <el-option
                v-for="item in appealableHomeworkAssignments"
                :key="item.homework_id"
                :label="item.title"
                :value="item.homework_id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="申诉理由">
            <el-input v-model="appealForm.reason_text" type="textarea" :rows="4" maxlength="2000" show-word-limit />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="appealSubmitting" @click="submitAppeal">提交申诉</el-button>
          </el-form-item>
        </el-form>
      </el-card>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import api from '@/api'
import { useUserStore } from '@/stores/user'

const OTHER_DAILY = '其他平时分'

const userStore = useUserStore()
const selectedCourse = computed(() => userStore.selectedCourse)
const semesters = ref([])
const semester = ref('')
const loading = ref(false)
const composition = ref(null)
const appealSubmitting = ref(false)
const appealForm = ref({
  target_component: 'total',
  reason_text: '',
  homework_id: null
})

const appealableHomeworkAssignments = computed(() =>
  (composition.value?.homework_assignments || []).filter(item => item.review_score != null)
)

const loadSemesters = async () => {
  semesters.value = await api.semesters.list()
  if (!semester.value && semesters.value.length) {
    semester.value = semesters.value[0].name
  }
}

const loadComposition = async () => {
  if (!selectedCourse.value || !semester.value) {
    composition.value = null
    return
  }
  loading.value = true
  try {
    composition.value = await api.scores.getMyComposition({
      subject_id: selectedCourse.value.id,
      semester: semester.value
    })
  } finally {
    loading.value = false
  }
}

const submitAppeal = async () => {
  if (!selectedCourse.value || !semester.value) {
    return
  }
  if (!appealForm.value.reason_text.trim()) {
    ElMessage.warning('请填写申诉理由')
    return
  }
  if (appealForm.value.target_component === 'homework' && !appealForm.value.homework_id) {
    ElMessage.warning('请选择要申诉的作业')
    return
  }
  appealSubmitting.value = true
  try {
    const payload = {
      semester: semester.value,
      target_component: appealForm.value.target_component,
      reason_text: appealForm.value.reason_text.trim(),
      homework_id: appealForm.value.target_component === 'homework' ? appealForm.value.homework_id : null
    }
    await api.scores.createAppeal(selectedCourse.value.id, payload)
    ElMessage.success('申诉已提交')
    appealForm.value = { target_component: 'total', reason_text: '', homework_id: null }
  } finally {
    appealSubmitting.value = false
  }
}

watch(
  () => appealForm.value.target_component,
  targetComponent => {
    if (targetComponent !== 'homework') {
      appealForm.value.homework_id = null
    }
  }
)

onMounted(async () => {
  await loadSemesters()
  await loadComposition()
})

watch(
  () => userStore.selectedCourse,
  async () => {
    await loadComposition()
  }
)
</script>

<style scoped>
.student-scores-page {
  padding: 24px;
  width: min(100%, 1120px);
  margin: 0 auto;
  min-width: 0;
}

.page-header {
  display: flex;
  justify-content: flex-start;
  margin-bottom: 24px;
}

.page-title {
  margin: 0 0 8px;
  font-size: 28px;
  color: var(--wa-color-text);
}

.page-subtitle {
  margin: 0;
  color: var(--wa-color-text-muted);
}

.toolbar-card {
  margin-bottom: 16px;
  border-radius: var(--wa-radius-lg);
  border: 1px solid color-mix(in srgb, var(--wa-border-subtle) 86%, transparent);
  background: color-mix(in srgb, var(--wa-color-surface) 90%, var(--wa-color-bg-soft));
  box-shadow: 0 4px 14px color-mix(in srgb, var(--wa-color-text) 4%, transparent);
}

.composition-card {
  margin-bottom: 20px;
  border-radius: var(--wa-radius-lg);
  border: 1px solid color-mix(in srgb, var(--wa-border-subtle) 86%, transparent);
  box-shadow: var(--wa-shadow-surface);
}

.student-scores-page > :deep(.el-card:not(.toolbar-card):not(.composition-card)) {
  border-radius: var(--wa-radius-lg);
  border: 1px solid color-mix(in srgb, var(--wa-border-subtle) 86%, transparent);
  box-shadow: var(--wa-shadow-surface);
}

.scheme-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.mb-16 {
  margin-bottom: 16px;
}

.mt-16 {
  margin-top: 16px;
}

.subsection-title {
  margin: 20px 0 12px;
  font-size: 16px;
  color: var(--wa-color-text);
}

.hint {
  margin: 0 0 16px;
  color: var(--wa-color-text-muted);
  font-size: 14px;
}

.appeal-form {
  max-width: 560px;
}

@media (max-width: 768px) {
  .student-scores-page {
    padding: 16px;
  }
}
</style>
