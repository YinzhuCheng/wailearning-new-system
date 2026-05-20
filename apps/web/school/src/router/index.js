import { createRouter, createWebHistory } from 'vue-router'

import { useUserStore } from '@/stores/user'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue')
  },
  {
    path: '/',
    component: () => import('@/views/Layout.vue'),
    children: [
      {
        path: '',
        redirect: '/students'
      },
      {
        path: 'courses',
        name: 'Courses',
        component: () => import('@/views/MyCourses.vue')
      },
      {
        path: 'course-home',
        name: 'StudentCourseHome',
        component: () => import('@/views/StudentCourseHome.vue')
      },
      {
        path: 'dashboard',
        redirect: '/students'
      },
      {
        path: 'teaching-calendar',
        redirect: '/attendance',
        meta: { title: '教学日历' }
      },
      {
        path: 'classes',
        name: 'Classes',
        component: () => import('@/views/Classes.vue'),
        meta: { requiresAdmin: true }
      },
      {
        path: 'students',
        name: 'Students',
        component: () => import('@/views/Students.vue')
      },
      {
        path: 'students/new',
        name: 'StudentCreate',
        component: () => import('@/views/StudentForm.vue'),
        meta: { requiresAdmin: true, title: '新增学生' }
      },
      {
        path: 'students/roster/new',
        name: 'RosterStudentCreate',
        component: () => import('@/views/StudentForm.vue'),
        meta: { requiresTeachingStaff: true, title: '新增花名册学生' }
      },
      {
        path: 'students/:id/edit',
        name: 'StudentEdit',
        component: () => import('@/views/StudentForm.vue'),
        meta: { requiresAdmin: true, title: '编辑学生' }
      },
      {
        path: 'students/:id/roster-edit',
        name: 'RosterStudentEdit',
        component: () => import('@/views/StudentForm.vue'),
        meta: { requiresTeachingStaff: true, title: '编辑花名册学生' }
      },
      {
        path: 'scores',
        name: 'Scores',
        component: () => import('@/views/Scores.vue')
      },
      {
        path: 'student-scores',
        name: 'StudentScores',
        component: () => import('@/views/StudentScores.vue')
      },
      {
        path: 'attendance',
        name: 'Attendance',
        component: () => import('@/views/Attendance.vue')
      },
      {
        path: 'rankings',
        name: 'Rankings',
        component: () => import('@/views/Rankings.vue')
      },
      {
        path: 'analysis',
        name: 'Analysis',
        component: () => import('@/views/Analysis.vue')
      },
      {
        path: 'users',
        name: 'Users',
        component: () => import('@/views/Users.vue'),
        meta: { requiresAdmin: true }
      },
      {
        path: 'subjects',
        name: 'Subjects',
        component: () => import('@/views/Subjects.vue')
      },
      {
        path: 'semesters',
        name: 'Semesters',
        component: () => import('@/views/Semesters.vue'),
        meta: { requiresAdmin: true }
      },
      {
        path: 'logs',
        name: 'Logs',
        component: () => import('@/views/Logs.vue'),
        meta: { requiresAdmin: true }
      },
      {
        path: 'points',
        name: 'Points',
        component: () => import('@/views/Points.vue')
      },
      {
        path: 'points-display',
        name: 'PointsDisplay',
        component: () => import('@/views/PointsDisplay.vue')
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('@/views/Settings.vue'),
        meta: { requiresAdmin: true }
      },
      {
        path: 'homework',
        component: () => import('@/views/HomeworkCenterLayout.vue'),
        redirect: { name: 'Homework' },
        children: [
          {
            path: '',
            name: 'Homework',
            component: () => import('@/views/Homework.vue'),
            meta: { title: '作业管理' }
          },
          {
            path: 'students',
            name: 'StudentHomeworkByCourse',
            component: () => import('@/views/StudentHomeworkByCourse.vue'),
            meta: { title: '学生作业一览', requiresTeacher: true }
          },
          {
            path: 'by-student',
            redirect: '/homework/students'
          },
          {
            path: ':id/submit',
            name: 'HomeworkSubmit',
            component: () => import('@/views/HomeworkSubmission.vue'),
            meta: { title: '提交作业' }
          },
          {
            path: ':id/submissions/:submissionId',
            name: 'HomeworkSubmissionReview',
            component: () => import('@/views/HomeworkSubmissionReview.vue'),
            meta: { title: '提交详情与评分', requiresTeacher: true }
          },
          {
            path: ':id/submissions',
            name: 'HomeworkSubmissions',
            component: () => import('@/views/HomeworkSubmissions.vue'),
            meta: { title: '学生提交', requiresTeacher: true }
          }
        ]
      },
      {
        path: 'materials/read/:id',
        name: 'MaterialRead',
        component: () => import('@/views/MaterialRead.vue'),
        meta: { title: '资料阅读' }
      },
      {
        path: 'materials',
        name: 'Materials',
        component: () => import('@/views/Materials.vue')
      },
      {
        path: 'learning-notes',
        name: 'LearningNotes',
        component: () => import('@/views/LearningNotes.vue'),
        meta: { title: '学习笔记' }
      },
      {
        path: 'recent-posts/me',
        name: 'RecentPostsMine',
        component: () => import('@/views/RecentPosts.vue'),
        meta: { title: '近期发表' }
      },
      {
        path: 'recent-posts/users/:userId',
        name: 'RecentPostsUser',
        component: () => import('@/views/RecentPosts.vue'),
        meta: { title: '近期发表' }
      },
      {
        path: 'notifications',
        name: 'Notifications',
        component: () => import('@/views/Notifications.vue')
      },
      {
        path: 'personal-settings',
        name: 'PersonalSettings',
        component: () => import('@/views/PersonalSettings.vue'),
        meta: { title: '个人设置' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

const adminHomePath = '/students'
const adminHiddenPaths = [
  '/courses',
  '/scores',
  '/attendance',
  '/teaching-calendar',
  '/rankings',
  '/analysis',
  '/points',
  '/materials',
  '/homework',
  '/homework/students'
]

router.beforeEach(async (to, from, next) => {
  const userStore = useUserStore()

  if (to.path !== '/login' && !userStore.isLoggedIn) {
    next('/login')
    return
  }

  if (to.path === '/login' && userStore.isLoggedIn) {
    next(userStore.isAdmin ? adminHomePath : userStore.isStudent ? '/courses' : '/students')
    return
  }

  if (to.meta.requiresAdmin && !userStore.isAdmin) {
    next(userStore.isStudent ? '/courses' : '/students')
    return
  }

  if (
    to.meta.requiresTeachingStaff &&
    !userStore.isAdmin &&
    !userStore.isTeacher &&
    !userStore.isClassTeacher
  ) {
    next(userStore.isStudent ? '/courses' : '/students')
    return
  }

  if (to.meta.requiresTeacher && (userStore.isStudent || userStore.isAdmin)) {
    next(userStore.isStudent ? '/homework' : adminHomePath)
    return
  }

  if (userStore.isAdmin && adminHiddenPaths.includes(to.path)) {
    next(adminHomePath)
    return
  }

  if (
    userStore.isStudent &&
    ['/students', '/scores', '/attendance', '/teaching-calendar', '/rankings', '/analysis', '/points'].includes(to.path)
  ) {
    next('/courses')
    return
  }

  if (!userStore.isAdmin && to.path !== '/login') {
    try {
      await userStore.ensureSelectedCourse(false, {
        preserveEmptySelection: userStore.isStudent
      })
    } catch (error) {
      console.error('Failed to preload teaching courses', error)
    }
  }

  if (
    userStore.isStudent &&
    to.path !== '/courses' &&
    to.path !== '/learning-notes' &&
    !to.path.startsWith('/recent-posts/') &&
    !userStore.selectedCourse &&
    to.path !== '/personal-settings'
  ) {
    try {
      await userStore.ensureSelectedCourse(false, {
        preserveEmptySelection: false
      })
    } catch (error) {
      console.error('Failed to auto-select course for student route', error)
    }
    if (!userStore.selectedCourse) {
      next('/courses')
      return
    }
  }

  next()
})

export default router
