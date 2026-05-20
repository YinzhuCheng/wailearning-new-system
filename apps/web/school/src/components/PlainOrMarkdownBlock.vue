<template>
  <RichMarkdownDisplay
    v-if="isMarkdown"
    :markdown="text"
    :variant="variant"
    :empty-text="emptyText"
  />
  <div v-else class="plain-body">{{ plainDisplay }}</div>
</template>

<script setup>
import { computed } from 'vue'

import RichMarkdownDisplay from '@/components/RichMarkdownDisplay.vue'
import { isMarkdownFormat } from '@/utils/contentFormat'

const props = defineProps({
  text: { type: String, default: '' },
  format: { type: String, default: 'markdown' },
  variant: { type: String, default: 'student' },
  emptyText: { type: String, default: '（空）' }
})

const isMarkdown = computed(() => isMarkdownFormat(props.format))

const plainDisplay = computed(() => {
  const raw = props.text ?? ''
  return raw.trim() ? raw : props.emptyText
})
</script>

<style scoped>
.plain-body {
  font-size: 14px;
  line-height: 1.65;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
