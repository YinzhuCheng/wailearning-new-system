<template>
  <div class="md-panel">
    <div v-if="isMarkdown" class="md-panel__toolbar">
      <el-button size="small" :disabled="disabled" @click="insertHeading('## ')">标题</el-button>
      <el-button size="small" :disabled="disabled" @click="insertBold">加粗</el-button>
      <el-button size="small" :disabled="disabled" @click="insertList">列表</el-button>
      <el-button size="small" :disabled="disabled" @click="insertCode">代码</el-button>
      <el-button size="small" :disabled="disabled" @click="insertInlineMath">行内公式</el-button>
      <el-button size="small" :disabled="disabled" @click="insertDisplayMath">独立公式</el-button>
      <el-upload
        v-if="enableImageUpload"
        class="md-panel__upload"
        :auto-upload="false"
        :show-file-list="false"
        accept="image/*,.jpg,.jpeg,.png,.gif,.webp,.bmp"
        :disabled="disabled"
        :on-change="onImagePick"
      >
        <el-button size="small" :loading="uploading" :disabled="disabled">上传图片</el-button>
      </el-upload>
      <el-button size="small" :disabled="disabled" @click="promptImageUrl">图片链接</el-button>
    </div>
    <p v-if="isMarkdown" class="md-panel__katex-hint">
      公式与预览：行内可写
      <code>\\( ... \\)</code>
      、
      <code>$...$</code>
      ；独立一行可写
      <code>$$ ... $$</code>
      或
      <code>\\[ ... \\]</code>
      。下方先展示固定示例渲染，再展示您在编辑区输入的内容；保存后与资料/作业阅读页一致。
    </p>
    <div v-if="isMarkdown" class="md-panel__help-toggles">
      <el-button size="small" link data-testid="md-panel-card-help-toggle" @click="showCardHelp = !showCardHelp">
        {{ showCardHelp ? '隐藏卡片与配色示例' : '查看卡片与配色示例' }}
      </el-button>
      <el-button size="small" link data-testid="md-panel-image-help-toggle" @click="showImageHelp = !showImageHelp">
        {{ showImageHelp ? '隐藏插图说明' : '查看当前支持的插图' }}
      </el-button>
    </div>
    <MarkdownLatexLiveDemo
      v-if="isMarkdown && showCardHelp"
      :show-insert="true"
      :show-card-section-toggle="true"
      :show-image-section-toggle="true"
      :show-source-collapse="!compactDemo"
      :compact="compactDemo"
      class="md-panel__demo"
      title="卡片 / Markdown / LaTeX 示例"
      subtitle="这里先展示基础 Markdown 和公式；卡片、插图示例按需展开。"
      @insert="insertExampleBlock"
    />
    <div v-if="isMarkdown && showImageHelp" class="md-panel__image-help" data-testid="md-panel-image-help">
      <div class="md-panel__image-help-title">当前系统支持的插图方式</div>
      <ul class="md-panel__image-help-list">
        <li v-if="enableImageUpload">本地上传图片：JPG、JPEG、PNG、GIF、WebP、BMP</li>
        <li>远程图片 URL：`![说明](https://...)`</li>
        <li>受控内置图片：可按需插入系统示例图，便于快速排版预览</li>
      </ul>
      <div class="md-panel__image-help-actions">
        <el-button size="small" :disabled="disabled" @click="insertImageTemplate">插入图片模板</el-button>
        <el-button size="small" type="primary" plain :disabled="disabled" @click="insertSampleImage">
          插入示例图
        </el-button>
      </div>
    </div>
    <el-input
      ref="inputRef"
      :model-value="modelValue"
      type="textarea"
      :autosize="{ minRows, maxRows }"
      :placeholder="effectivePlaceholder"
      :disabled="disabled"
      class="md-panel__input"
      :data-testid="dataTestid || undefined"
      @update:model-value="v => $emit('update:modelValue', v)"
    />
    <div v-if="hint" class="md-panel__hint">{{ hint }}</div>
    <div v-if="showFormatToggle" class="md-panel__format">
      <span class="md-panel__format-label">正文格式</span>
      <el-radio-group
        :model-value="contentFormat"
        size="small"
        :disabled="disabled"
        @update:model-value="onContentFormatChange"
      >
        <el-radio-button label="markdown">Markdown</el-radio-button>
        <el-radio-button label="plain">纯文本</el-radio-button>
      </el-radio-group>
      <span v-if="contentFormat === 'plain'" class="md-panel__format-note">
        纯文本不会解析 *、# 等符号为排版；换行将原样保留。
      </span>
    </div>
    <template v-if="isMarkdown">
      <div class="md-panel__preview-label">您的内容预览</div>
      <div class="md-panel__preview">
        <RichMarkdownDisplay :markdown="modelValue" variant="student" empty-text="（空）" />
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import api from '@/api'
import MarkdownLatexLiveDemo from '@/components/MarkdownLatexLiveDemo.vue'
import RichMarkdownDisplay from '@/components/RichMarkdownDisplay.vue'
import { MARKDOWN_IMAGE_EXAMPLE_MARKDOWN } from '@/utils/markdownLatexDemo'
import { validateAttachmentFile } from '@/utils/attachments'

const props = defineProps({
  modelValue: { type: String, default: '' },
  /** `markdown` | `plain` — plain disables MD preview and toolbar. */
  contentFormat: { type: String, default: 'markdown' },
  placeholder: { type: String, default: '' },
  hint: { type: String, default: '' },
  minRows: { type: Number, default: 6 },
  maxRows: { type: Number, default: 22 },
  enableImageUpload: { type: Boolean, default: true },
  showFormatToggle: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  /** Optional for E2E / automation */
  dataTestid: { type: String, default: '' },
  /** Tighter demo panel (dialogs with multiple Markdown fields). */
  compactDemo: { type: Boolean, default: false }
})

const emit = defineEmits(['update:modelValue', 'update:contentFormat'])

const inputRef = ref(null)
const uploading = ref(false)
const showCardHelp = ref(false)
const showImageHelp = ref(false)

const isMarkdown = computed(() => (props.contentFormat || 'markdown') === 'markdown')

const effectivePlaceholder = computed(() => {
  if (!isMarkdown.value) {
    return props.placeholder || '输入正文（纯文本）'
  }
  return props.placeholder || ''
})

const getTextarea = () => inputRef.value?.textarea

const emitUpdate = v => emit('update:modelValue', v)

const insertAtCursor = snippet => {
  const ta = getTextarea()
  const cur = props.modelValue || ''
  if (!ta || typeof ta.selectionStart !== 'number') {
    emitUpdate((cur || '') + snippet)
    return
  }
  const start = ta.selectionStart
  const end = ta.selectionEnd
  const next = cur.slice(0, start) + snippet + cur.slice(end)
  emitUpdate(next)
  const pos = start + snippet.length
  queueMicrotask(() => {
    const t2 = getTextarea()
    if (t2) {
      t2.focus()
      t2.selectionStart = t2.selectionEnd = pos
    }
  })
}

const insertExampleBlock = snippet => {
  const cur = props.modelValue || ''
  const sep = cur.trim() ? '\n\n' : ''
  emitUpdate(`${cur}${sep}${snippet}`)
}

const insertHeading = prefix => insertAtCursor(`\n${prefix}`)
const insertBold = () => insertAtCursor('**加粗**')
const insertList = () => insertAtCursor('\n- 条目\n')
const insertCode = () => insertAtCursor('\n```\n代码\n```\n')
const insertInlineMath = () => insertAtCursor('\\( x \\)')
const insertDisplayMath = () => insertAtCursor('\n$$\n\n$$\n')
const insertImageTemplate = () => insertAtCursor('\n![图片说明](https://example.com/your-image.png)\n')
const insertSampleImage = () => insertAtCursor(`\n${MARKDOWN_IMAGE_EXAMPLE_MARKDOWN}\n`)

const onImagePick = async uploadFile => {
  const file = uploadFile.raw
  const result = validateAttachmentFile(file, { imageOnly: true })
  if (!result.valid) {
    ElMessage.error(result.message)
    return false
  }
  uploading.value = true
  try {
    const uploaded = await api.files.upload(file)
    const url = uploaded?.attachment_url || ''
    if (!url) {
      ElMessage.error('上传失败')
      return false
    }
    const name = (file.name || 'image').replace(/]/g, '')
    insertAtCursor(`\n![${name}](${url})\n`)
    ElMessage.success('已插入图片')
  } catch (e) {
    console.error(e)
  } finally {
    uploading.value = false
  }
  return false
}

const promptImageUrl = async () => {
  try {
    const { value } = await ElMessageBox.prompt('请输入图片 URL（https 推荐）', '插入图片链接', {
      confirmButtonText: '插入',
      cancelButtonText: '取消',
      inputPlaceholder: 'https://...'
    })
    const url = (value || '').trim()
    if (!url) {
      return
    }
    insertAtCursor(`\n![](${url})\n`)
  } catch {
    /* cancel */
  }
}

const onContentFormatChange = v => {
  const next = v === 'plain' ? 'plain' : 'markdown'
  if (next === 'plain' && (props.modelValue || '').trim()) {
    ElMessage.info('已切换为纯文本：正文将按字面显示，不再作为 Markdown 解析。')
  }
  emit('update:contentFormat', next)
}
</script>

<style scoped>
.md-panel {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
  overflow: hidden;
}

.md-panel__toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  padding: 8px 10px;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
}

.md-panel__upload {
  display: inline-block;
}

.md-panel__katex-hint {
  margin: 0;
  padding: 6px 10px 0;
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
}

.md-panel__demo {
  margin: 8px 10px 0;
}

.md-panel__help-toggles {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding: 8px 10px 0;
}

.md-panel__image-help {
  margin: 8px 10px 0;
  padding: 10px 12px;
  border: 1px solid #dbe4ee;
  border-radius: 10px;
  background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
}

.md-panel__image-help-title {
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 6px;
}

.md-panel__image-help-list {
  margin: 0 0 8px 18px;
  padding: 0;
  color: #475569;
  font-size: 12px;
  line-height: 1.6;
}

.md-panel__image-help-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.md-panel__katex-hint code {
  font-size: 11px;
  padding: 0.1em 0.35em;
  border-radius: 4px;
  background: #f1f5f9;
  color: #0f172a;
}

.md-panel__input :deep(.el-textarea__inner) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  font-size: 13px;
  border: none;
  box-shadow: none;
  border-radius: 0;
}

.md-panel__hint {
  padding: 6px 12px 0;
  font-size: 12px;
  color: #64748b;
}

.md-panel__format {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 14px;
  padding: 8px 12px;
  border-top: 1px dashed #e2e8f0;
  background: #fafbfc;
}

.md-panel__format-label {
  font-size: 12px;
  font-weight: 600;
  color: #475569;
}

.md-panel__format-note {
  flex: 1 1 220px;
  font-size: 12px;
  color: #64748b;
  line-height: 1.45;
}

.md-panel__preview-label {
  padding: 8px 12px 0;
  font-size: 12px;
  font-weight: 600;
  color: #475569;
}

.md-panel__preview {
  padding: 8px 12px 12px;
  max-height: 280px;
  overflow-y: auto;
  border-top: 1px dashed #e2e8f0;
  margin-top: 6px;
  background: #fafbfc;
}
</style>
