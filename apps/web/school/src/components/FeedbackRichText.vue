<template>
  <div
    ref="rootRef"
    class="feedback-rich"
    :class="variant === 'teacher' ? 'feedback-rich--teacher' : 'feedback-rich--student'"
    v-html="renderedHtml"
  />
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import katex from 'katex'
import renderMathInElement from 'katex/contrib/auto-render'
import 'katex/dist/katex.min.css'

import { createCourseMarkdownIt, renderCourseMarkdown } from '@/utils/markdownIt'

const props = defineProps({
  text: { type: String, default: '' },
  /** 'student' | 'teacher' — subtle theme tint */
  variant: { type: String, default: 'student' }
})

const rootRef = ref(null)

const md = createCourseMarkdownIt()

const renderedHtml = computed(() => {
  const raw = (props.text || '').trim()
  if (!raw) {
    return '<p class="feedback-rich__empty">暂无内容</p>'
  }
  return renderCourseMarkdown(md, raw)
})

const applyMath = () => {
  const el = rootRef.value
  if (!el) {
    return
  }
  try {
    renderMathInElement(el, {
      delimiters: [
        { left: '$$', right: '$$', display: true },
        { left: '$', right: '$', display: false },
        { left: '\\(', right: '\\)', display: false },
        { left: '\\[', right: '\\]', display: true }
      ],
      throwOnError: false,
      trust: false,
      strict: 'ignore'
    })
  } catch {
    /* ignore KaTeX edge cases */
  }
}

onMounted(async () => {
  await nextTick()
  applyMath()
})

watch(
  () => props.text,
  async () => {
    await nextTick()
    applyMath()
  },
  { immediate: true }
)
</script>

<style scoped>
.feedback-rich {
  font-size: 14px;
  line-height: 1.65;
  word-break: break-word;
}

.feedback-rich--student {
  color: #334155;
}

.feedback-rich--teacher {
  color: #1e293b;
  font-size: 13px;
  line-height: 1.6;
}

.feedback-rich :deep(h1),
.feedback-rich :deep(h2),
.feedback-rich :deep(h3) {
  margin: 0.75em 0 0.35em;
  font-weight: 600;
  color: #0f172a;
}

.feedback-rich :deep(h1) {
  font-size: 1.15rem;
}
.feedback-rich :deep(h2) {
  font-size: 1.08rem;
}
.feedback-rich :deep(h3) {
  font-size: 1.02rem;
}

.feedback-rich :deep(p) {
  margin: 0.45em 0;
}

.feedback-rich :deep(ul),
.feedback-rich :deep(ol) {
  margin: 0.35em 0 0.5em 1.25em;
  padding: 0;
}

.feedback-rich :deep(li) {
  margin: 0.2em 0;
}

.feedback-rich :deep(blockquote) {
  margin: 0.5em 0;
  padding: 0.35em 0.75em;
  border-left: 3px solid #cbd5e1;
  background: #f8fafc;
  color: #475569;
}

.feedback-rich :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  font-size: 0.9em;
  padding: 0.1em 0.35em;
  border-radius: 4px;
  background: #f1f5f9;
  color: #0f172a;
}

.feedback-rich :deep(pre) {
  margin: 0.5em 0;
  padding: 0.65em 0.85em;
  border-radius: 8px;
  background: #0f172a;
  color: #e2e8f0;
  overflow-x: auto;
}

.feedback-rich :deep(pre code) {
  background: transparent;
  color: inherit;
  padding: 0;
}

.feedback-rich :deep(a) {
  color: #2563eb;
  text-decoration: none;
}
.feedback-rich :deep(a:hover) {
  text-decoration: underline;
}

.feedback-rich :deep(.katex-display) {
  margin: 0.65em 0;
  overflow-x: auto;
}

.feedback-rich__empty {
  margin: 0;
  color: #94a3b8;
  font-size: 13px;
}
</style>
