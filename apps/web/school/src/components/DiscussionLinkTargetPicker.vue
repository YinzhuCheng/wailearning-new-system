<template>
  <div class="discussion-link-picker">
    <el-button plain size="small" data-testid="discussion-link-picker-open" @click="openDialog">添加链接</el-button>

    <el-dialog
      v-model="dialogVisible"
      title="添加内容链接"
      width="min(720px, calc(100vw - 28px))"
      destroy-on-close
      class="discussion-link-picker-dialog"
    >
      <div class="discussion-link-picker__controls">
        <el-radio-group v-model="activeType" size="small">
          <el-radio-button label="homework">作业</el-radio-button>
          <el-radio-button label="material">资料</el-radio-button>
          <el-radio-button label="learning_note">笔记</el-radio-button>
          <el-radio-button label="course">课程</el-radio-button>
          <el-radio-button label="discussion_entry">评论</el-radio-button>
        </el-radio-group>
        <el-input
          v-model="searchText"
          clearable
          placeholder="按标题搜索可见内容"
          class="discussion-link-picker__search"
          data-testid="discussion-link-picker-search"
        />
      </div>

      <div v-loading="loading" class="discussion-link-picker__results" data-testid="discussion-link-picker-results">
        <el-empty v-if="!loading && !rows.length" description="没有找到可添加的内容" />
        <div v-for="item in rows" :key="targetKey(item)" class="discussion-link-picker__row">
          <div class="discussion-link-picker__meta">
            <span class="discussion-link-picker__type">{{ item.target_label }}</span>
            <strong>{{ item.title }}</strong>
            <span v-if="item.secondary_text" class="discussion-link-picker__secondary">{{ item.secondary_text }}</span>
          </div>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="selectedKeys.has(targetKey(item))"
            data-testid="discussion-link-picker-add"
            @click="attach(item)"
          >
            {{ selectedKeys.has(targetKey(item)) ? '已添加' : '添加' }}
          </el-button>
        </div>
      </div>

      <template #footer>
        <el-button @click="dialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

import api from '@/api'
import { discussionLinkedTargetKey as targetKey } from '@/utils/discussionLinkTargets'

const props = defineProps({
  preferredSubjectId: {
    type: Number,
    default: null
  },
  selectedTargets: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['select'])

const dialogVisible = ref(false)
const activeType = ref('homework')
const searchText = ref('')
const rows = ref([])
const loading = ref(false)
let debounceTimer = null

const selectedKeys = computed(() => new Set(props.selectedTargets.map(item => targetKey(item))))

const loadRows = async () => {
  if (!dialogVisible.value) return
  loading.value = true
  try {
    const result = await api.discussions.searchTargets({
      target_type: activeType.value,
      q: searchText.value || undefined,
      preferred_subject_id: props.preferredSubjectId || undefined,
      limit: 16
    })
    rows.value = result?.data || []
  } finally {
    loading.value = false
  }
}

const scheduleLoad = () => {
  if (debounceTimer) {
    window.clearTimeout(debounceTimer)
  }
  debounceTimer = window.setTimeout(loadRows, 180)
}

const openDialog = () => {
  dialogVisible.value = true
  loadRows()
}

const attach = item => {
  emit('select', item)
  dialogVisible.value = false
}

watch(
  () => [dialogVisible.value, activeType.value, searchText.value, props.preferredSubjectId],
  () => {
    scheduleLoad()
  }
)
</script>

<style scoped>
.discussion-link-picker__controls {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 12px;
  align-items: center;
  margin-bottom: 14px;
}

.discussion-link-picker__search {
  flex: 1 1 260px;
}

.discussion-link-picker__results {
  min-height: 180px;
  max-height: min(52vh, 430px);
  overflow: auto;
  padding-right: 4px;
}

.discussion-link-picker__row {
  display: flex;
  gap: 14px;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.discussion-link-picker__row:last-child {
  border-bottom: none;
}

.discussion-link-picker__meta {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.discussion-link-picker__meta strong {
  color: #0f172a;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.discussion-link-picker__type {
  color: #0369a1;
  font-size: 12px;
  font-weight: 700;
}

.discussion-link-picker__secondary {
  color: #64748b;
  font-size: 12px;
  line-height: 1.4;
}

@media (max-width: 720px) {
  .discussion-link-picker__controls {
    align-items: stretch;
    flex-direction: column;
  }

  .discussion-link-picker__controls :deep(.el-radio-group) {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    width: 100%;
  }

  .discussion-link-picker__controls :deep(.el-radio-button__inner) {
    width: 100%;
    padding-inline: 8px;
  }

  .discussion-link-picker__search {
    flex-basis: auto;
    width: 100%;
  }

  .discussion-link-picker__row {
    align-items: flex-start;
    flex-direction: column;
  }

  .discussion-link-picker__row :deep(.el-button) {
    width: 100%;
  }
}
</style>
