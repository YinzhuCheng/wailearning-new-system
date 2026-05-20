<template>
  <div
    ref="rootRef"
    class="rich-md"
    :class="variant === 'teacher' ? 'rich-md--teacher' : 'rich-md--student'"
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
  markdown: { type: String, default: '' },
  variant: { type: String, default: 'student' },
  emptyText: { type: String, default: '暂无内容' }
})

const rootRef = ref(null)
const md = createCourseMarkdownIt()

const renderedHtml = computed(() => {
  const raw = (props.markdown || '').trim()
  if (!raw) {
    return `<p class="rich-md__empty">${escapeHtml(props.emptyText)}</p>`
  }
  return renderCourseMarkdown(md, raw)
})

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

const applyMath = () => {
  const el = rootRef.value
  if (!el) return
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
    /* ignore */
  }
}

onMounted(async () => {
  await nextTick()
  applyMath()
})

watch(
  () => props.markdown,
  async () => {
    await nextTick()
    applyMath()
  },
  { flush: 'post' }
)
</script>

<style scoped>
.rich-md {
  font-size: 14px;
  line-height: 1.65;
  word-break: break-word;
}

.rich-md--student {
  color: #334155;
}

.rich-md--teacher {
  color: #1e293b;
  font-size: 13px;
  line-height: 1.6;
}

.rich-md :deep(h1),
.rich-md :deep(h2),
.rich-md :deep(h3) {
  margin: 0.75em 0 0.35em;
  font-weight: 600;
  color: #0f172a;
}

.rich-md :deep(h1) {
  font-size: 1.15rem;
}
.rich-md :deep(h2) {
  font-size: 1.08rem;
}
.rich-md :deep(h3) {
  font-size: 1.02rem;
}

.rich-md :deep(p) {
  margin: 0.45em 0;
}

.rich-md :deep(ul),
.rich-md :deep(ol) {
  margin: 0.35em 0 0.5em 1.25em;
  padding: 0;
}

.rich-md :deep(li) {
  margin: 0.2em 0;
}

.rich-md :deep(blockquote) {
  margin: 0.5em 0;
  padding: 0.35em 0.75em;
  border-left: 3px solid #cbd5e1;
  background: #f8fafc;
  color: #475569;
}

.rich-md :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  font-size: 0.9em;
  padding: 0.1em 0.35em;
  border-radius: 4px;
  background: #f1f5f9;
  color: #0f172a;
}

.rich-md :deep(pre) {
  margin: 0.5em 0;
  padding: 0.65em 0.85em;
  border-radius: 8px;
  background: #0f172a;
  color: #e2e8f0;
  overflow-x: auto;
}

.rich-md :deep(pre code) {
  background: transparent;
  color: inherit;
  padding: 0;
}

.rich-md :deep(a) {
  color: #2563eb;
  text-decoration: none;
}
.rich-md :deep(a:hover) {
  text-decoration: underline;
}

.rich-md :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: 6px;
  margin: 0.35em 0;
  vertical-align: middle;
}

.rich-md :deep(.katex-display) {
  margin: 0.65em 0;
  overflow-x: auto;
}

.rich-md :deep(.md-card) {
  --md-card-bg: #f8fafc;
  --md-card-border: #dbe4ee;
  --md-card-accent: #94a3b8;
  margin: 0.8em 0;
  padding: 0.85em 1em;
  border: 1px solid var(--md-card-border);
  border-radius: 12px;
  background: var(--md-card-bg);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.55);
}

.rich-md :deep(.md-card--titled) {
  padding-top: 0.8em;
}

.rich-md :deep(.md-card__title) {
  margin: 0 0 0.55em;
  font-size: 0.95em;
  font-weight: 700;
  color: #0f172a;
  display: flex;
  align-items: center;
  gap: 0.5em;
}

.rich-md :deep(.md-card__title::before) {
  content: '';
  width: 0.55em;
  height: 0.55em;
  border-radius: 999px;
  background: var(--md-card-accent);
  flex: 0 0 auto;
}

.rich-md :deep(.md-card > :first-child) {
  margin-top: 0;
}

.rich-md :deep(.md-card > :last-child) {
  margin-bottom: 0;
}

.rich-md :deep(.md-card ul),
.rich-md :deep(.md-card ol) {
  margin-bottom: 0.2em;
}

.rich-md :deep(.md-card--example) {
  --md-card-bg: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
  --md-card-border: #dbe4ee;
  --md-card-accent: #64748b;
}

.rich-md :deep(.md-card--pricing) {
  --md-card-bg: linear-gradient(180deg, #f7f8fb 0%, #eef2f7 100%);
  --md-card-border: #d3dae6;
  --md-card-accent: #475569;
}

.rich-md :deep(.md-card--note) {
  --md-card-bg: linear-gradient(180deg, #f5f9ff 0%, #edf5ff 100%);
  --md-card-border: #cfe0ff;
  --md-card-accent: #3b82f6;
}

.rich-md :deep(.md-card--tip) {
  --md-card-bg: linear-gradient(180deg, #f2fbf5 0%, #e7f8ec 100%);
  --md-card-border: #c5ead0;
  --md-card-accent: #16a34a;
}

.rich-md :deep(.md-card--warning) {
  --md-card-bg: linear-gradient(180deg, #fff9ec 0%, #fff2cc 100%);
  --md-card-border: #f2d38a;
  --md-card-accent: #d97706;
}

.rich-md :deep(.md-card--danger) {
  --md-card-bg: linear-gradient(180deg, #fff4f4 0%, #ffe7e7 100%);
  --md-card-border: #f4b4b4;
  --md-card-accent: #dc2626;
}

.rich-md__empty {
  margin: 0;
  color: #94a3b8;
  font-size: 13px;
}
</style>
