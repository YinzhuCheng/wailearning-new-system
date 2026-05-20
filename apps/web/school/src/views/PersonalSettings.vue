<template>
  <div class="personal-settings">
    <div class="page-head">
      <h1>个人设置</h1>
      <p class="muted">管理显示名称、头像与登录密码</p>
    </div>

    <div class="settings-grid">
      <el-card class="block-card block-card--profile" shadow="never">
        <template #header>
          <span>基本信息</span>
        </template>
        <el-form label-position="top" class="profile-form" @submit.prevent>
          <el-form-item label="用户名">
            <el-input :model-value="userStore.userInfo?.username || ''" disabled />
          </el-form-item>
          <el-form-item label="姓名">
            <el-input
              v-model="profileForm.real_name"
              data-testid="personal-profile-real-name"
              maxlength="120"
              show-word-limit
              placeholder="用于界面显示的姓名"
            />
          </el-form-item>
          <el-form-item label="角色">
            <el-input :model-value="roleLabel" disabled />
          </el-form-item>
          <el-form-item label="讨论区分页（每页回复条数）">
            <el-input-number
              v-model="profileForm.discussion_page_size"
              :min="5"
              :max="50"
              :step="1"
              controls-position="right"
              data-testid="personal-discussion-page-size"
            />
            <p class="hint">默认 5；仅影响作业与资料讨论区的分页，可在 5～50 之间调整。</p>
          </el-form-item>
          <el-form-item label="教材视图风格">
            <el-radio-group v-model="profileForm.material_presentation_style" class="material-style-group">
              <el-radio-button
                v-for="option in materialPresentationOptions"
                :key="option.value"
                :label="option.value"
              >
                {{ option.label }}
              </el-radio-button>
            </el-radio-group>
            <p class="hint">{{ currentMaterialPresentationDescription }}</p>
          </el-form-item>
          <el-button type="primary" data-testid="personal-profile-save" :loading="profileSaving" @click="saveProfile">
            保存基本信息
          </el-button>
          <el-button plain @click="router.push({ name: 'RecentPostsMine' })">
            近期发表
          </el-button>
        </el-form>
      </el-card>

    <el-card class="block-card" shadow="never">
      <template #header>
        <span>头像</span>
      </template>
      <div class="avatar-row">
        <el-avatar :size="96" :src="avatarDisplaySrc">
          {{ userStore.userInfo?.real_name?.charAt(0) || 'U' }}
        </el-avatar>
        <div class="avatar-actions">
          <el-upload
            accept="image/jpeg,image/png,image/gif,image/webp"
            :show-file-list="false"
            :before-upload="beforeAvatarUpload"
            :http-request="handleAvatarRequest"
          >
            <el-button type="primary" :loading="avatarUploading">上传头像</el-button>
          </el-upload>
          <el-button
            v-if="userStore.userInfo?.avatar_url"
            :loading="avatarRemoving"
            @click="removeAvatar"
          >
            移除头像
          </el-button>
          <p class="hint">支持 JPG、PNG、GIF、WebP，最大 2 MB。</p>
        </div>
      </div>
    </el-card>

    <el-card class="block-card" shadow="never">
      <template #header>
        <span>修改密码</span>
      </template>
      <el-form label-position="top" class="pwd-form" @submit.prevent>
        <input
          :value="userStore.userInfo?.username || ''"
          type="text"
          name="username"
          autocomplete="username"
          readonly
          tabindex="-1"
          aria-hidden="true"
          class="hidden-username"
        />

        <el-form-item label="当前密码">
          <el-input
            v-model="passwordForm.current_password"
            type="password"
            show-password
            autocomplete="current-password"
          />
        </el-form-item>

        <el-form-item label="新密码">
          <el-input
            v-model="passwordForm.new_password"
            type="password"
            show-password
            autocomplete="new-password"
          />
        </el-form-item>

        <el-form-item label="确认新密码">
          <el-input
            v-model="passwordForm.confirm_password"
            type="password"
            show-password
            autocomplete="new-password"
            @keyup.enter="submitChangePassword"
          />
        </el-form-item>

        <el-text type="info">新密码需为 8 到 72 个字符，保存后立即生效。</el-text>
        <div class="pwd-actions">
          <el-button type="primary" :loading="passwordSubmitting" @click="submitChangePassword">
            更新密码
          </el-button>
        </div>
      </el-form>
    </el-card>
    </div>

    <AppearanceStylePanel />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import api from '@/api'
import AppearanceStylePanel from '@/components/AppearanceStylePanel.vue'
import { fetchAttachmentBlobUrl, validateAttachmentFile } from '@/utils/attachments'
import {
  getMaterialPresentationStyle,
  MATERIAL_PRESENTATION_OPTIONS,
  setMaterialPresentationStyle
} from '@/utils/materialPresentation'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const router = useRouter()

const profileForm = reactive({
  real_name: '',
  discussion_page_size: 5,
  material_presentation_style: 'academic'
})

const profileSaving = ref(false)
const avatarUploading = ref(false)
const avatarRemoving = ref(false)
const passwordSubmitting = ref(false)

const passwordForm = reactive({
  current_password: '',
  new_password: '',
  confirm_password: ''
})

const avatarDisplaySrc = ref('')
let avatarBlobUrl = ''

const revokeAvatarBlob = () => {
  if (avatarBlobUrl) {
    URL.revokeObjectURL(avatarBlobUrl)
    avatarBlobUrl = ''
  }
  avatarDisplaySrc.value = ''
}

const loadAvatarPreview = async () => {
  revokeAvatarBlob()
  const url = userStore.userInfo?.avatar_url
  if (!url) {
    return
  }
  try {
    avatarBlobUrl = await fetchAttachmentBlobUrl(url)
    avatarDisplaySrc.value = avatarBlobUrl
  } catch (error) {
    console.error('加载头像失败', error)
  }
}

const roleLabel = computed(
  () =>
    ({
      admin: '管理员',
      class_teacher: '班主任',
      teacher: '任课老师',
      student: '学生'
    }[userStore.userInfo?.role] || '—')
)

const materialPresentationOptions = MATERIAL_PRESENTATION_OPTIONS
const currentMaterialPresentationDescription = computed(
  () =>
    materialPresentationOptions.find(option => option.value === profileForm.material_presentation_style)?.description ||
    ''
)

const syncProfileForm = () => {
  profileForm.real_name = userStore.userInfo?.real_name || ''
  const d = userStore.userInfo?.discussion_page_size
  profileForm.discussion_page_size =
    d != null && Number.isFinite(Number(d)) && Number(d) >= 5 && Number(d) <= 50 ? Number(d) : 5
  profileForm.material_presentation_style = getMaterialPresentationStyle()
}

watch(
  () => userStore.userInfo?.id,
  () => {
    syncProfileForm()
  },
  { immediate: true }
)

watch(
  () => userStore.userInfo?.avatar_url,
  () => {
    loadAvatarPreview()
  },
  { immediate: true }
)

const saveProfile = async () => {
  const name = (profileForm.real_name || '').trim()
  if (!name) {
    ElMessage.warning('请填写姓名')
    return
  }

  profileSaving.value = true
  try {
    await api.auth.updateProfile({
      real_name: name,
      discussion_page_size: profileForm.discussion_page_size
    })
    setMaterialPresentationStyle(profileForm.material_presentation_style)
    await userStore.refreshUserInfo()
    ElMessage.success('已保存')
  } finally {
    profileSaving.value = false
  }
}

const beforeAvatarUpload = rawFile => {
  const hint = validateAttachmentFile(rawFile, { imageOnly: true })
  if (!hint.valid) {
    ElMessage.warning(hint.message)
    return false
  }
  if (rawFile.size > 2 * 1024 * 1024) {
    ElMessage.warning('头像大小不能超过 2 MB')
    return false
  }
  const lower = (rawFile.name || '').toLowerCase()
  const ok = ['.jpg', '.jpeg', '.png', '.gif', '.webp'].some(ext => lower.endsWith(ext))
  if (!ok) {
    ElMessage.warning('请选择 JPG、PNG、GIF 或 WebP 图片')
    return false
  }
  return true
}

const handleAvatarRequest = async ({ file }) => {
  avatarUploading.value = true
  try {
    await api.auth.uploadAvatar(file)
    await userStore.refreshUserInfo()
    ElMessage.success('头像已更新')
  } finally {
    avatarUploading.value = false
  }
}

const removeAvatar = async () => {
  avatarRemoving.value = true
  try {
    await api.auth.deleteAvatar()
    await userStore.refreshUserInfo()
    ElMessage.success('已移除头像')
  } finally {
    avatarRemoving.value = false
  }
}

const resetPasswordForm = () => {
  passwordForm.current_password = ''
  passwordForm.new_password = ''
  passwordForm.confirm_password = ''
}

const submitChangePassword = async () => {
  if (!passwordForm.current_password || !passwordForm.new_password || !passwordForm.confirm_password) {
    ElMessage.warning('请完整填写密码信息')
    return
  }

  if (passwordForm.new_password !== passwordForm.confirm_password) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }

  passwordSubmitting.value = true
  try {
    const result = await api.auth.changePassword({ ...passwordForm })
    ElMessage.success(result?.message || '密码修改成功')
    resetPasswordForm()
  } finally {
    passwordSubmitting.value = false
  }
}

onMounted(() => {
  syncProfileForm()
})

onBeforeUnmount(() => {
  revokeAvatarBlob()
})
</script>

<style scoped>
.personal-settings {
  max-width: 1080px;
  padding: 24px 28px 48px;
}

.settings-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(280px, 0.75fr);
  gap: 20px;
}

.page-head {
  margin-bottom: 20px;
  text-align: center;
}

.page-head h1 {
  margin: 0 0 6px;
  font-size: var(--wa-font-size-2xl);
  font-weight: 600;
  color: #0f172a;
}

.muted {
  margin: 0;
  font-size: var(--wa-font-size-md);
  color: #64748b;
}

.block-card {
  margin-bottom: 20px;
  border-radius: 12px;
}

.settings-grid :deep(.el-card__header) {
  text-align: center;
}

.block-card--profile {
  grid-row: span 2;
}

.profile-form {
  max-width: 520px;
  margin: 0 auto;
}

.avatar-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 24px;
  text-align: center;
}

.avatar-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.avatar-actions .hint {
  margin: 4px 0 0;
  font-size: var(--wa-font-size-sm);
  color: #64748b;
  text-align: center;
}

.pwd-form {
  max-width: 520px;
  margin: 0 auto;
}

.pwd-actions {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

.profile-form :deep(.el-form-item__label),
.pwd-form :deep(.el-form-item__label) {
  justify-content: center;
  width: 100%;
  text-align: center;
}

.profile-form .hint,
.pwd-form :deep(.el-text) {
  display: block;
  text-align: center;
}

.material-style-group {
  display: inline-flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}

.profile-form > .el-button {
  display: flex;
  margin: 0 auto;
}

.hidden-username {
  position: absolute;
  left: -9999px;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

@media (max-width: 900px) {
  .personal-settings {
    padding: 18px 16px 36px;
  }

  .settings-grid {
    grid-template-columns: 1fr;
  }

  .block-card--profile {
    grid-row: auto;
  }
}
</style>
