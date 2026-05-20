import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import api, { http } from '@/api'
import { normalizeSystemSettings } from '@/utils/branding'

const cachedSystemSettings = normalizeSystemSettings(
  JSON.parse(localStorage.getItem('system_settings') || 'null')
)

if (cachedSystemSettings) {
  localStorage.setItem('system_settings', JSON.stringify(cachedSystemSettings))
}

const cachedSelectedCourse = JSON.parse(localStorage.getItem('selected_course') || 'null')

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('token') || '')
  const userInfo = ref(JSON.parse(localStorage.getItem('user') || 'null'))
  const systemSettings = ref(cachedSystemSettings)
  const appearanceState = ref(null)
  const selectedCourse = ref(cachedSelectedCourse)
  const selectedCourseSelectionEvent = ref({
    sequence: 0,
    reason: 'init',
    courseId: cachedSelectedCourse?.id ?? null
  })
  const teachingCourses = ref([])
  const teachingCoursesLoaded = ref(false)

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => userInfo.value?.role === 'admin')
  const isClassTeacher = computed(() => userInfo.value?.role === 'class_teacher')
  const isTeacher = computed(() => userInfo.value?.role === 'teacher')
  const isStudent = computed(() => userInfo.value?.role === 'student')
  const classId = computed(() => userInfo.value?.class_id)
  const canManageTeaching = computed(() => ['admin', 'class_teacher', 'teacher'].includes(userInfo.value?.role))
  const canSelectCourse = computed(() => ['class_teacher', 'teacher', 'student'].includes(userInfo.value?.role))

  function mergeCourseSnapshot(preferredCourse, cachedCourse) {
    if (!preferredCourse && !cachedCourse) {
      return null
    }
    if (!preferredCourse) {
      return cachedCourse
    }
    if (!cachedCourse) {
      return preferredCourse
    }
    // Keep the freshest route/page snapshot while retaining any stable fields
    // from the cached teaching-courses entry.
    return {
      ...cachedCourse,
      ...preferredCourse
    }
  }

  function setSelectedCourse(course, options = {}) {
    const { reason = 'system', emitEvent = reason === 'user' } = options
    const matchedCourse = course
      ? teachingCourses.value.find(item => String(item.id) === String(course.id)) || null
      : null
    const normalizedCourse = mergeCourseSnapshot(course, matchedCourse)

    if (normalizedCourse) {
      const nextCourses = [...teachingCourses.value]
      const index = nextCourses.findIndex(item => String(item.id) === String(normalizedCourse.id))
      if (index >= 0) {
        nextCourses[index] = mergeCourseSnapshot(normalizedCourse, nextCourses[index])
        teachingCourses.value = nextCourses
      }
    }

    selectedCourse.value = normalizedCourse
    if (normalizedCourse) {
      localStorage.setItem('selected_course', JSON.stringify(normalizedCourse))
    } else {
      localStorage.removeItem('selected_course')
    }

    if (emitEvent) {
      selectedCourseSelectionEvent.value = {
        sequence: selectedCourseSelectionEvent.value.sequence + 1,
        reason,
        courseId: normalizedCourse?.id ?? null
      }
    }
  }

  function clearSelectedCourse() {
    setSelectedCourse(null)
  }

  function rankTeachingCourses(courses) {
    return [...courses].sort((left, right) => {
      const leftActive = left.status !== 'completed'
      const rightActive = right.status !== 'completed'

      if (leftActive !== rightActive) {
        return leftActive ? -1 : 1
      }

      const semesterCompare = `${right.semester || ''}`.localeCompare(`${left.semester || ''}`, 'zh-CN', {
        numeric: true,
        sensitivity: 'base'
      })

      if (semesterCompare !== 0) {
        return semesterCompare
      }

      return Number(right.id || 0) - Number(left.id || 0)
    })
  }

  function resolvePreferredCourse(courses, options = {}) {
    const { preserveEmptySelection = false } = options

    if (!courses.length) {
      return null
    }

    const cachedCourse = selectedCourse.value
      ? courses.find(item => String(item.id) === String(selectedCourse.value.id))
      : null

    if (cachedCourse) {
      return cachedCourse
    }

    if (preserveEmptySelection) {
      return null
    }

    return courses[0]
  }

  async function fetchTeachingCourses(force = false) {
    if (!canSelectCourse.value || isAdmin.value) {
      teachingCourses.value = []
      teachingCoursesLoaded.value = true
      return []
    }

    if (teachingCoursesLoaded.value && !force) {
      return teachingCourses.value
    }

    const data = await api.courses.list()
    teachingCourses.value = rankTeachingCourses(Array.isArray(data) ? data : [])
    teachingCoursesLoaded.value = true

    return teachingCourses.value
  }

  async function ensureSelectedCourse(force = false, options = {}) {
    const { preserveEmptySelection = false } = options
    const courses = await fetchTeachingCourses(force)
    const preferredCourse = resolvePreferredCourse(courses, { preserveEmptySelection })

    if (preferredCourse) {
      setSelectedCourse(preferredCourse)
    } else {
      if (selectedCourse.value || !preserveEmptySelection) {
        clearSelectedCourse()
      }
    }

    return preferredCourse
  }

  async function login(username, password) {
    const formData = new FormData()
    formData.append('username', username)
    formData.append('password', password)

    try {
      const data = await api.auth.login(formData)
      token.value = data.access_token
      localStorage.setItem('token', data.access_token)

      const userData = await api.auth.getCurrentUser()
      userInfo.value = userData
      localStorage.setItem('user', JSON.stringify(userData))

      if (userData?.role === 'student') {
        clearSelectedCourse()
      }

      await fetchSystemSettings()
      await fetchAppearanceState()

      return userData
    } catch (error) {
      token.value = ''
      userInfo.value = null
      appearanceState.value = null
      selectedCourse.value = null
      teachingCourses.value = []
      teachingCoursesLoaded.value = false
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      localStorage.removeItem('selected_course')
      throw error
    }
  }

  async function refreshUserInfo() {
    const userData = await api.auth.getCurrentUser()
    userInfo.value = userData
    localStorage.setItem('user', JSON.stringify(userData))
    return userData
  }

  async function fetchSystemSettings() {
    try {
      const data = await http.get('/settings/public')
      const normalizedSettings = normalizeSystemSettings(data)
      systemSettings.value = normalizedSettings
      localStorage.setItem('system_settings', JSON.stringify(normalizedSettings))
      document.title = normalizedSettings?.system_name || 'CourseEval Admin'
    } catch (error) {
      console.error('Failed to fetch system settings', error)
    }
  }

  async function fetchAppearanceState() {
    if (!token.value) {
      appearanceState.value = null
      return null
    }

    try {
      const data = await api.appearance.getMine()
      appearanceState.value = data
      return data
    } catch (error) {
      console.error('Failed to fetch appearance state', error)
      appearanceState.value = null
      return null
    }
  }

  function setAppearanceState(nextState) {
    appearanceState.value = nextState || null
  }

  function logout() {
    token.value = ''
    userInfo.value = null
    systemSettings.value = null
    appearanceState.value = null
    selectedCourse.value = null
    teachingCourses.value = []
    teachingCoursesLoaded.value = false
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    localStorage.removeItem('system_settings')
    localStorage.removeItem('selected_course')
  }

  return {
    token,
    userInfo,
    systemSettings,
    appearanceState,
    selectedCourse,
    selectedCourseSelectionEvent,
    teachingCourses,
    teachingCoursesLoaded,
    isLoggedIn,
    isAdmin,
    isClassTeacher,
    isTeacher,
    isStudent,
    classId,
    canManageTeaching,
    canSelectCourse,
    login,
    logout,
    fetchSystemSettings,
    fetchAppearanceState,
    setAppearanceState,
    refreshUserInfo,
    setSelectedCourse,
    clearSelectedCourse,
    fetchTeachingCourses,
    ensureSelectedCourse
  }
})
