<template>
  <div class="md-latex-live-demo" :class="{ 'md-latex-live-demo--compact': compact }">
    <div class="md-latex-live-demo__head">
      <span class="md-latex-live-demo__title">{{ title }}</span>
      <div class="md-latex-live-demo__actions">
        <el-button size="small" @click="copySource">{{ copied ? '已复制源码' : '复制示例源码' }}</el-button>
        <el-button v-if="showInsert" size="small" type="primary" link @click="emitInsert">
          插入到编辑区
        </el-button>
      </div>
    </div>
    <p class="md-latex-live-demo__sub">{{ subtitle }}</p>
    <div class="md-latex-live-demo__sections">
      <div class="md-latex-live-demo__section">
        <div class="md-latex-live-demo__section-head">
          <span>基础示例</span>
        </div>
        <div class="md-latex-live-demo__render" data-testid="markdown-latex-demo-base-render">
          <RichMarkdownDisplay :markdown="MARKDOWN_BASE_EXAMPLE_MARKDOWN" variant="student" empty-text="" />
        </div>
      </div>
      <div class="md-latex-live-demo__section">
        <div class="md-latex-live-demo__section-head">
          <span>卡片示例</span>
          <el-button
            v-if="showCardSectionToggle"
            size="small"
            link
            data-testid="markdown-latex-demo-card-toggle"
            @click="showCards = !showCards"
          >
            {{ showCards ? '收起卡片示例' : '显示卡片示例' }}
          </el-button>
        </div>
        <div v-if="showCards" class="md-latex-live-demo__render" data-testid="markdown-latex-demo-card-render">
          <RichMarkdownDisplay :markdown="MARKDOWN_CARD_EXAMPLE_MARKDOWN" variant="student" empty-text="" />
        </div>
      </div>
      <div class="md-latex-live-demo__section">
        <div class="md-latex-live-demo__section-head">
          <span>插图示例</span>
          <el-button
            v-if="showImageSectionToggle"
            size="small"
            link
            data-testid="markdown-latex-demo-image-toggle"
            @click="showImage = !showImage"
          >
            {{ showImage ? '收起插图示例' : '显示插图示例' }}
          </el-button>
        </div>
        <div v-if="showImage" class="md-latex-live-demo__render" data-testid="markdown-latex-demo-image-render">
          <RichMarkdownDisplay :markdown="MARKDOWN_IMAGE_EXAMPLE_MARKDOWN" variant="student" empty-text="" />
        </div>
      </div>
    </div>
    <el-collapse v-if="showSourceCollapse" class="md-latex-live-demo__collapse">
      <el-collapse-item title="查看示例 Markdown 源码" name="src">
        <pre class="md-latex-live-demo__pre">{{ MARKDOWN_LATEX_EXAMPLE_MARKDOWN }}</pre>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

import RichMarkdownDisplay from '@/components/RichMarkdownDisplay.vue'
import { copyText } from '@/utils/clipboard'
import {
  MARKDOWN_BASE_EXAMPLE_MARKDOWN,
  MARKDOWN_CARD_EXAMPLE_MARKDOWN,
  MARKDOWN_IMAGE_EXAMPLE_MARKDOWN,
  MARKDOWN_LATEX_EXAMPLE_MARKDOWN
} from '@/utils/markdownLatexDemo'

defineProps({
  /** Smaller typography / padding for discussion composer etc. */
  compact: { type: Boolean, default: false },
  showInsert: { type: Boolean, default: false },
  showCardSectionToggle: { type: Boolean, default: true },
  showImageSectionToggle: { type: Boolean, default: true },
  showSourceCollapse: { type: Boolean, default: true },
  title: {
    type: String,
    default: 'LaTeX 渲染示例（固定演示）'
  },
  subtitle: {
    type: String,
    default:
      '选择「Markdown」格式时始终显示本区：下图即为发布后的阅读效果。请使用 \\(…\\)、$…$、$$…$$ 或 \\[…\\]，勿用 [ … ] 冒充公式。'
  }
})

const emit = defineEmits(['insert'])

const copied = ref(false)
const showCards = ref(false)
const showImage = ref(false)

const emitInsert = () => {
  emit('insert', MARKDOWN_LATEX_EXAMPLE_MARKDOWN)
}

const copySource = async () => {
  try {
    if (!(await copyText(MARKDOWN_LATEX_EXAMPLE_MARKDOWN))) {
      throw new Error('copy failed')
    }
    copied.value = true
    ElMessage.success('示例 Markdown 已复制')
    setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch {
    ElMessage.warning('复制失败：请手动展开「查看示例 Markdown 源码」选择文本')
  }
}
</script>

<style scoped>
.md-latex-live-demo {
  margin: 0;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px dashed #cbd5e1;
  background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
}

.md-latex-live-demo--compact {
  padding: 8px 10px;
}

.md-latex-live-demo__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.md-latex-live-demo__title {
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
}

.md-latex-live-demo__actions {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 6px;
}

.md-latex-live-demo__sub {
  margin: 0 0 8px;
  font-size: 12px;
  color: #64748b;
  line-height: 1.55;
}

.md-latex-live-demo__sections {
  display: grid;
  gap: 10px;
}

.md-latex-live-demo__section {
  display: grid;
  gap: 8px;
}

.md-latex-live-demo__section-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  font-weight: 700;
  color: #0f172a;
}

.md-latex-live-demo__render {
  padding: 10px 12px;
  border-radius: 8px;
  background: #fff;
  border: 1px solid #e2e8f0;
}

.md-latex-live-demo--compact .md-latex-live-demo__render {
  padding: 8px 10px;
}

.md-latex-live-demo__collapse {
  margin-top: 10px;
}

.md-latex-live-demo__pre {
  margin: 0;
  padding: 10px;
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 6px;
  max-height: 220px;
  overflow: auto;
}
</style>
