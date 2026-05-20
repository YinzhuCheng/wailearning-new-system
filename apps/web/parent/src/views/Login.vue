<template>
  <div class="login-container">
    <div class="login-header">
      <div class="logo">🎓</div>
      <img :src="courseEvalMark" alt="CourseEval" class="brand-logo" />
      <h1>Parent Portal</h1>
      <p class="subtitle">CourseEval</p>
    </div>

    <el-card class="login-card">
      <el-form :model="form" :rules="rules" ref="formRef" size="large">
        <el-form-item prop="parentCode">
          <el-input
            v-model="form.parentCode"
            placeholder="请输入8位家长码"
            maxlength="8"
            :prefix-icon="Key"
            @keyup.enter="handleLogin"
          >
          </el-input>
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            :loading="loading"
            @click="handleLogin"
            class="login-btn"
          >
            {{ loading ? '验证中...' : '绑定孩子' }}
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <div class="tips">
      <p>📌 请使用班主任提供的8位家长码</p>
      <p>❓ 如有疑问请联系学校老师</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Key } from '@element-plus/icons-vue'
import api from '@/api'
import { clearParentSession } from '@/session'
import courseEvalMark from '@/assets/brand/courseeval-mark.svg'

const router = useRouter()
const formRef = ref()
const loading = ref(false)

const form = ref({
  parentCode: ''
})

const rules = {
  parentCode: [
    { required: true, message: '请输入家长码', trigger: 'blur' },
    { min: 8, max: 8, message: '家长码为8位', trigger: 'blur' }
  ]
}

const handleLogin = async () => {
  await formRef.value.validate()

  loading.value = true
  try {
    clearParentSession()
    const verifyResult = await api.verifyCode(form.value.parentCode)

    if (verifyResult.valid) {
      localStorage.setItem('parent_code', form.value.parentCode)
      localStorage.setItem('student_name', verifyResult.student_name)
      localStorage.setItem('class_name', verifyResult.class_name)

      ElMessage.success(`绑定成功！欢迎，${verifyResult.student_name}的家长`)

      const student = await api.getStudent(form.value.parentCode)
      localStorage.setItem('student_id', student.student_id)
      localStorage.setItem('class_id', student.class_id)

      router.push('/home')
    } else {
      ElMessage.error(verifyResult.message)
    }
  } catch (error) {
    ElMessage.error(error.detail || error.message || '验证失败，请检查家长码是否正确')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 20px;
  background: #409eff;
}

.login-header {
  text-align: center;
  margin-bottom: 30px;
  color: white;
}

.logo {
  font-size: 64px;
  margin-bottom: 10px;
}

.brand-logo {
  width: 72px;
  height: 72px;
  display: block;
  margin: 0 auto 12px;
  border-radius: 16px;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.22);
}

.login-header > .logo {
  display: none;
}

.login-header h1 {
  font-size: 28px;
  margin: 10px 0;
  text-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.subtitle {
  font-size: 14px;
  opacity: 0.9;
}

.login-card {
  border-radius: 16px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
}

.login-card :deep(.el-form-item) {
  margin-bottom: 24px;
}

.login-btn {
  width: 100%;
  height: 48px;
  font-size: 16px;
  border-radius: 24px;
}

.tips {
  margin-top: 30px;
  text-align: center;
  color: rgba(255, 255, 255, 0.9);
  font-size: 13px;
}

.tips p {
  margin: 8px 0;
}
</style>
