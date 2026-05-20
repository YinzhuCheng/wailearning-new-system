<template>
  <StudentActionMenu
    v-if="showStudentActionMenu"
    :user-id="userId"
    :student-id="studentId"
    :course="course"
  >
    <template #trigger>
      <button
        type="button"
        class="discussion-author-avatar-wrap discussion-author-avatar-wrap--button"
        :title="buttonTitle"
        data-testid="discussion-author-student-action-trigger"
      >
        <el-avatar
          :size="size"
          :src="avatarSrc || undefined"
          class="discussion-author-avatar"
          :class="{ 'discussion-author-avatar--assistant': messageKind === 'llm_assistant' }"
          :style="{ backgroundColor: fallbackColor }"
        >
          {{ fallbackText }}
        </el-avatar>
        <span
          v-if="badgeLabel"
          class="discussion-author-avatar__badge"
          :class="badgeClass"
          :title="badgeTitle"
          aria-hidden="true"
        >
          {{ badgeLabel }}
        </span>
      </button>
    </template>
  </StudentActionMenu>
  <button
    v-else-if="clickable"
    type="button"
    class="discussion-author-avatar-wrap discussion-author-avatar-wrap--button"
    :title="buttonTitle"
    @click="openRecentPosts"
  >
    <el-avatar
      :size="size"
      :src="avatarSrc || undefined"
      class="discussion-author-avatar"
      :class="{ 'discussion-author-avatar--assistant': messageKind === 'llm_assistant' }"
      :style="{ backgroundColor: fallbackColor }"
    >
      {{ fallbackText }}
    </el-avatar>
    <span
      v-if="badgeLabel"
      class="discussion-author-avatar__badge"
      :class="badgeClass"
      :title="badgeTitle"
      aria-hidden="true"
    >
      {{ badgeLabel }}
    </span>
  </button>
  <div v-else class="discussion-author-avatar-wrap">
    <el-avatar
      :size="size"
      :src="avatarSrc || undefined"
      class="discussion-author-avatar"
      :class="{ 'discussion-author-avatar--assistant': messageKind === 'llm_assistant' }"
      :style="{ backgroundColor: fallbackColor }"
    >
      {{ fallbackText }}
    </el-avatar>
    <span
      v-if="badgeLabel"
      class="discussion-author-avatar__badge"
      :class="badgeClass"
      :title="badgeTitle"
      aria-hidden="true"
    >
      {{ badgeLabel }}
    </span>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import StudentActionMenu from '@/components/StudentActionMenu.vue'
import { fetchAttachmentBlobUrl } from '@/utils/attachments'

const props = defineProps({
  userId: { type: [Number, String], default: null },
  avatarUrl: { type: String, default: '' },
  name: { type: String, default: '' },
  role: { type: String, default: '' },
  studentId: { type: [Number, String], default: null },
  course: { type: Object, default: null },
  messageKind: { type: String, default: 'human' },
  size: { type: Number, default: 32 },
})

const router = useRouter()
const avatarSrc = ref('')
let avatarBlobUrl = ''

const clickable = computed(() => props.messageKind !== 'llm_assistant' && props.userId != null && props.userId !== '')
const showStudentActionMenu = computed(() => props.role === 'student' && clickable.value)
const buttonTitle = computed(() => `查看${props.name || '该用户'}的近期发表`)

const openRecentPosts = () => {
  if (!clickable.value) {
    return
  }
  router.push({ name: 'RecentPostsUser', params: { userId: String(props.userId) } })
}

const fallbackText = computed(() => {
  if (props.messageKind === 'llm_assistant') return '助'
  const name = (props.name || '').trim()
  if (name) return name.charAt(0)
  return ({ admin: '管', class_teacher: '班', teacher: '师', student: '学' }[props.role] || '人')
})

const fallbackColor = computed(() => {
  if (props.messageKind === 'llm_assistant') return '#15803d'
  return (
    {
      admin: '#7c3aed',
      class_teacher: '#0d9488',
      teacher: '#2563eb',
      student: '#f59e0b',
    }[props.role] || '#64748b'
  )
})

// Corner badge 管/师/班/学/助 — always shown (including over fetched photo avatars).
const badgeLabel = computed(() => {
  if (props.messageKind === 'llm_assistant') return '助'
  const m = { admin: '管', class_teacher: '班', teacher: '师', student: '学' }
  return m[props.role] || ''
})

const badgeTitle = computed(() => {
  if (props.messageKind === 'llm_assistant') return '智能助教'
  return (
    {
      admin: '管理员',
      class_teacher: '班主任',
      teacher: '教师',
      student: '学生',
    }[props.role] || ''
  )
})

const badgeClass = computed(() => {
  if (props.messageKind === 'llm_assistant') return 'discussion-author-avatar__badge--assistant'
  const k = props.role || 'default'
  return `discussion-author-avatar__badge--role-${k}`
})

const revokeBlob = () => {
  if (avatarBlobUrl) {
    URL.revokeObjectURL(avatarBlobUrl)
    avatarBlobUrl = ''
  }
  avatarSrc.value = ''
}

const loadAvatar = async () => {
  revokeBlob()
  if (!props.avatarUrl) {
    return
  }
  try {
    avatarBlobUrl = await fetchAttachmentBlobUrl(props.avatarUrl)
    avatarSrc.value = avatarBlobUrl
  } catch {
    revokeBlob()
  }
}

watch(
  () => props.avatarUrl,
  () => {
    loadAvatar()
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  revokeBlob()
})
</script>

<style scoped>
.discussion-author-avatar-wrap {
  position: relative;
  flex-shrink: 0;
  align-self: flex-start;
}

.discussion-author-avatar-wrap--button {
  appearance: none;
  border: 0;
  padding: 0;
  margin: 0;
  background: transparent;
  cursor: pointer;
}

.discussion-author-avatar-wrap--button:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 3px;
  border-radius: 999px;
}

.discussion-author-avatar {
  flex-shrink: 0;
  color: #fff;
  font-weight: 700;
  border: 2px solid #fff;
  box-shadow: 0 0 0 1px rgba(15, 23, 42, 0.06);
}

.discussion-author-avatar--assistant {
  box-shadow:
    0 0 0 2px rgba(22, 163, 74, 0.35),
    0 2px 8px rgba(22, 163, 74, 0.18);
}

.discussion-author-avatar__badge {
  position: absolute;
  right: -2px;
  bottom: -2px;
  min-width: 16px;
  height: 16px;
  padding: 0 3px;
  border-radius: 5px;
  font-size: 10px;
  font-weight: 800;
  line-height: 16px;
  text-align: center;
  color: #fff;
  border: 1.5px solid #fff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.18);
  pointer-events: none;
}

.discussion-author-avatar__badge--assistant {
  background: linear-gradient(145deg, #22c55e, #15803d);
}

.discussion-author-avatar__badge--role-admin {
  background: linear-gradient(145deg, #a78bfa, #6d28d9);
}

.discussion-author-avatar__badge--role-class_teacher {
  background: linear-gradient(145deg, #2dd4bf, #0f766e);
}

.discussion-author-avatar__badge--role-teacher {
  background: linear-gradient(145deg, #60a5fa, #1d4ed8);
}

.discussion-author-avatar__badge--role-student {
  background: linear-gradient(145deg, #fbbf24, #d97706);
}

.discussion-author-avatar__badge--role-default {
  background: linear-gradient(145deg, #94a3b8, #475569);
}
</style>
