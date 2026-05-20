<template>
  <router-view />
</template>

<script setup>
import { onMounted, watch } from 'vue'

import { useUserStore } from '@/stores/user'
import { applyAppearanceStyle, resolveAppearanceFromState } from '@/utils/theme'

const userStore = useUserStore()

function syncAdminTheme() {
  applyAppearanceStyle(resolveAppearanceFromState(userStore.systemSettings || {}, userStore.appearanceState))
}

watch(() => userStore.systemSettings, syncAdminTheme, { deep: true })
watch(() => userStore.appearanceState, syncAdminTheme, { deep: true })

onMounted(async () => {
  syncAdminTheme()
  if (userStore.isLoggedIn) {
    await userStore.fetchAppearanceState()
    syncAdminTheme()
  }
})
</script>
