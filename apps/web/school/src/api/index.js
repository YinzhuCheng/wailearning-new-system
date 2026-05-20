import axios from 'axios'
import { ElMessage } from 'element-plus'

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api'

/** After this many ms without first byte, show a non-blocking busy hint (configurable per product). */
const SLOW_RESPONSE_THRESHOLD_MS = 3000
const SLOW_BUSY_MESSAGE = '系统正忙，请等待。'

const http = axios.create({
  baseURL: apiBaseUrl,
  timeout: 10000
})
const fileTransferRequestConfig = {
  timeout: 0
}

const clearSlowBusyIfAny = config => {
  if (!config) {
    return
  }
  if (config._slowBusyTimer != null) {
    window.clearTimeout(config._slowBusyTimer)
    config._slowBusyTimer = null
  }
  if (config._slowBusyMessage) {
    try {
      config._slowBusyMessage.close()
    } catch {
      /* ignore */
    }
    config._slowBusyMessage = null
  }
}

const attachSlowBusyWatcher = config => {
  clearSlowBusyIfAny(config)
  if (config.skipSlowBusyMessage) {
    return config
  }
  const t = config.timeout
  if (t === 0 || t === false) {
    return config
  }
  config._slowBusyTimer = window.setTimeout(() => {
    config._slowBusyTimer = null
    config._slowBusyMessage = ElMessage({
      message: SLOW_BUSY_MESSAGE,
      type: 'warning',
      duration: 0,
      showClose: true
    })
  }, SLOW_RESPONSE_THRESHOLD_MS)
  return config
}

const attachAuthToken = config => {
  const token = localStorage.getItem('token') || ''
  config._authTokenAtDispatch = token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
}

const clearCurrentSessionForUnauthorized = config => {
  const requestToken = config?._authTokenAtDispatch || ''
  const currentToken = localStorage.getItem('token') || ''
  if (!requestToken || requestToken !== currentToken) {
    return false
  }
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  localStorage.removeItem('selected_course')
  window.location.href = '/login'
  return true
}

/** FastAPI/Pydantic 422: { detail: [{ loc, msg, type }, ...] } — must stringify for ElMessage. */
const formatValidationDetail = detail => {
  if (!Array.isArray(detail) || !detail.length) {
    return null
  }
  const parts = detail
    .map(item => {
      if (typeof item === 'string') {
        return item
      }
      if (item && typeof item === 'object') {
        if (typeof item.msg === 'string') {
          return item.msg
        }
        if (typeof item.message === 'string') {
          return item.message
        }
      }
      return null
    })
    .filter(Boolean)
  return parts.length ? parts.join('；') : null
}

const extractErrorMessage = async error => {
  const data = error?.response?.data

  if (data instanceof Blob) {
    try {
      const text = await data.text()
      if (text) {
        try {
          const parsed = JSON.parse(text)
          const d = parsed?.detail
          if (Array.isArray(d)) {
            return formatValidationDetail(d) || parsed?.message || text
          }
          if (typeof d === 'string') {
            return d
          }
          return parsed?.message || text
        } catch {
          return text
        }
      }
    } catch {
      return 'Request failed'
    }
  }

  if (typeof data === 'string' && data.trim()) {
    return data
  }

  const detail = data?.detail
  if (Array.isArray(detail)) {
    return formatValidationDetail(detail) || data?.message || 'Request failed'
  }
  if (detail != null && typeof detail === 'object') {
    if (typeof detail.msg === 'string') {
      return detail.msg
    }
    if (typeof detail.message === 'string') {
      return detail.message
    }
  }
  if (typeof detail === 'string') {
    return detail
  }

  return data?.message || 'Request failed'
}

http.interceptors.request.use(
  config => {
    attachAuthToken(config)
    attachSlowBusyWatcher(config)
    return config
  },
  error => Promise.reject(error)
)

http.interceptors.response.use(
  response => {
    clearSlowBusyIfAny(response.config)
    return response.config?.returnFullResponse ? response : response.data
  },
  async error => {
    clearSlowBusyIfAny(error.config)
    if (error.response) {
      const message = await extractErrorMessage(error)
      if (!error.config?.skipGlobalErrorMessage) {
        ElMessage.error(message)
      }
      if (error.response.status === 401) {
        clearCurrentSessionForUnauthorized(error.config)
      }
    } else if (error.code === 'ECONNABORTED') {
      ElMessage.error('Request timed out')
    } else {
      ElMessage.error('Network error')
    }
    return Promise.reject(error)
  }
)

/** Same as `http` but no global ElMessage on error (caller handles toasts) and unbounded timeout for long LLM calls. */
const httpQuiet = axios.create({
  baseURL: apiBaseUrl,
  timeout: 0
})
httpQuiet.interceptors.request.use(
  config => {
    attachAuthToken(config)
    attachSlowBusyWatcher(config)
    return config
  },
  error => Promise.reject(error)
)
httpQuiet.interceptors.response.use(
  response => {
    clearSlowBusyIfAny(response.config)
    return response.config?.returnFullResponse ? response : response.data
  },
  error => {
    clearSlowBusyIfAny(error.config)
    if (error.response?.status === 401) {
      clearCurrentSessionForUnauthorized(error.config)
    }
    return Promise.reject(error)
  }
)

/** Unauthenticated API calls (login page); no Bearer header, same base URL. */
const httpPublic = axios.create({
  baseURL: apiBaseUrl,
  timeout: 10000
})
httpPublic.interceptors.request.use(
  config => {
    attachSlowBusyWatcher(config)
    return config
  },
  error => Promise.reject(error)
)
httpPublic.interceptors.response.use(
  response => {
    clearSlowBusyIfAny(response.config)
    return response.config?.returnFullResponse ? response : response.data
  },
  async error => {
    clearSlowBusyIfAny(error.config)
    if (error.response) {
      const message = await extractErrorMessage(error)
      ElMessage.error(message)
    } else if (error.code === 'ECONNABORTED') {
      ElMessage.error('Request timed out')
    } else {
      ElMessage.error('Network error')
    }
    return Promise.reject(error)
  }
)

export { http, httpQuiet, httpPublic, apiBaseUrl }

/** Course list/sync can exceed default timeout on large SQLite E2E databases. */
const subjectsHeavyTimeout = 60000
const rosterHeavyTimeout = 60000

const subjectsApi = {
  list: params => http.get('/subjects', { params, timeout: subjectsHeavyTimeout }),
    electiveCatalog: () => http.get('/subjects/elective-catalog', { timeout: subjectsHeavyTimeout }),
    courseCatalog: () => http.get('/subjects/course-catalog', { timeout: subjectsHeavyTimeout }),
  studentSelfEnroll: subjectId => http.post(`/subjects/${subjectId}/student-self-enroll`),
  studentSelfDrop: subjectId => http.post(`/subjects/${subjectId}/student-self-drop`),
  get: id => http.get(`/subjects/${id}`),
  create: data => http.post('/subjects', data, { timeout: subjectsHeavyTimeout }),
    update: (id, data) => http.put(`/subjects/${id}`, data, { timeout: subjectsHeavyTimeout }),
    delete: id => http.delete(`/subjects/${id}`, { timeout: subjectsHeavyTimeout }),
    uploadCoverImage: (subjectId, file) => {
      const formData = new FormData()
      formData.append('file', file)
      return http.post(`/subjects/${subjectId}/cover-image`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        ...fileTransferRequestConfig
      })
    },
  getStudents: id => http.get(`/subjects/${id}/students`, { timeout: subjectsHeavyTimeout }),
  syncEnrollments: id => http.post(`/subjects/${id}/sync-enrollments`, {}, { timeout: subjectsHeavyTimeout }),
  rosterEnroll: (subjectId, data) => http.post(`/subjects/${subjectId}/roster-enroll`, data, { timeout: subjectsHeavyTimeout }),
  removeStudent: (subjectId, studentId) =>
    http.delete(`/subjects/${subjectId}/students/${studentId}`, { timeout: subjectsHeavyTimeout }),
  updateEnrollmentType: (subjectId, studentId, data) => http.put(`/subjects/${subjectId}/students/${studentId}/enrollment-type`, data)
}

const api = {
  auth: {
    login: data => http.post('/auth/login', data),
    register: data => http.post('/auth/register', data),
    getCurrentUser: () => http.get('/auth/me'),
    updateProfile: data => http.patch('/auth/me', data),
    uploadAvatar: file => {
      const formData = new FormData()
      formData.append('file', file)
      return http.post('/auth/me/avatar', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        ...fileTransferRequestConfig
      })
    },
    deleteAvatar: () => http.delete('/auth/me/avatar'),
    changePassword: data => http.post('/auth/change-password', data),
    forgotPassword: data => httpPublic.post('/auth/forgot-password', data)
  },
  users: {
    list: params => http.get('/users', { params, timeout: rosterHeavyTimeout }),
    batchSetClass: data => http.post('/users/batch-set-class', data),
    upsertStudentRosterFromUsers: data => http.post('/users/student-roster/from-users', data),
    get: id => http.get(`/users/${id}`),
    create: data => http.post('/users', data, { timeout: rosterHeavyTimeout }),
    update: (id, data) => http.put(`/users/${id}`, data),
    delete: id => http.delete(`/users/${id}`),
    resetPassword: (id, data) => http.post(`/users/${id}/reset-password`, data)
  },
  classes: {
    list: () => http.get('/classes'),
    get: id => http.get(`/classes/${id}`),
    create: data => http.post('/classes', data),
    update: (id, data) => http.put(`/classes/${id}`, data),
    delete: id => http.delete(`/classes/${id}`)
  },
  students: {
    list: params => http.get('/students', { params, timeout: rosterHeavyTimeout }),
    get: id => http.get(`/students/${id}`),
    create: data => http.post('/students', data),
    update: (id, data) => http.put(`/students/${id}`, data),
    delete: id => http.delete(`/students/${id}`),
    batchCreate: data =>
      http.post('/students/batch', JSON.stringify(data), {
        headers: { 'Content-Type': 'application/json' }
      })
  },
  subjects: subjectsApi,
  courses: subjectsApi,
  scores: {
    list: params => http.get('/scores', { params }),
    get: id => http.get(`/scores/${id}`),
    create: data => http.post('/scores', data),
    batchCreate: data =>
      http.post('/scores/batch', JSON.stringify(data), {
        headers: { 'Content-Type': 'application/json' }
      }),
    update: (id, data) => http.put(`/scores/${id}`, data),
    delete: id => http.delete(`/scores/${id}`),
    getStudentScores: (studentId, params) => http.get(`/scores/student/${studentId}`, { params }),
    getWeights: subjectId => http.get(`/scores/weights/${subjectId}`),
    updateWeights: (subjectId, data) => http.put(`/scores/weights/${subjectId}`, data),
    getGradeScheme: subjectId => http.get(`/scores/grade-scheme/${subjectId}`),
    updateGradeScheme: (subjectId, data) => http.put(`/scores/grade-scheme/${subjectId}`, data),
    getMyComposition: params => http.get('/scores/composition/me', { params }),
    getStudentComposition: (studentId, params) =>
      http.get(`/scores/composition/${studentId}`, { params }),
    listClassComposition: params => http.get('/scores/composition/class', { params }),
    createAppeal: (subjectId, data) => http.post(`/scores/appeals?subject_id=${subjectId}`, data),
    listAppeals: params => http.get('/scores/appeals', { params }),
    updateAppeal: (appealId, data) => http.put(`/scores/appeals/${appealId}`, data)
  },
  semesters: {
    list: () => http.get('/semesters'),
    create: data => http.post('/semesters', data),
    update: (id, data) => http.put(`/semesters/${id}`, data),
    delete: id => http.delete(`/semesters/${id}`)
  },
  attendance: {
    list: params => http.get('/attendance', { params }),
    create: data => http.post('/attendance', data),
    update: (id, data) => http.put(`/attendance/${id}`, data),
    delete: id => http.delete(`/attendance/${id}`),
    getClassStats: (classId, params) => http.get(`/attendance/statistics/class/${classId}`, { params }),
    getStudentStats: (studentId, params) => http.get(`/attendance/statistics/student/${studentId}`, { params }),
    batchCreate: data =>
      http.post('/attendance/batch', JSON.stringify(data), {
        headers: { 'Content-Type': 'application/json' }
      }),
    batchCreateForClass: data =>
      http.post('/attendance/class-batch', JSON.stringify(data), {
        headers: { 'Content-Type': 'application/json' }
      })
  },
  dashboard: {
    getStats: params => http.get('/dashboard/stats', { params }),
    getClassRankings: params => http.get('/dashboard/rankings/classes', { params }),
    getStudentRankings: params => http.get('/dashboard/rankings/students', { params }),
    getSubjectRankings: (subjectId, params) => http.get(`/dashboard/rankings/subjects/${subjectId}`, { params }),
    getTrends: params => http.get('/dashboard/analysis/trends', { params }),
    getSubjectAnalysis: params => http.get('/dashboard/analysis/subjects', { params })
  },
  homework: {
    list: params => http.get('/homeworks', { params }),
    get: id => http.get(`/homeworks/${id}`),
    create: data => http.post('/homeworks', data),
    update: (id, data) => http.put(`/homeworks/${id}`, data),
    delete: id => http.delete(`/homeworks/${id}`),
    batchLateSubmission: data => http.post('/homeworks/batch-late-submission', data),
    batchRegrade: (homeworkId, data) =>
      http.post(`/homeworks/${homeworkId}/submissions/batch-regrade`, data),
    getMySubmission: id => http.get(`/homeworks/${id}/submission/me`),
    getMySubmissionHistory: id => http.get(`/homeworks/${id}/submission/me/history`),
    submit: (id, data) => http.post(`/homeworks/${id}/submission`, data),
    getSubmissions: (id, params) => http.get(`/homeworks/${id}/submissions`, { params }),
    /** Teacher-only status row for one submission (deep-link review page). */
    getSubmissionStatusRow: (homeworkId, submissionId) =>
      http.get(`/homeworks/${homeworkId}/submissions/${submissionId}/status`),
    listCourseStudents: subjectId => http.get(`/homeworks/courses/${subjectId}/students`),
    listStudentHomeworks: (subjectId, studentId, params) =>
      http.get(`/homeworks/courses/${subjectId}/students/${studentId}/homeworks`, { params }),
    submitAppeal: (homeworkId, submissionId, data) =>
      http.post(`/homeworks/${homeworkId}/submissions/${submissionId}/appeal`, data),
    acknowledgeAppeal: (homeworkId, submissionId) =>
      http.post(`/homeworks/${homeworkId}/submissions/${submissionId}/appeal/acknowledge`),
    respondAppeal: (homeworkId, submissionId, data) =>
      http.put(`/homeworks/${homeworkId}/submissions/${submissionId}/appeal`, data),
    getSubmissionHistory: (homeworkId, submissionId) =>
      http.get(`/homeworks/${homeworkId}/submissions/${submissionId}/history`),
    reviewSubmission: (homeworkId, submissionId, data) =>
      http.put(`/homeworks/${homeworkId}/submissions/${submissionId}/review`, data),
    regradeSubmission: (homeworkId, submissionId, data = {}) =>
      http.post(`/homeworks/${homeworkId}/submissions/${submissionId}/regrade`, data),
    downloadSubmissions: (id, data) =>
      http.post(`/homeworks/${id}/submissions/download`, data, {
        responseType: 'blob',
        returnFullResponse: true,
        ...fileTransferRequestConfig
      })
  },
  discussions: {
    list: params => http.get('/discussions', { params }),
    searchTargets: params => http.get('/discussions/link-targets', { params }),
    locateEntry: (id, params) => http.get(`/discussions/entries/${id}/locator`, { params }),
    create: data => http.post('/discussions', data),
    delete: id => http.delete(`/discussions/${id}`),
    /** @param {AbortSignal} [signal] */
    listSignal: (params, signal) => http.get('/discussions', { params, signal })
  },
  recentPosts: {
    mine: params => http.get('/recent-posts/me', { params }),
    mineGrouped: params => http.get('/recent-posts/me/grouped', { params }),
    user: (userId, params) => http.get(`/recent-posts/users/${userId}`, { params }),
    userGrouped: (userId, params) => http.get(`/recent-posts/users/${userId}/grouped`, { params })
  },
  llmSettings: {
    listPresets: () => http.get('/llm-settings/presets'),
    createPreset: data => http.post('/llm-settings/presets', data),
    updatePreset: (id, data) => http.put(`/llm-settings/presets/${id}`, data),
    /** multipart with field `image` (File); do not set Content-Type manually. */
    validatePreset: (id, imageFile) => {
      const form = new FormData()
      form.append('image', imageFile)
      return httpQuiet.post(`/llm-settings/presets/${id}/validate`, form)
    },
    getCourseConfig: subjectId => http.get(`/llm-settings/courses/${subjectId}`),
    updateCourseConfig: (subjectId, data) => http.put(`/llm-settings/courses/${subjectId}`, data),
    getStudentQuota: subjectId => http.get(`/llm-settings/courses/student-quota/${subjectId}`),
    getStudentQuotasSummary: () => http.get('/llm-settings/courses/student-quotas'),
    getGlobalQuotaPolicy: () => http.get('/llm-settings/admin/quota-policy'),
    updateGlobalQuotaPolicy: data => http.put('/llm-settings/admin/quota-policy', data),
    bulkQuotaOverrides: data => http.post('/llm-settings/admin/quota-overrides/bulk', data),
    setStudentQuotaOverride: (studentId, data) => http.put(`/llm-settings/admin/students/${studentId}/quota-override`, data)
  },
  appearance: {
    listPresets: () => http.get('/appearance/presets'),
    getMine: () => http.get('/appearance/me'),
    createStyle: data => http.post('/appearance/me/styles', data),
    updateStyle: (id, data) => http.put(`/appearance/me/styles/${id}`, data),
    selectStyle: id => http.post(`/appearance/me/styles/${id}/select`),
    useSystem: () => http.post('/appearance/me/use-system'),
    deleteStyle: id => http.delete(`/appearance/me/styles/${id}`)
  },
  notifications: {
    syncStatus: params => http.get('/notifications/sync-status', { params }),
    list: params => http.get('/notifications', { params }),
    get: id => http.get(`/notifications/${id}`),
    create: data => http.post('/notifications', data),
    update: (id, data) => http.put(`/notifications/${id}`, data),
    delete: id => http.delete(`/notifications/${id}`),
    markRead: id => http.post(`/notifications/${id}/read`),
    markAllRead: params => http.post('/notifications/mark-all-read', null, { params })
  },
  materials: {
    list: params => http.get('/materials', { params }),
    get: id => http.get(`/materials/${id}`),
    create: data => http.post('/materials', data),
    update: (id, data) => http.put(`/materials/${id}`, data),
    delete: id => http.delete(`/materials/${id}`)
  },
  materialChapters: {
    tree: params => http.get('/material-chapters/tree', { params }),
    create: (subjectId, data) => http.post(`/material-chapters?subject_id=${subjectId}`, data),
    update: (chapterId, data) => http.put(`/material-chapters/${chapterId}`, data),
    delete: (chapterId, subjectId) => http.delete(`/material-chapters/${chapterId}?subject_id=${subjectId}`),
    reorderChapters: (subjectId, data) => http.post(`/material-chapters/reorder?subject_id=${subjectId}`, data),
    reorderSections: (subjectId, data) =>
      http.post(`/material-chapters/sections/reorder?subject_id=${subjectId}`, data),
    addPlacement: (materialId, subjectId, data) =>
      http.post(`/material-chapters/materials/${materialId}/placements?subject_id=${subjectId}`, data),
    removePlacement: (sectionId, subjectId) =>
      http.delete(`/material-chapters/placements/${sectionId}?subject_id=${subjectId}`),
    addHomeworkLink: (subjectId, data) =>
      http.post(`/material-chapters/homework-links?subject_id=${subjectId}`, data),
    removeHomeworkLink: (linkId, subjectId) =>
      http.delete(`/material-chapters/homework-links/${linkId}?subject_id=${subjectId}`)
  },
  learningNotes: {
    list: params => http.get('/learning-notes', { params }),
    get: id => http.get(`/learning-notes/${id}`),
    create: data => http.post('/learning-notes', data),
    update: (id, data) => http.put(`/learning-notes/${id}`, data),
    delete: id => http.delete(`/learning-notes/${id}`),
    createChapter: (noteId, data) => http.post(`/learning-notes/${noteId}/chapters`, data),
    updateChapter: (noteId, chapterId, data) => http.put(`/learning-notes/${noteId}/chapters/${chapterId}`, data),
    deleteChapter: (noteId, chapterId) => http.delete(`/learning-notes/${noteId}/chapters/${chapterId}`),
    createResource: (noteId, data) => http.post(`/learning-notes/${noteId}/resources`, data),
    updateResource: (noteId, resourceId, data) => http.put(`/learning-notes/${noteId}/resources/${resourceId}`, data),
    deleteResource: (noteId, resourceId) => http.delete(`/learning-notes/${noteId}/resources/${resourceId}`),
    discussion: (noteId, params) => http.get(`/learning-notes/${noteId}/discussion`, { params }),
    locateDiscussionEntry: (id, params) => http.get(`/learning-notes/discussion-entries/${id}/locator`, { params }),
    createDiscussion: (noteId, data) => http.post(`/learning-notes/${noteId}/discussion`, data)
  },
  files: {
    upload: file => {
      const formData = new FormData()
      formData.append('file', file)
      return http
        .post('/files/upload', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
          ...fileTransferRequestConfig,
          skipGlobalErrorMessage: true
        })
        .catch(async err => {
          const message = await extractErrorMessage(err)
          ElMessage.error(message)
          return Promise.reject(err)
        })
    }
  }
}

export default api
