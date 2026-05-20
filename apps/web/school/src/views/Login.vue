<template>
  <div class="login-container" :class="{ 'has-background': hasBackground }" :style="backgroundStyle" data-testid="login-page">
    <div class="login-card" data-testid="login-panel">
      <div class="login-header">
        <div class="logo-container">
          <img :src="settings.system_logo || courseEvalLogo" alt="CourseEval" class="system-logo" />
        </div>
        <h1 class="system-name">{{ settings.system_name }}</h1>
        <p class="system-desc">{{ settings.system_intro }}</p>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" class="login-form">
        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            placeholder="用户名 / Username"
            :prefix-icon="User"
            size="large"
            clearable
            data-testid="login-username"
          />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码 / Password"
            :prefix-icon="Lock"
            size="large"
            show-password
            data-testid="login-password"
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            data-testid="login-submit"
            @click="handleLogin"
            class="login-btn"
          >
            {{ loading ? '登录中...' : '登录' }}
          </el-button>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" link class="forgot-link" @click="openForgotDialog">忘记密码</el-button>
        </el-form-item>
      </el-form>

      <div class="login-footer">
        {{ settings.copyright }}
      </div>
    </div>

    <!-- Outside .login-card so layout is not clipped by the card; teleports to body with full-viewport modal. -->
    <teleport to="body">
      <el-dialog
        v-model="forgotVisible"
        title="忘记密码"
        width="440px"
        align-center
        append-to-body
        destroy-on-close
        class="login-forgot-dialog"
        modal-class="login-forgot-dialog__overlay"
        @closed="resetForgot"
      >
        <p class="forgot-hint">
          将向管理员反馈并重置密码，请使用邮箱或其他通讯手段联系管理员获取新密码。
        </p>
        <el-form ref="forgotFormRef" :model="forgotForm" :rules="forgotRules" label-width="0">
          <el-form-item prop="username">
            <el-input v-model="forgotForm.username" placeholder="请输入用户名" clearable />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="forgotVisible = false">取消</el-button>
          <el-button type="primary" :loading="forgotSubmitting" @click="submitForgot">确定</el-button>
        </template>
      </el-dialog>
    </teleport>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import { Lock, User } from '@element-plus/icons-vue'

import courseEvalLogo from '@/assets/brand/courseeval-logo.svg'
import { normalizeSystemSettings } from '@/utils/branding'
import { useUserStore } from '@/stores/user'
import api from '@/api'

const apiPublic = axios.create({ baseURL: '/api' })
const router = useRouter()
const userStore = useUserStore()

const formRef = ref(null)
const loading = ref(false)
const bingBackground = ref('')

const settings = ref({
  system_name: 'CourseEval',
  system_logo: '',
  system_intro: 'Teaching management platform',
  login_background: '',
  copyright: '(c) 2026 CourseEval',
  use_bing_background: true
})

const form = reactive({
  username: '',
  password: ''
})

const forgotVisible = ref(false)
const forgotSubmitting = ref(false)
const forgotFormRef = ref(null)
const forgotForm = reactive({ username: '' })
const forgotRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }]
}

const openForgotDialog = () => {
  forgotForm.username = form.username?.trim() || ''
  forgotVisible.value = true
}

const resetForgot = () => {
  forgotForm.username = ''
  forgotFormRef.value?.clearValidate?.()
}

const submitForgot = async () => {
  await forgotFormRef.value?.validate?.()
  forgotSubmitting.value = true
  try {
    const msg = await api.auth.forgotPassword({ username: forgotForm.username.trim() })
    ElMessage.success(msg?.message || '已提交')
    forgotVisible.value = false
  } catch (e) {
    console.error(e)
  } finally {
    forgotSubmitting.value = false
  }
}

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

const backgroundStyle = computed(() => {
  if (settings.value.use_bing_background && bingBackground.value) {
    return {
      backgroundImage: `url(${bingBackground.value})`,
      backgroundSize: 'cover',
      backgroundPosition: 'center'
    }
  }
  if (settings.value.login_background) {
    return {
      backgroundImage: `url(${settings.value.login_background})`,
      backgroundSize: 'cover',
      backgroundPosition: 'center'
    }
  }
  return {}
})

const hasBackground = computed(() => {
  return (settings.value.use_bing_background && bingBackground.value) || settings.value.login_background
})

const fetchBingBackground = async () => {
  try {
    const res = await apiPublic.get('/bing-background')
    if (res.data.url) {
      bingBackground.value = res.data.url
    }
  } catch (error) {
    console.error('获取 Bing 背景失败', error)
  }
}

const fetchSettings = async () => {
  try {
    const res = await apiPublic.get('/settings/public')
    const normalizedSettings = normalizeSystemSettings(res.data)
    settings.value = normalizedSettings
    document.title = normalizedSettings?.system_name || 'CourseEval Admin'
  } catch (error) {
    console.error('获取系统设置失败', error)
  }
}

const handleLogin = async () => {
  await formRef.value.validate(async valid => {
    if (!valid) return

    loading.value = true
    try {
      const userData = await userStore.login(form.username, form.password)
      const needsAutoCourse = ['teacher', 'class_teacher'].includes(userData?.role)
      let preferredCourse = null
      if (needsAutoCourse) {
        preferredCourse = await userStore.ensureSelectedCourse(true)
      } else if (userData?.role === 'student') {
        await userStore.fetchTeachingCourses(true)
      }
      ElMessage.success('登录成功')

      if (userData?.role === 'admin') {
        router.push('/students')
        return
      }

      if (userData?.role === 'teacher' || userData?.role === 'class_teacher') {
        router.push('/students')
        return
      }

      router.push('/courses')
    } catch (error) {
      console.error(error)
      ElMessage.error('登录失败，请检查用户名和密码')
    } finally {
      loading.value = false
    }
  })
}

onMounted(async () => {
  await Promise.all([fetchSettings(), fetchBingBackground()])
})
</script>

<style scoped>
.login-container {
  width: 100%;
  height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: linear-gradient(135deg, var(--wa-color-primary-900) 0%, var(--wa-color-primary-700) 52%, var(--wa-color-accent-600) 100%);
  position: relative;
  overflow: hidden;
}

.login-container.has-background {
  background-size: cover !important;
  background-position: center !important;
}

.login-container.has-background::before,
.login-container.has-background::after {
  display: none;
}

.login-container:not(.has-background)::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 20% 80%, rgba(56, 189, 248, 0.28) 0%, transparent 48%),
    radial-gradient(circle at 80% 20%, color-mix(in srgb, var(--wa-color-primary-300) 24%, transparent) 0%, transparent 45%);
}

.login-card {
  width: 420px;
  padding: 40px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(16px);
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.24);
  border: 1px solid rgba(255, 255, 255, 0.35);
  position: relative;
  z-index: 1;
}

.login-header {
  text-align: center;
  margin-bottom: 28px;
}

.logo-container {
  margin-bottom: 16px;
}

.system-logo {
  max-width: 200px;
  max-height: 60px;
}

.system-name {
  margin: 0 0 12px;
  font-size: 28px;
  color: #0f172a;
  color: var(--wa-color-text);
}

.system-desc {
  margin: 0;
  color: var(--wa-color-text-muted);
  line-height: 1.7;
}

.login-btn {
  width: 100%;
  height: 46px;
  border-radius: 14px;
}

.forgot-link {
  padding: 0;
  font-size: 14px;
}

.forgot-hint {
  margin: 0 0 16px;
  color: var(--wa-color-text-muted);
  line-height: 1.65;
  font-size: 14px;
}

:deep(.login-forgot-dialog__overlay) {
  z-index: 3000;
}

:deep(.login-forgot-dialog.el-overlay-dialog) {
  z-index: 3001;
}

.login-footer {
  margin-top: 16px;
  text-align: center;
  color: var(--wa-color-text-muted);
  font-size: 13px;
}

@media (max-width: 768px) {
  .login-card {
    width: calc(100% - 32px);
    padding: 28px 22px;
  }
}
</style>
