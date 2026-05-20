import router from '@/router'

export function clearParentSession() {
  localStorage.removeItem('parent_code')
  localStorage.removeItem('student_name')
  localStorage.removeItem('class_name')
  localStorage.removeItem('student_id')
  localStorage.removeItem('class_id')
}

export function handleParentApiError(error) {
  const status = error?.status_code || error?.status
  if ([403, 404, 429].includes(status)) {
    clearParentSession()
    if (router.currentRoute.value.path !== '/login') {
      router.replace('/login')
    }
    return true
  }
  return false
}
