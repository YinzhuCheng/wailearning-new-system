const fs = require('fs')
const path = require('path')
const vm = require('vm')

const repoRoot = path.resolve(__dirname, '..')
const utilsPath = path.join(repoRoot, 'src', 'utils', 'appealNotificationActions.js')
const notificationsViewPath = path.join(repoRoot, 'src', 'views', 'Notifications.vue')

function loadResolverModule(filePath) {
  let source = fs.readFileSync(filePath, 'utf8')
  source = source.replace(/export const /g, 'const ')
  source = source.replace(/export function /g, 'function ')
  source += `
module.exports = {
  APPEAL_STATUS_PENDING,
  APPEAL_STATUS_ACKNOWLEDGED,
  APPEAL_STATUS_RESOLVED,
  APPEAL_STATUS_REJECTED,
  isTerminalAppealStatus,
  isActionableAppealStatus,
  getAppealStatusLabel,
  getAppealStatusTagType,
  getAppealActionLabel,
  getAppealReadonlyLabel,
  canOpenAppealNotification,
  buildAppealNotificationRoute
}
`
  const context = { module: { exports: {} }, exports: {} }
  vm.createContext(context)
  new vm.Script(source, { filename: filePath }).runInContext(context)
  return context.module.exports
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message)
  }
}

function run() {
  const resolver = loadResolverModule(utilsPath)
  const {
    APPEAL_STATUS_PENDING,
    APPEAL_STATUS_ACKNOWLEDGED,
    APPEAL_STATUS_RESOLVED,
    APPEAL_STATUS_REJECTED,
    isTerminalAppealStatus,
    isActionableAppealStatus,
    getAppealStatusLabel,
    getAppealActionLabel,
    getAppealReadonlyLabel,
    canOpenAppealNotification,
    buildAppealNotificationRoute
  } = resolver

  assert(isActionableAppealStatus(APPEAL_STATUS_PENDING), 'pending should be actionable')
  assert(isActionableAppealStatus(APPEAL_STATUS_ACKNOWLEDGED), 'acknowledged should be actionable')
  assert(!isActionableAppealStatus(APPEAL_STATUS_RESOLVED), 'resolved should not be actionable')
  assert(!isActionableAppealStatus(APPEAL_STATUS_REJECTED), 'rejected should not be actionable')

  assert(!isTerminalAppealStatus(APPEAL_STATUS_PENDING), 'pending should not be terminal')
  assert(!isTerminalAppealStatus(APPEAL_STATUS_ACKNOWLEDGED), 'acknowledged should not be terminal')
  assert(isTerminalAppealStatus(APPEAL_STATUS_RESOLVED), 'resolved should be terminal')
  assert(isTerminalAppealStatus(APPEAL_STATUS_REJECTED), 'rejected should be terminal')

  assert(getAppealStatusLabel(APPEAL_STATUS_PENDING) === '待处理', 'pending label mismatch')
  assert(getAppealStatusLabel(APPEAL_STATUS_ACKNOWLEDGED) === '已阅', 'acknowledged label mismatch')
  assert(getAppealStatusLabel(APPEAL_STATUS_RESOLVED) === '已处理', 'resolved label mismatch')
  assert(getAppealStatusLabel(APPEAL_STATUS_REJECTED) === '已拒绝', 'rejected label mismatch')

  const gradeNotification = {
    notification_kind: 'grade_appeal',
    related_homework_id: 12,
    related_student_id: 34,
    appeal_status: APPEAL_STATUS_PENDING
  }
  assert(getAppealActionLabel(gradeNotification) === '处理', 'pending homework action label should be 处理')
  assert(canOpenAppealNotification(gradeNotification, { isStudent: false }), 'teacher should open homework appeal notification')
  assert(!canOpenAppealNotification(gradeNotification, { isStudent: true }), 'student should not open homework appeal notification')
  const gradeRoute = buildAppealNotificationRoute(gradeNotification)
  assert(gradeRoute && gradeRoute.path === '/homework/12/submissions', 'homework route path mismatch')
  assert(gradeRoute.query.student_id === '34', 'homework route student id mismatch')

  const scoreNotification = {
    notification_kind: 'score_grade_appeal',
    subject_id: 56,
    related_score_appeal_id: 78,
    appeal_status: APPEAL_STATUS_RESOLVED
  }
  assert(getAppealActionLabel(scoreNotification) === '查看', 'resolved score action label should be 查看')
  assert(getAppealReadonlyLabel(scoreNotification) === '查看对应成绩申诉', 'readonly score label mismatch')
  const scoreRoute = buildAppealNotificationRoute(scoreNotification)
  assert(scoreRoute && scoreRoute.path === '/scores', 'score route path mismatch')
  assert(scoreRoute.query.appeal_id === '78', 'score route appeal id mismatch')
  assert(scoreRoute.query.subject_id === '56', 'score route subject id mismatch')

  const scoreHomeworkNotification = {
    notification_kind: 'score_grade_appeal',
    subject_id: 56,
    related_score_appeal_id: 78,
    related_homework_id: 90,
    related_student_id: 34,
    appeal_status: APPEAL_STATUS_PENDING
  }
  assert(getAppealReadonlyLabel(scoreHomeworkNotification) === '查看对应作业评分页', 'score-homework readonly label mismatch')
  const scoreHomeworkRoute = buildAppealNotificationRoute(scoreHomeworkNotification)
  assert(scoreHomeworkRoute && scoreHomeworkRoute.path === '/homework/90/submissions', 'score-homework route path mismatch')
  assert(scoreHomeworkRoute.query.student_id === '34', 'score-homework route student id mismatch')

  const incompleteScoreNotification = {
    notification_kind: 'score_grade_appeal',
    subject_id: 56,
    appeal_status: APPEAL_STATUS_RESOLVED
  }
  assert(buildAppealNotificationRoute(incompleteScoreNotification) === null, 'missing score appeal id should not build route')

  const notificationsView = fs.readFileSync(notificationsViewPath, 'utf8')
  assert(
    !notificationsView.includes("appeal_status === 'resolved'"),
    'Notifications.vue should not inline resolved-only appeal checks'
  )

  console.log('appeal notification resolver checks passed')
}

run()
