import { createRouter, createWebHistory } from 'vue-router'
import { clearParentSession } from '@/session'

const routes = [
  {
    path: '/',
    redirect: '/login'
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue')
  },
  {
    path: '/home',
    name: 'Home',
    component: () => import('@/views/Home.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/scores',
    name: 'Scores',
    component: () => import('@/views/Scores.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/notifications',
    name: 'Notifications',
    component: () => import('@/views/Notifications.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/homework',
    name: 'Homework',
    component: () => import('@/views/Homework.vue'),
    meta: { requiresAuth: true }
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

router.beforeEach((to, from, next) => {
  const parentCode = localStorage.getItem('parent_code')
  const studentId = localStorage.getItem('student_id')
  if (to.meta.requiresAuth && !parentCode) {
    next('/login')
  } else if (to.meta.requiresAuth && !studentId) {
    clearParentSession()
    next('/login')
  } else {
    next()
  }
})

export default router
