export const resolveClassTeacherClassId = (userInfo, courses = []) => {
  if (userInfo?.class_id) {
    return Number(userInfo.class_id)
  }

  const firstCourse = (courses || []).find(course => course?.class_id)
  return firstCourse?.class_id ? Number(firstCourse.class_id) : null
}

export const resolveClassTeacherClassName = (userInfo, courses = []) => {
  const classId = resolveClassTeacherClassId(userInfo, courses)

  if (!classId) {
    return ''
  }

  const matchedCourse = (courses || []).find(course => Number(course?.class_id) === classId && course?.class_name)
  return matchedCourse?.class_name || ''
}

export const filterCoursesByClassId = (courses = [], classId) => {
  if (!classId) {
    return []
  }

  const cid = Number(classId)
  return (courses || []).filter(course => {
    if (Number(course?.class_id) === cid) {
      return true
    }
    const links = course?.class_links || []
    return links.some(l => Number(l.class_id) === cid)
  })
}

export const filterNotificationsForClass = (notifications = [], classId, courseIds = new Set()) => {
  if (!classId) {
    return []
  }

  return (notifications || []).filter(notification => {
    const matchesClass = Number(notification?.class_id) === Number(classId)
    const matchesCourse = notification?.subject_id ? courseIds.has(Number(notification.subject_id)) : false
    return matchesClass || matchesCourse
  })
}

export const filterImportantNotifications = (notifications = []) =>
  (notifications || []).filter(notification => ['important', 'urgent'].includes(notification?.priority))
