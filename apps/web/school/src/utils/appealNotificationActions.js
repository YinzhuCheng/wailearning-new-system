export const APPEAL_STATUS_PENDING = 'pending'
export const APPEAL_STATUS_ACKNOWLEDGED = 'acknowledged'
export const APPEAL_STATUS_RESOLVED = 'resolved'
export const APPEAL_STATUS_REJECTED = 'rejected'

const ACTIONABLE_STATUSES = new Set([APPEAL_STATUS_PENDING, APPEAL_STATUS_ACKNOWLEDGED])
const TERMINAL_STATUSES = new Set([APPEAL_STATUS_RESOLVED, APPEAL_STATUS_REJECTED])

const STATUS_META = {
  [APPEAL_STATUS_PENDING]: { shortLabel: '待处理', detailLabel: '待处理', tagType: 'warning' },
  [APPEAL_STATUS_ACKNOWLEDGED]: { shortLabel: '已阅', detailLabel: '已阅/处理中', tagType: 'info' },
  [APPEAL_STATUS_RESOLVED]: { shortLabel: '已处理', detailLabel: '已处理', tagType: 'success' },
  [APPEAL_STATUS_REJECTED]: { shortLabel: '已拒绝', detailLabel: '已拒绝', tagType: 'danger' }
}

function normalizeStatus(status) {
  return typeof status === 'string' ? status.trim().toLowerCase() : ''
}

export function isTerminalAppealStatus(status) {
  return TERMINAL_STATUSES.has(normalizeStatus(status))
}

export function isActionableAppealStatus(status) {
  return ACTIONABLE_STATUSES.has(normalizeStatus(status))
}

export function getAppealStatusMeta(status) {
  return STATUS_META[normalizeStatus(status)] || null
}

export function getAppealStatusLabel(status, options = {}) {
  const meta = getAppealStatusMeta(status)
  if (!meta) {
    return typeof status === 'string' && status.trim() ? status.trim() : ''
  }
  return options.verbose ? meta.detailLabel : meta.shortLabel
}

export function getAppealStatusTagType(status) {
  return getAppealStatusMeta(status)?.tagType || 'info'
}

export function isHomeworkAppealNotification(notification) {
  return (
    notification?.notification_kind === 'grade_appeal' &&
    Boolean(notification?.related_homework_id) &&
    Boolean(notification?.related_student_id)
  )
}

export function isScoreAppealNotification(notification) {
  return notification?.notification_kind === 'score_grade_appeal' && Boolean(notification?.subject_id)
}

export function getAppealActionLabel(notification) {
  return isTerminalAppealStatus(notification?.appeal_status) ? '查看' : '处理'
}

export function getAppealReadonlyLabel(notification) {
  if (isScoreAppealNotification(notification) && notification?.related_homework_id) {
    return '查看对应作业评分页'
  }
  if (isScoreAppealNotification(notification)) {
    return '查看对应成绩申诉'
  }
  if (isHomeworkAppealNotification(notification)) {
    return '查看对应作业评分页'
  }
  return '查看申诉'
}

export function canOpenAppealNotification(notification, userContext = {}) {
  if (userContext.isStudent) {
    return false
  }
  return isHomeworkAppealNotification(notification) || isScoreAppealNotification(notification)
}

export function buildAppealNotificationRoute(notification) {
  if (isHomeworkAppealNotification(notification)) {
    return {
      path: `/homework/${notification.related_homework_id}/submissions`,
      query: { student_id: String(notification.related_student_id) }
    }
  }

  if (isScoreAppealNotification(notification)) {
    if (notification.related_homework_id) {
      return {
        path: `/homework/${notification.related_homework_id}/submissions`,
        query: notification.related_student_id ? { student_id: String(notification.related_student_id) } : {}
      }
    }
    if (!notification.related_score_appeal_id) {
      return null
    }
    return {
      path: '/scores',
      query: {
        appeal_id: String(notification.related_score_appeal_id),
        subject_id: String(notification.subject_id)
      }
    }
  }

  return null
}

export function buildAppealRouteSelectedCourse(notification) {
  if (!isScoreAppealNotification(notification)) {
    return null
  }
  return {
    id: notification.subject_id,
    name: notification.subject_name || '',
    class_id: notification.class_id || null,
    class_name: notification.class_name || ''
  }
}
