<template>
  <el-dropdown
    v-if="hasActions"
    trigger="click"
    class="student-action-menu"
    data-testid="student-action-menu"
    @command="handleCommand"
  >
    <slot name="trigger">
      <el-button
        :type="buttonType"
        :size="size"
        :link="link"
        :text="text"
        :circle="circle"
        class="student-action-menu__button"
        :aria-label="ariaLabel"
        :title="ariaLabel"
        data-testid="student-action-menu-button"
      >
        <el-icon><MoreFilled /></el-icon>
        <span v-if="showLabel" class="student-action-menu__label">操作</span>
      </el-button>
    </slot>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item v-if="canViewRecentPosts" command="recent-posts" data-testid="student-action-menu-recent-posts">
          <el-icon><ChatDotRound /></el-icon>
          <span>近期发表</span>
        </el-dropdown-item>
        <el-dropdown-item v-if="canViewHomeworkStatus" command="homework-status" data-testid="student-action-menu-homework-status">
          <el-icon><Document /></el-icon>
          <span>作业状态</span>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ChatDotRound, Document, MoreFilled } from '@element-plus/icons-vue'

import { useUserStore } from '@/stores/user'

const props = defineProps({
  userId: { type: [Number, String], default: null },
  studentId: { type: [Number, String], default: null },
  course: { type: Object, default: null },
  size: { type: String, default: 'small' },
  buttonType: { type: String, default: 'primary' },
  link: { type: Boolean, default: true },
  text: { type: Boolean, default: false },
  circle: { type: Boolean, default: false },
  showLabel: { type: Boolean, default: false },
})

const router = useRouter()
const userStore = useUserStore()

const activeCourse = computed(() => props.course || userStore.selectedCourse || null)
const canViewRecentPosts = computed(() => props.userId != null && props.userId !== '')
const isCourseInstructor = computed(() => {
  const course = activeCourse.value
  const currentUserId = userStore.userInfo?.id
  if (!course?.id || !currentUserId) return false
  if (userStore.isAdmin) return true
  if (!userStore.isTeacher && !userStore.isClassTeacher) return false
  return String(course.teacher_id || '') === String(currentUserId)
})
const canViewHomeworkStatus = computed(
  () => props.studentId != null && props.studentId !== '' && activeCourse.value?.id && isCourseInstructor.value
)
const hasActions = computed(() => canViewRecentPosts.value || canViewHomeworkStatus.value)
const ariaLabel = computed(() => '学生操作')

const openRecentPosts = () => {
  if (!canViewRecentPosts.value) return
  router.push({ name: 'RecentPostsUser', params: { userId: String(props.userId) } })
}

const openHomeworkStatus = () => {
  if (!canViewHomeworkStatus.value) return
  userStore.setSelectedCourse(activeCourse.value, { reason: 'user' })
  router.push({
    name: 'StudentHomeworkByCourse',
    query: { student_id: String(props.studentId) }
  })
}

const handleCommand = command => {
  if (command === 'recent-posts') {
    openRecentPosts()
    return
  }
  if (command === 'homework-status') {
    openHomeworkStatus()
  }
}
</script>

<style scoped>
.student-action-menu {
  display: inline-flex;
  vertical-align: middle;
}

.student-action-menu__button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.student-action-menu__label {
  line-height: 1;
}
</style>
