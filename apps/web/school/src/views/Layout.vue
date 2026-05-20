<template>
  <el-container
    class="layout-container"
    :class="{
      'layout-container--mobile-sidebar-open': isMobile && !isCollapsed,
      'layout-container--sidebar-hidden': !isMobile && isSidebarHidden
    }"
  >
    <div v-if="isMobile && !isCollapsed" class="mobile-sidebar-backdrop" @click="isCollapsed = true" />
    <el-aside
      :width="sidebarWidth"
      class="sidebar"
      :class="{
        'sidebar--hidden': isSidebarHidden && !isMobile,
        'sidebar--mobile-collapsed': isMobile && isCollapsed
      }"
    >
      <div class="logo">
        <div class="logo-main">
          <div class="logo-icon">
            <img :src="courseEvalMark" alt="" class="logo-mark" />
          </div>
          <div v-if="!isCollapsed" class="logo-texts">
            <h2>CourseEval</h2>
            <p>大学教学管理系统</p>
          </div>
        </div>
      </div>

      <div class="sidebar-body">
        <el-menu
          :default-active="sidebarMenuActivePath"
          :default-openeds="homeworkMenuOpenIndices"
          :collapse="isCollapsed"
          router
          class="sidebar-menu sidebar-menu--scroll"
        >
          <template v-for="item in menuItems" :key="item.type === 'submenu' ? item.index : item.path">
            <el-sub-menu v-if="item.type === 'submenu'" :index="item.index">
              <template #title>
                <el-icon><component :is="item.icon" /></el-icon>
                <span>{{ item.label }}</span>
              </template>
              <el-menu-item v-for="child in item.children" :key="child.path" :index="child.path">
                <el-icon><component :is="child.icon" /></el-icon>
                <template #title>{{ child.label }}</template>
              </el-menu-item>
            </el-sub-menu>
            <el-menu-item v-else :index="item.path">
              <el-icon><component :is="item.icon" /></el-icon>
              <template #title>{{ item.label }}</template>
            </el-menu-item>
          </template>
        </el-menu>

        <div class="sidebar-footer">
          <div v-show="!isCollapsed" class="sidebar-footer__section-title">账户</div>
          <el-tooltip content="近期发表" placement="right" :disabled="!isCollapsed || isMobile">
            <button
              type="button"
              class="sidebar-footer__btn"
              :class="{ 'sidebar-footer__btn--active': route.path === '/recent-posts/me' }"
              data-testid="sidebar-recent-posts"
              @click="goRecentPosts"
            >
              <el-icon :size="18"><Clock /></el-icon>
              <span v-show="!isCollapsed" class="sidebar-footer__label">近期发表</span>
            </button>
          </el-tooltip>
          <el-tooltip content="通知中心" placement="right" :disabled="!isCollapsed || isMobile">
            <button
              type="button"
              class="sidebar-footer__btn"
              :class="{ 'sidebar-footer__btn--active': route.path === '/notifications' }"
              data-testid="sidebar-notifications"
              @click="goNotifications"
            >
              <el-icon :size="18"><Bell /></el-icon>
              <span v-show="!isCollapsed" class="sidebar-footer__label">通知中心</span>
              <span v-if="!isCollapsed && headerUnreadCount > 0" class="sidebar-footer__badge">
                {{ headerUnreadCount > 99 ? '99+' : headerUnreadCount }}
              </span>
            </button>
          </el-tooltip>
          <el-tooltip content="个人设置" placement="right" :disabled="!isCollapsed || isMobile">
            <button
              type="button"
              class="sidebar-footer__btn"
              :class="{ 'sidebar-footer__btn--active': route.path === '/personal-settings' }"
              data-testid="sidebar-personal-settings"
              @click="goPersonalSettings"
            >
              <el-icon :size="18"><Setting /></el-icon>
              <span v-show="!isCollapsed" class="sidebar-footer__label">个人设置</span>
            </button>
          </el-tooltip>
          <el-tooltip content="退出登录" placement="right" :disabled="!isCollapsed || isMobile">
            <button type="button" class="sidebar-footer__btn sidebar-footer__btn--danger" data-testid="sidebar-logout" @click="sidebarLogout">
              <el-icon :size="18"><SwitchButton /></el-icon>
              <span v-show="!isCollapsed" class="sidebar-footer__label">退出登录</span>
            </button>
          </el-tooltip>
        </div>
      </div>
    </el-aside>

    <button
      v-if="!isMobile"
      type="button"
      class="sidebar-edge-handle"
      :class="{
        'sidebar-edge-handle--hidden': !isMobile && isSidebarHidden,
        'sidebar-edge-handle--drawer-open': isMobile && !isCollapsed
      }"
      :style="sidebarHandleStyle"
      :aria-label="sidebarHandleLabel"
      :title="sidebarHandleLabel"
      data-testid="sidebar-edge-handle"
      @click="toggleSidebarDrawer"
    >
      <el-icon :size="18">
        <component :is="sidebarHandleIcon" />
      </el-icon>
    </button>

    <el-container>
      <el-header class="header">
        <div class="header-left">
          <el-button
            v-if="isMobile"
            class="mobile-menu-btn"
            :icon="isCollapsed ? Expand : Fold"
            circle
            size="small"
            aria-label="打开导航菜单"
            @click="toggleMobileSidebar"
          />
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: homePath }">首页</el-breadcrumb-item>
            <el-breadcrumb-item v-if="homeworkBreadcrumbParent" :to="{ path: '/homework' }">
              作业
            </el-breadcrumb-item>
            <el-breadcrumb-item>{{ currentRouteName }}</el-breadcrumb-item>
          </el-breadcrumb>

          <div v-if="showClassContext" class="context-chip context-chip--class">
            <span class="context-chip__label">当前班级</span>
            <div class="context-chip__meta">
              <strong>{{ currentClassName }}</strong>
              <span>{{ classContextText }}</span>
            </div>
          </div>

          <div v-else-if="showCourseContext" class="context-chip context-chip--course">
            <span class="context-chip__label">当前课程</span>
            <div class="context-chip__meta">
              <strong>{{ selectedCourse?.name }}</strong>
              <span>{{ selectedCourse?.semester || '未设置学期' }}</span>
            </div>
            <el-tag size="small" type="primary">
              {{ selectedCourse?.course_type === 'elective' ? '选修课' : '必修课' }}
            </el-tag>
          </div>
        </div>

        <div class="header-right">
          <el-dropdown v-if="showCourseSwitcher" trigger="click" data-testid="header-course-switch" popper-class="course-dropdown-popper" @command="handleCourseSwitch">
            <el-button text>
              切换课程
              <el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu class="course-dropdown-menu">
                <el-dropdown-item
                  v-for="course in availableCourses"
                  :key="course.id"
                  :command="course.id"
                  :class="{ 'is-current-course': selectedCourse?.id === course.id }"
                >
                  <div class="course-option">
                    <strong>{{ course.name }}</strong>
                    <span>{{ course.semester || '未设置学期' }}</span>
                  </div>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <el-dropdown trigger="hover" data-testid="header-user-menu" popper-class="user-profile-dropdown" @visible-change="onUserMenuVisible" @command="handleCommand">
            <el-badge
              :value="headerUnreadCount"
              :hidden="headerUnreadCount === 0"
              :max="99"
              class="header-user-badge"
              data-testid="header-notification-badge"
            >
              <div class="user-box">
                <el-avatar :size="34" :src="headerAvatarSrc || undefined">
                  {{ userStore.userInfo?.real_name?.charAt(0) || 'U' }}
                </el-avatar>
                <div v-if="!isCollapsed" class="user-meta">
                  <strong>{{ userStore.userInfo?.real_name }}</strong>
                  <span>{{ roleText(userStore.userInfo?.role) }}</span>
                </div>
              </div>
            </el-badge>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled class="user-dropdown-card">
                  <div class="user-dropdown-profile">
                    <el-avatar :size="72" :src="headerAvatarSrc || undefined">
                      {{ userStore.userInfo?.real_name?.charAt(0) || 'U' }}
                    </el-avatar>
                    <div class="user-dropdown-id">
                      <strong>{{ userStore.userInfo?.real_name || userStore.userInfo?.username || 'User' }}</strong>
                      <span>{{ roleText(userStore.userInfo?.role) }}</span>
                      <small>{{ userStore.userInfo?.username }}</small>
                    </div>
                  </div>
                  <div class="user-dropdown-token">
                    <div class="user-dropdown-token__row">
                      <span>LLM token</span>
                      <strong>{{ tokenUsageLabel }}</strong>
                    </div>
                    <el-progress
                      :percentage="tokenUsagePercent"
                      :stroke-width="10"
                      :show-text="false"
                      :color="quotaBarColors"
                    />
                    <p>{{ tokenDetailText }}</p>
                  </div>
                </el-dropdown-item>
                <el-dropdown-item command="recent-posts">近期发表</el-dropdown-item>
                <el-dropdown-item command="notifications">通知中心</el-dropdown-item>
                <el-dropdown-item command="personal-settings">个人设置</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="main-content">
        <router-view />
      </el-main>

      <el-footer class="footer">
        {{ userStore.systemSettings?.copyright || '(c) 2026 CourseEval' }}
      </el-footer>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElNotification } from 'element-plus'
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  Bell,
  Calendar,
  Clock,
  Collection,
  Document,
  EditPen,
  Expand,
  Fold,
  House,
  Reading,
  School,
  Setting,
  SwitchButton,
  Trophy,
  User,
  UserFilled
} from '@element-plus/icons-vue'

import api from '@/api'
import courseEvalMark from '@/assets/brand/courseeval-mark.svg'
import { useUserStore } from '@/stores/user'
import { fetchAttachmentBlobUrl } from '@/utils/attachments'
import { filterCoursesByClassId, resolveClassTeacherClassId, resolveClassTeacherClassName } from '@/utils/classTeacher'
import {
  DEFAULT_NOTIFICATION_POLL_INTERVAL_MS,
  emitNotificationRefresh,
  startNotificationPolling,
  subscribeNotificationBroadcast
} from '@/utils/notificationSync'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const adminHomePath = '/students'
const mobileBreakpoint = 768
const desktopSidebarStorageKey = 'courseeval-school-sidebar-state'
const isCollapsed = ref(false)
const isSidebarHidden = ref(false)
const isMobile = ref(false)

const headerAvatarSrc = ref('')
let headerAvatarBlobUrl = ''
const headerQuotaSummary = ref(null)
const headerQuotaLoading = ref(false)
const headerQuotaError = ref(false)

const revokeHeaderAvatarBlob = () => {
  if (headerAvatarBlobUrl) {
    URL.revokeObjectURL(headerAvatarBlobUrl)
    headerAvatarBlobUrl = ''
  }
  headerAvatarSrc.value = ''
}

const loadHeaderAvatar = async () => {
  revokeHeaderAvatarBlob()
  const url = userStore.userInfo?.avatar_url
  if (!url) {
    return
  }
  try {
    headerAvatarBlobUrl = await fetchAttachmentBlobUrl(url)
    headerAvatarSrc.value = headerAvatarBlobUrl
  } catch (error) {
    console.error('加载头像失败', error)
  }
}

const lastNotificationSyncSignature = ref(null)
const headerUnreadCount = ref(0)
const headerLastPollUnread = ref(null)
const headerLastPollTotal = ref(null)
const lastNotificationToastSignature = ref(null)
let stopNotificationPolling = () => {}
let unsubscribeNotificationBroadcast = () => {}

const notificationSyncParams = computed(() => {
  if (userStore.isAdmin) {
    return null
  }

  if ((userStore.isTeacher || userStore.isStudent) && selectedCourse.value?.id) {
    return { subject_id: selectedCourse.value.id }
  }

  return {}
})

const quotaBarColors = [
  { color: '#93c5fd', percentage: 60 },
  { color: '#3b82f6', percentage: 85 },
  { color: '#f59e0b', percentage: 95 },
  { color: '#ef4444', percentage: 100 }
]

const tokenUsageLimit = computed(() =>
  Number(headerQuotaSummary.value?.daily_student_token_limit ?? headerQuotaSummary.value?.global_default_daily_student_tokens ?? 0)
)
const tokenUsageUsed = computed(() => Number(headerQuotaSummary.value?.student_used_tokens_today ?? 0))
const tokenUsagePercent = computed(() => {
  if (!userStore.isStudent || !tokenUsageLimit.value) {
    return 0
  }
  return Math.min(100, Math.round((tokenUsageUsed.value / tokenUsageLimit.value) * 1000) / 10)
})
const tokenUsageLabel = computed(() => {
  if (!userStore.isStudent) {
    return 'system policy'
  }
  if (headerQuotaLoading.value) {
    return 'loading'
  }
  if (headerQuotaError.value) {
    return 'unavailable'
  }
  if (!tokenUsageLimit.value) {
    return 'no data'
  }
  return `${tokenUsageUsed.value} / ${tokenUsageLimit.value}`
})
const tokenDetailText = computed(() => {
  if (!userStore.isStudent) {
    return 'Managed in system LLM quota settings.'
  }
  if (headerQuotaError.value) {
    return 'Unable to load today quota.'
  }
  if (!headerQuotaSummary.value) {
    return 'Hover to load today quota.'
  }
  const remaining = headerQuotaSummary.value.student_remaining_tokens_today ?? Math.max(0, tokenUsageLimit.value - tokenUsageUsed.value)
  if (tokenUsageLimit.value > 0 && tokenUsageUsed.value > tokenUsageLimit.value) {
    return `Over limit by ${tokenUsageUsed.value - tokenUsageLimit.value} · ${headerQuotaSummary.value.usage_date || ''} ${headerQuotaSummary.value.quota_timezone || ''}`.trim()
  }
  return `Remaining ${remaining} · ${headerQuotaSummary.value.usage_date || ''} ${headerQuotaSummary.value.quota_timezone || ''}`.trim()
})

const loadHeaderQuotaSummary = async () => {
  if (!userStore.isStudent || headerQuotaLoading.value) {
    return
  }
  headerQuotaLoading.value = true
  try {
    headerQuotaSummary.value = await api.llmSettings.getStudentQuotasSummary()
    headerQuotaError.value = false
  } catch (error) {
    console.error('load header quota failed', error)
    headerQuotaSummary.value = null
    headerQuotaError.value = true
  } finally {
    headerQuotaLoading.value = false
  }
}

const onUserMenuVisible = visible => {
  if (visible) {
    loadHeaderQuotaSummary()
  }
}

const pollNotificationSync = async () => {
  if (!userStore.isLoggedIn) {
    return
  }

  const params = notificationSyncParams.value || {}

  try {
    const status = await api.notifications.syncStatus(params)
    const unread = Number(status.unread_count || 0)
    const total = Number(status.total || 0)
    headerUnreadCount.value = unread

    const signature = `${total}:${unread}:${status.latest_updated_at || ''}`
    const hadBaseline = lastNotificationSyncSignature.value !== null
    const prevUnread = headerLastPollUnread.value
    const prevTotal = headerLastPollTotal.value

    if (hadBaseline && signature !== lastNotificationSyncSignature.value) {
      emitNotificationRefresh()
    }

    const looksLikeNewUnread =
      hadBaseline &&
      (unread > (prevUnread ?? 0) || (total > (prevTotal ?? 0) && unread > 0))

    if (looksLikeNewUnread && lastNotificationToastSignature.value !== signature) {
      lastNotificationToastSignature.value = signature
      ElNotification({
        title: '新通知',
        message:
          unread > 0
            ? `您有 ${unread} 条未读通知，请打开底部「通知中心」查看。`
            : '通知列表已更新。',
        type: unread > 0 ? 'info' : 'success',
        duration: 5200,
        position: 'top-right'
      })
    }

    lastNotificationSyncSignature.value = signature
    headerLastPollUnread.value = unread
    headerLastPollTotal.value = total
  } catch (error) {
    console.error('通知同步检查失败', error)
  }
}

const selectedCourse = computed(() => userStore.selectedCourse)
const availableCourses = computed(() => userStore.teachingCourses || [])
const currentClassId = computed(() => resolveClassTeacherClassId(userStore.userInfo, availableCourses.value))
const classTeacherCourses = computed(() => filterCoursesByClassId(availableCourses.value, currentClassId.value))
const currentClassName = computed(() => resolveClassTeacherClassName(userStore.userInfo, availableCourses.value) || '未分配班级')

const homePath = computed(() => {
  if (userStore.isAdmin) {
    return adminHomePath
  }

  return userStore.isStudent ? '/courses' : '/students'
})

const showClassContext = computed(() => userStore.isClassTeacher && Boolean(currentClassId.value))
const showCourseContext = computed(() => !userStore.isAdmin && !userStore.isClassTeacher && Boolean(selectedCourse.value))
const showCourseSwitcher = computed(() => !userStore.isAdmin && !userStore.isClassTeacher && availableCourses.value.length > 0)
const sidebarWidth = computed(() => {
  if (isMobile.value) {
    return isCollapsed.value ? '0px' : '240px'
  }
  if (isSidebarHidden.value) {
    return '0px'
  }
  return isCollapsed.value ? '72px' : '240px'
})
const sidebarHandleStyle = computed(() => {
  if (isMobile.value) {
    return { left: isCollapsed.value ? '0px' : '226px' }
  }

  return { left: isSidebarHidden.value ? '0px' : `calc(${sidebarWidth.value} - 14px)` }
})
const sidebarHandleLabel = computed(() => {
  if (isMobile.value) {
    return isCollapsed.value ? '打开导航菜单' : '关闭导航菜单'
  }

  return isSidebarHidden.value ? '拉出侧边栏' : '隐藏侧边栏'
})
const sidebarHandleIcon = computed(() => {
  if (isMobile.value) {
    return isCollapsed.value ? ArrowRight : ArrowLeft
  }

  return isSidebarHidden.value ? ArrowRight : ArrowLeft
})
const classContextText = computed(() => `班级课程 ${classTeacherCourses.value.length} 门`)

const routeNameMap = {
  '/courses': '选课与进度',
  '/course-home': '学习主页',
  '/classes': '班级管理',
  '/students': '学生信息',
  '/scores': '成绩管理',
  '/student-scores': '我的成绩',
  '/attendance': '考勤管理',
  '/rankings': '班级排名',
  '/analysis': '数据分析',
  '/users': '用户管理',
  '/subjects': '课程信息',
  '/semesters': '学期管理',
  '/logs': '操作日志',
  '/points': '积分系统',
  '/points-display': '积分展示',
  '/settings': '系统设置',
  '/materials': '课程目录',
  '/learning-notes': '学习笔记',
  '/homework': '作业管理',
  '/homework/students': '学生作业一览',
  '/homework/by-student': '学生作业一览',
  '/notifications': '消息与通知',
  '/personal-settings': '个人设置'
}

const currentRouteName = computed(() => route.meta?.title || routeNameMap[route.path] || '页面')

const homeworkBreadcrumbParent = computed(() => {
  const p = route.path
  return p === '/homework/students' || /^\/homework\/\d+\//.test(p)
})

/**
 * Element Plus menu `index` matches top-level routes like `/materials`, but nested routes
 * such as `/materials/read/:id` must highlight the parent item so teachers/students see where they are.
 */
const sidebarMenuActivePath = computed(() => {
  const p = route.path
  if (p.startsWith('/materials/read/')) {
    return '/materials'
  }
  if (p.startsWith('/homework/') && p !== '/homework') {
    if (p.startsWith('/homework/students')) {
      return '/homework/students'
    }
    return '/homework'
  }
  return p
})

const homeworkMenuOpenIndices = computed(() => {
  const p = route.path
  if (userStore.isStudent) {
    // Student rail is flat, so there is no submenu to pre-open.
    return []
  }
  if (userStore.isAdmin) {
    const open = []
    if (p.startsWith('/semesters') || p.startsWith('/settings')) {
      open.push('admin-academic-config')
    }
    if (p.startsWith('/logs')) {
      open.push('admin-ops')
    }
    return open
  }
  if (userStore.isClassTeacher) {
    if (
      p.startsWith('/students') ||
      p.startsWith('/subjects')
    ) {
      return ['class-teaching']
    }
    return []
  }
  // Teacher accounts use a flat sidebar, so there is no submenu to pre-open here.
  return []
})

const classTeacherMenu = [
  {
    type: 'submenu',
    index: 'class-teaching',
    label: '班级教学',
    icon: School,
    children: [
      { path: '/students', label: '学生信息', icon: User },
      { path: '/subjects', label: '课程信息', icon: Reading }
    ]
  }
]

/** Flat menu: teacher routes are direct top-level entries for lower click depth. */
const teacherMenu = [
  { path: '/students', label: '学生管理', icon: User },
  { path: '/homework', label: '作业管理', icon: Reading },
  { path: '/materials', label: '课程目录', icon: Collection },
  { path: '/learning-notes', label: '学习笔记', icon: EditPen }
]

/** Flat menu: student course routes are direct top-level entries for lower click depth. */
const studentMenu = [
  { path: '/courses', label: '选课与进度', icon: School },
  { path: '/course-home', label: '学习主页', icon: House },
  { path: '/homework', label: '课程作业', icon: Document },
  { path: '/materials', label: '课程目录', icon: Collection },
  { path: '/learning-notes', label: '学习笔记', icon: EditPen },
  { path: '/student-scores', label: '我的成绩', icon: Trophy }
]

const adminMenu = [
  { path: '/students', label: '学生管理', icon: User },
  { path: '/classes', label: '班级管理', icon: School },
  { path: '/users', label: '用户管理', icon: UserFilled },
  { path: '/subjects', label: '课程管理', icon: Reading },
  {
    type: 'submenu',
    index: 'admin-academic-config',
    label: '学期与配置',
    icon: Setting,
    children: [
      { path: '/semesters', label: '学期管理', icon: Calendar },
      { path: '/settings', label: '系统设置', icon: Setting }
    ]
  },
  {
    type: 'submenu',
    index: 'admin-ops',
    label: '消息与审计',
    icon: Bell,
    children: [
      { path: '/logs', label: '操作日志', icon: Document }
    ]
  }
]

const menuItems = computed(() => {
  if (userStore.isStudent) {
    return studentMenu
  }

  if (userStore.isAdmin) {
    return adminMenu
  }

  if (userStore.isClassTeacher) {
    return classTeacherMenu
  }

  return teacherMenu
})

const roleText = role => ({
  admin: '管理员',
  class_teacher: '班主任',
  teacher: '任课老师',
  student: '学生'
}[role] || '未知角色')

const persistDesktopSidebarState = () => {
  if (typeof window === 'undefined' || isMobile.value) {
    return
  }

  // Desktop UX: only distinguish hidden vs expanded (icon-only rail removed — edge handle is canonical).
  const state = isSidebarHidden.value ? 'hidden' : 'expanded'
  window.localStorage.setItem(desktopSidebarStorageKey, state)
}

const restoreDesktopSidebarState = () => {
  if (typeof window === 'undefined') {
    return
  }

  const state = window.localStorage.getItem(desktopSidebarStorageKey)
  if (state === 'hidden') {
    isSidebarHidden.value = true
    isCollapsed.value = false
    return
  }
  // Migrate legacy "collapsed" rail preference to fully expanded menu (sidebar rail toggle removed).
  isSidebarHidden.value = false
  isCollapsed.value = false
}

const toggleMobileSidebar = () => {
  isCollapsed.value = !isCollapsed.value
}

const toggleSidebarDrawer = () => {
  if (isMobile.value) {
    toggleMobileSidebar()
    return
  }

  isSidebarHidden.value = !isSidebarHidden.value
  if (!isSidebarHidden.value) {
    isCollapsed.value = false
  }
  persistDesktopSidebarState()
}

const syncResponsiveSidebar = () => {
  if (typeof window === 'undefined') {
    return
  }

  const nextIsMobile = window.innerWidth <= mobileBreakpoint
  const changedMode = nextIsMobile !== isMobile.value
  isMobile.value = nextIsMobile
  if (isMobile.value) {
    isSidebarHidden.value = false
    isCollapsed.value = true
    return
  }

  if (changedMode) {
    restoreDesktopSidebarState()
  }
}

const syncTeacherCourses = async force => {
  if (!userStore.canSelectCourse) {
    return
  }

  try {
    await userStore.ensureSelectedCourse(force, {
      preserveEmptySelection: userStore.isStudent || userStore.isClassTeacher
    })
  } catch (error) {
    console.error('加载课程失败', error)
  }
}

const handleWindowFocus = () => {
  syncTeacherCourses(true)
  pollNotificationSync()
}

const handleVisibilityChange = () => {
  if (document.visibilityState === 'visible') {
    syncTeacherCourses(true)
    pollNotificationSync()
  }
}

const handleCourseSwitch = courseId => {
  const course = availableCourses.value.find(item => String(item.id) === String(courseId))
  if (!course) {
    return
  }

  userStore.setSelectedCourse(course, { reason: 'user' })

  if (/^\/homework\/\d+\//.test(route.path)) {
    router.push('/homework')
    return
  }

  if (route.path === '/courses') {
    router.push(userStore.isStudent ? '/course-home' : '/students')
  }
}

const handleCommand = command => {
  if (command === 'recent-posts') {
    router.push('/recent-posts/me')
    return
  }

  if (command === 'notifications') {
    router.push('/notifications')
    return
  }

  if (command === 'personal-settings') {
    router.push('/personal-settings')
    return
  }

  if (command === 'logout') {
    userStore.logout()
    router.push('/login')
  }
}

const goRecentPosts = () => {
  router.push('/recent-posts/me')
  if (isMobile.value) {
    isCollapsed.value = true
  }
}

const goPersonalSettings = () => {
  router.push('/personal-settings')
  if (isMobile.value) {
    isCollapsed.value = true
  }
}

const goNotifications = () => {
  router.push('/notifications')
  if (isMobile.value) {
    isCollapsed.value = true
  }
}

const sidebarLogout = () => {
  userStore.logout()
  router.push('/login')
}

onMounted(async () => {
  restoreDesktopSidebarState()
  syncResponsiveSidebar()
  window.addEventListener('resize', syncResponsiveSidebar)
  window.addEventListener('focus', handleWindowFocus)
  document.addEventListener('visibilitychange', handleVisibilityChange)
  await loadHeaderAvatar()
  await syncTeacherCourses(true)
  await pollNotificationSync()
  stopNotificationPolling = startNotificationPolling(pollNotificationSync, DEFAULT_NOTIFICATION_POLL_INTERVAL_MS)
  unsubscribeNotificationBroadcast = subscribeNotificationBroadcast(() => {
    emitNotificationRefresh()
  })
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', syncResponsiveSidebar)
  window.removeEventListener('focus', handleWindowFocus)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  stopNotificationPolling()
  unsubscribeNotificationBroadcast()
  revokeHeaderAvatarBlob()
})

watch(
  () => userStore.userInfo?.id,
  async () => {
    lastNotificationSyncSignature.value = null
    lastNotificationToastSignature.value = null
    headerLastPollUnread.value = null
    headerLastPollTotal.value = null
    headerUnreadCount.value = 0
    await syncTeacherCourses(true)
    await pollNotificationSync()
    await loadHeaderAvatar()
  }
)

watch(
  () => userStore.userInfo?.avatar_url,
  () => {
    loadHeaderAvatar()
  }
)

watch(
  () => route.fullPath,
  async () => {
    if (isMobile.value) {
      isCollapsed.value = true
    }
    await syncTeacherCourses(true)
    await pollNotificationSync()
  }
)

watch(notificationSyncParams, () => {
  lastNotificationSyncSignature.value = null
  lastNotificationToastSignature.value = null
  headerLastPollUnread.value = null
  headerLastPollTotal.value = null
  pollNotificationSync()
})
</script>

<style scoped>
.layout-container {
  min-height: 100vh;
  background: var(--wa-color-bg);
}

.layout-container > .el-container {
  min-width: 0;
}

.sidebar {
  position: sticky;
  top: 0;
  align-self: flex-start;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--wa-sidebar-bg);
  color: #fff;
  transition: width 0.2s ease, transform 0.2s ease;
}

.sidebar--hidden {
  overflow: hidden;
}

.sidebar-edge-handle {
  position: fixed;
  top: 50%;
  z-index: 1000;
  display: inline-flex;
  width: 22px;
  height: 46px;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-left: none;
  border-radius: 0 var(--wa-radius-xl) var(--wa-radius-xl) 0;
  background: color-mix(in srgb, var(--wa-sidebar-bg-start) 78%, rgba(255, 255, 255, 0.22));
  color: rgba(255, 255, 255, 0.9);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.2);
  cursor: pointer;
  transform: translateY(-50%);
  backdrop-filter: blur(10px);
  transition: left 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease, color 0.2s ease;
}

.sidebar-edge-handle:hover,
.sidebar-edge-handle:focus-visible {
  transform: translateY(-50%) translateX(2px);
  background: color-mix(in srgb, var(--wa-color-primary-500) 62%, rgba(255, 255, 255, 0.2));
  color: #ffffff;
  box-shadow: 0 16px 34px color-mix(in srgb, var(--wa-color-primary-600) 26%, transparent);
  outline: none;
}

.sidebar-edge-handle--hidden {
  border-color: rgba(148, 163, 184, 0.28);
  background: rgba(255, 255, 255, 0.92);
  color: var(--wa-color-primary-600);
}

.sidebar-edge-handle--drawer-open {
  color: #ffffff;
  background: color-mix(in srgb, var(--wa-sidebar-bg-start) 80%, rgba(255, 255, 255, 0.24));
}

.mobile-sidebar-backdrop {
  position: fixed;
  inset: 0;
  z-index: 998;
  background: rgba(15, 23, 42, 0.36);
}

.sidebar-body {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
}

.sidebar-menu--scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}

.sidebar-footer {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0 12px 12px 6px;
  padding: 10px 8px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: var(--wa-radius-xl);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.045) 0%, rgba(255, 255, 255, 0.015) 100%),
    var(--wa-sidebar-footer-bg);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);
}

.sidebar-footer__section-title {
  padding: 0 8px 5px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: rgba(255, 255, 255, 0.56);
  text-transform: uppercase;
}

.sidebar-footer__btn {
  display: flex;
  width: 100%;
  position: relative;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
  margin: 0;
  padding: 9px 8px;
  border: none;
  border-radius: var(--wa-radius-lg);
  background: transparent;
  color: rgba(255, 255, 255, 0.82);
  font-size: 14px;
  cursor: pointer;
  text-align: left;
  transition: background 0.16s ease, color 0.16s ease, transform 0.16s ease;
}

.sidebar-footer__btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
}

.sidebar-footer__btn--active {
  background: color-mix(in srgb, var(--wa-color-primary-500) 26%, rgba(255, 255, 255, 0.1));
  color: #fff;
}

.sidebar-footer__btn--danger:hover {
  background: rgba(248, 113, 113, 0.22);
  color: #fecaca;
}

.sidebar-body:has(.el-menu--collapse) .sidebar-footer__btn {
  justify-content: center;
  padding-left: 8px;
  padding-right: 8px;
}

.sidebar-body:has(.el-menu--collapse) .sidebar-footer {
  margin-left: 8px;
  margin-right: 8px;
  padding-left: 6px;
  padding-right: 6px;
}

.sidebar-footer__label {
  white-space: nowrap;
}

.sidebar-footer__badge {
  margin-left: auto;
  min-width: 20px;
  border-radius: 999px;
  background: #ef4444;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  line-height: 18px;
  padding: 0 6px;
  text-align: center;
}

.logo {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.logo-main {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo-icon {
  display: flex;
  width: 40px;
  height: 40px;
  align-items: center;
  justify-content: center;
  border-radius: var(--wa-radius-lg);
  background: color-mix(in srgb, var(--wa-color-primary-500) 22%, transparent);
  color: var(--wa-color-primary-300);
}

.logo-mark {
  width: 34px;
  height: 34px;
  display: block;
  border-radius: 10px;
}

.logo-texts h2 {
  margin: 0;
  font-size: 18px;
  color: #fff;
}

.logo-texts p {
  margin: 4px 0 0;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.65);
}

.sidebar-menu {
  border-right: none;
  background: transparent;
  padding: 12px 8px;
}

.sidebar-menu :deep(.el-sub-menu),
.sidebar-menu :deep(.el-menu--inline),
.sidebar-menu :deep(.el-sub-menu .el-menu) {
  background: transparent;
}

.sidebar-menu :deep(.el-sub-menu .el-menu) {
  padding: 0;
}

.sidebar-menu :deep(.el-sub-menu__title),
.sidebar-menu :deep(.el-sub-menu .el-menu-item) {
  background-color: transparent;
}

.sidebar-menu :deep(.el-menu-item) {
  margin: 6px 0;
  border-radius: var(--wa-radius-lg);
  color: rgba(255, 255, 255, 0.82);
  min-height: 48px;
  transform-origin: left center;
  transition: transform 0.16s ease, background 0.16s ease, color 0.16s ease;
}

.sidebar-menu :deep(.el-menu-item .el-icon),
.sidebar-menu :deep(.el-sub-menu__title .el-icon) {
  width: 22px;
  height: 22px;
  margin-right: 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.82);
}

.sidebar-menu :deep(.el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
  transform: translateX(2px) scale(1.025);
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  background: var(--wa-sidebar-active-bg);
  color: #fff;
  box-shadow: 0 10px 22px color-mix(in srgb, var(--wa-color-primary-600) 22%, transparent);
}

.sidebar-menu :deep(.el-menu-item.is-active .el-icon),
.sidebar-menu :deep(.el-sub-menu__title:hover .el-icon),
.sidebar-menu :deep(.el-menu-item:hover .el-icon) {
  background: rgba(255, 255, 255, 0.16);
  color: #fff;
}

.sidebar-menu :deep(.el-sub-menu .el-menu-item.is-active) {
  background: var(--wa-sidebar-active-bg);
}

.sidebar-menu :deep(.el-sub-menu__title) {
  margin: 6px 0;
  border-radius: var(--wa-radius-lg);
  color: rgba(255, 255, 255, 0.82);
  min-height: 48px;
  transform-origin: left center;
  transition: transform 0.16s ease, background 0.16s ease, color 0.16s ease;
}

.sidebar-menu :deep(.el-sub-menu__title:hover) {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
  transform: translateX(2px) scale(1.025);
}

.sidebar-menu :deep(.el-sub-menu .el-menu-item) {
  margin: 4px 0;
  padding-left: 48px !important;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--wa-border-subtle);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(255, 255, 255, 0.86)),
    color-mix(in srgb, var(--wa-color-primary-50) 18%, #fff);
  backdrop-filter: blur(14px);
  box-shadow: 0 8px 22px color-mix(in srgb, var(--wa-color-text) 5%, transparent);
}

.header-left {
  display: flex;
  flex: 1 1 auto;
  align-items: center;
  gap: 18px;
  min-width: 0;
}

.context-chip {
  display: flex;
  flex: 0 1 320px;
  min-width: 0;
  align-items: center;
  gap: 10px;
  max-width: 100%;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--wa-color-primary-200) 64%, transparent);
  background: color-mix(in srgb, var(--wa-color-primary-50) 86%, #fff);
  padding: 8px 14px;
  color: var(--wa-color-primary-700);
  transition: transform 0.16s ease, box-shadow 0.16s ease;
}

.context-chip:hover {
  transform: scale(1.02);
  box-shadow: 0 8px 20px color-mix(in srgb, var(--wa-color-primary-600) 12%, transparent);
}

.context-chip--class {
  background: var(--wa-color-accent-50);
  color: var(--wa-color-accent-700);
}

.context-chip--course {
  padding-left: 18px;
  gap: 12px;
}

.context-chip__label {
  flex: 0 0 auto;
  color: var(--wa-color-text-muted);
}

.context-chip__meta {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
}

.context-chip__meta strong,
.context-chip__meta span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.context-chip__meta span {
  font-size: 12px;
  color: var(--wa-color-text-muted);
}

.context-chip :deep(.el-tag) {
  flex: 0 0 auto;
}

.header-right {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.course-option {
  display: flex;
  min-width: 200px;
  flex-direction: column;
  gap: 4px;
}

.course-option span {
  font-size: 12px;
  color: var(--wa-color-text-muted);
}

.course-dropdown-menu :deep(.is-current-course) {
  background: var(--wa-color-primary-50);
}

.header-user-badge :deep(.el-badge__content) {
  top: 4px;
  right: 6px;
  border: 2px solid var(--wa-color-bg, #fff);
}

.user-box {
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  border-radius: var(--wa-radius-pill);
  padding: 4px 8px 4px 4px;
  transition: transform 0.16s ease, background 0.16s ease, box-shadow 0.16s ease;
}

.user-box:hover {
  background: var(--wa-color-primary-50);
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.08);
  transform: scale(1.025);
}

.user-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.user-meta strong {
  color: var(--wa-color-text);
}

.user-meta span {
  font-size: 12px;
  color: var(--wa-color-text-muted);
}

.user-dropdown-card {
  width: 300px;
  cursor: default;
}

.user-dropdown-card.is-disabled {
  opacity: 1;
}

.user-dropdown-profile {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 8px 4px 12px;
}

.user-dropdown-id {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.user-dropdown-id strong,
.user-dropdown-id span,
.user-dropdown-id small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-dropdown-id strong {
  color: var(--wa-color-text);
}

.user-dropdown-id span,
.user-dropdown-id small {
  color: var(--wa-color-text-muted);
}

.user-dropdown-token {
  border: 1px solid var(--wa-border-subtle);
  border-radius: var(--wa-radius-md);
  background: color-mix(in srgb, var(--wa-color-primary-50) 70%, white);
  padding: 10px;
}

.user-dropdown-token__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  color: var(--wa-color-text-soft);
}

.user-dropdown-token__row strong {
  color: var(--wa-color-primary-700);
}

.user-dropdown-token p {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--wa-color-text-muted);
}

.main-content {
  min-width: 0;
  padding: 0;
}

.footer {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: var(--wa-color-text-muted);
}

@media (max-width: 768px) {
  .sidebar.sidebar--mobile-collapsed {
    flex: 0 0 0 !important;
    width: 0 !important;
    min-width: 0 !important;
    max-width: 0 !important;
    padding: 0 !important;
    margin: 0 !important;
    border: none !important;
    overflow: hidden !important;
    pointer-events: none;
  }

  .sidebar.sidebar--mobile-collapsed .sidebar-body,
  .sidebar.sidebar--mobile-collapsed .logo {
    visibility: hidden;
  }

  .layout-container {
    position: relative;
  }

  .sidebar {
    position: fixed;
    inset: 0 auto 0 0;
    z-index: 999;
    overflow: hidden;
    box-shadow: 18px 0 40px rgba(15, 23, 42, 0.2);
  }

  .sidebar[style*="0px"] {
    transform: translateX(-100%);
  }

  .sidebar-edge-handle {
    width: 26px;
    height: 52px;
  }

  .layout-container--mobile-sidebar-open {
    overflow: hidden;
  }

  .logo {
    padding: 14px 12px;
  }

  .header {
    height: auto;
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
    padding: 12px;
  }

  .header-left {
    width: 100%;
    flex-wrap: wrap;
    align-items: flex-start;
    gap: 10px;
  }

  .mobile-menu-btn {
    flex: 0 0 auto;
  }

  .header-left :deep(.el-breadcrumb) {
    min-width: 0;
    max-width: calc(100% - 44px);
  }

  .context-chip {
    width: 100%;
    border-radius: 18px;
    align-items: flex-start;
  }

  .header-right {
    width: 100%;
    justify-content: space-between;
    flex-wrap: wrap;
  }

  .user-meta {
    display: none;
  }
}
</style>
