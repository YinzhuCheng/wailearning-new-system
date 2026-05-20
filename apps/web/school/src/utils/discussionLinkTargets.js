import api from '@/api'

export function discussionLinkedTargetKey(target) {
  return `${target?.target_type || ''}:${target?.target_id || ''}`
}

async function switchSelectedCourseIfNeeded(userStore, target) {
  if (!target?.subject_id || !userStore.canSelectCourse) {
    return
  }
  if (String(userStore.selectedCourse?.id || '') === String(target.subject_id)) {
    return
  }
  const courses = await userStore.fetchTeachingCourses(false)
  const match = courses.find(item => String(item.id) === String(target.subject_id))
  if (match) {
    userStore.setSelectedCourse(match)
  }
}

async function resolveDiscussionLinkedTargetRoute(target, userStore) {
  if (!target?.target_type || !target?.target_id) {
    return null
  }
  if (target.target_type === 'course') {
    await switchSelectedCourseIfNeeded(userStore, target)
    return userStore.isStudent ? { name: 'StudentCourseHome' } : { name: 'Students' }
  }
  if (target.target_type === 'homework') {
    if (userStore.isStudent || userStore.isAdmin) {
      return { name: 'HomeworkSubmit', params: { id: String(target.target_id) } }
    }
    return { name: 'HomeworkSubmissions', params: { id: String(target.target_id) } }
  }
  if (target.target_type === 'material') {
    return { name: 'MaterialRead', params: { id: String(target.target_id) } }
  }
  if (target.target_type === 'learning_note') {
    return { name: 'LearningNotes', query: { note: String(target.target_id) } }
  }
  if (target.target_type === 'discussion_entry') {
    const meta = target.meta || {}
    if (meta.discussion_family === 'learning_note') {
      const locator = await api.learningNotes.locateDiscussionEntry(target.target_id, { page_size: 20 })
      return {
        name: 'LearningNotes',
        query: {
          note: String(locator.note_id),
          discussion_entry: String(locator.target_id || target.target_id),
          discussion_page: String(locator.page || 1)
        }
      }
    }
    const locator = await api.discussions.locateEntry(meta.entry_id || target.target_id, {
      page_size: userStore.userInfo?.discussion_page_size || undefined
    })
    const query = {
      discussion_entry: String(locator.entry_id),
      discussion_page: String(locator.page || 1)
    }
    if (locator.thread_target_type === 'material') {
      return { name: 'MaterialRead', params: { id: String(locator.thread_target_id) }, query }
    }
    if (userStore.isStudent || userStore.isAdmin) {
      return { name: 'HomeworkSubmit', params: { id: String(locator.thread_target_id) }, query }
    }
    return { name: 'HomeworkSubmissions', params: { id: String(locator.thread_target_id) }, query }
  }
  return null
}

export async function openDiscussionLinkedTarget(target, router, userStore) {
  if (!target?.available) {
    return
  }
  await switchSelectedCourseIfNeeded(userStore, target)
  const route = await resolveDiscussionLinkedTargetRoute(target, userStore)
  if (!route) {
    return
  }
  await router.push(route)
}
