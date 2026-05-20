<template>
  <el-card class="appearance-panel block-card" shadow="never">
    <template #header>
      <div class="appearance-panel__header">
        <span>外观风格</span>
        <el-tag v-if="usingSystemDefault" type="info" size="small">跟随全站默认</el-tag>
        <el-tag v-else type="success" size="small">个人风格</el-tag>
      </div>
    </template>

    <div v-loading="loading" class="appearance-panel__body">
      <section class="style-section">
        <div class="style-section__head">
          <div>
            <h3>官方预设</h3>
            <p>预设只是推荐组合，你可以在下方继续调整并保存为自己的命名风格。</p>
          </div>
          <el-button :loading="saving" @click="useSystemDefault">跟随全站默认</el-button>
        </div>

        <div class="preset-grid">
          <button
            v-for="preset in presets"
            :key="preset.key"
            type="button"
            class="preset-card"
            :class="{ 'preset-card--active': activePresetKey === preset.key }"
            :data-testid="`appearance-preset-${preset.key}`"
            @click="applyPreset(preset)"
          >
            <span class="preset-card__swatches">
              <i :style="{ background: colorFor(preset.config.primary, 600) }" />
              <i :style="{ background: colorFor(preset.config.accent, 600) }" />
            </span>
            <strong>{{ preset.name }}</strong>
            <small>{{ preset.description }}</small>
          </button>
        </div>
      </section>

      <section class="style-section">
        <div class="style-section__head">
          <div>
            <h3>自定义组合</h3>
            <p>颜色、字体、字号、透明度、阴影和界面圆润度会立即预览；保存后可命名并再次选择。</p>
          </div>
          <el-input
            v-model="styleName"
            class="style-name-input"
            maxlength="80"
            placeholder="风格名称"
            data-testid="appearance-style-name"
          />
        </div>

        <div class="control-grid">
          <label class="control-field">
            <span>主色</span>
            <el-select v-model="draft.primary" data-testid="appearance-primary">
              <el-option v-for="item in colorOptions" :key="item.value" :label="item.label" :value="item.value">
                <span class="option-swatch" :style="{ background: colorFor(item.value, 600) }" />
                {{ item.label }}
              </el-option>
            </el-select>
          </label>

          <label class="control-field">
            <span>辅助色</span>
            <el-select v-model="draft.accent" data-testid="appearance-accent">
              <el-option v-for="item in colorOptions" :key="item.value" :label="item.label" :value="item.value">
                <span class="option-swatch" :style="{ background: colorFor(item.value, 600) }" />
                {{ item.label }}
              </el-option>
            </el-select>
          </label>

          <label class="control-field">
            <span>字体</span>
            <el-select v-model="draft.font_family" data-testid="appearance-font-family">
              <el-option v-for="item in fontFamilyOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </label>

          <label class="control-field">
            <span>字号</span>
            <el-segmented v-model="draft.font_scale" :options="fontScaleOptions" data-testid="appearance-font-scale" />
          </label>

          <label class="control-field">
            <span>阴影</span>
            <el-segmented v-model="draft.shadow" :options="shadowOptions" data-testid="appearance-shadow" />
          </label>

          <label class="control-field">
            <span>透明度</span>
            <el-segmented v-model="draft.transparency" :options="transparencyOptions" data-testid="appearance-transparency" />
          </label>

          <label class="control-field">
            <span>界面圆润度</span>
            <el-segmented v-model="draft.radius" :options="radiusOptions" data-testid="appearance-radius" />
          </label>

          <label class="control-field">
            <span>密度</span>
            <el-segmented v-model="draft.density" :options="densityOptions" data-testid="appearance-density" />
          </label>
        </div>

        <div class="preview-surface">
          <div class="preview-shell" :style="previewStyle">
            <div class="preview-sidebar">
              <span />
              <span />
              <span class="is-active" />
            </div>
            <div class="preview-main">
              <div class="preview-toolbar">
                <strong>Dashboard</strong>
                <button type="button">Action</button>
              </div>
              <div class="preview-cards">
                <article>
                  <b>92%</b>
                  <span>Completion</span>
                </article>
                <article>
                  <b>18</b>
                  <span>Courses</span>
                </article>
              </div>
              <div class="preview-table">
                <span />
                <span />
                <span />
              </div>
            </div>
          </div>
        </div>

        <div class="style-actions">
          <el-button type="primary" :loading="saving" data-testid="appearance-save-style" @click="saveStyle">
            保存并使用
          </el-button>
          <el-button :loading="saving" data-testid="appearance-apply-unsaved" @click="applyUnsaved">
            仅本次预览
          </el-button>
        </div>
      </section>

      <section class="style-section">
        <div class="style-section__head">
          <div>
            <h3>我的风格</h3>
            <p>保存过的风格只属于当前账号，可随时选择、覆盖或删除。</p>
          </div>
        </div>

        <div v-if="savedStyles.length" class="saved-list">
          <div v-for="style in savedStyles" :key="style.id" class="saved-item">
            <div class="saved-item__meta">
              <strong>{{ style.name }}</strong>
              <span>{{ describeConfig(style.config) }}</span>
            </div>
            <div class="saved-item__actions">
              <el-button size="small" type="primary" :disabled="style.is_selected" @click="selectStyle(style)">
                使用
              </el-button>
              <el-button size="small" @click="loadStyle(style)">载入</el-button>
              <el-button size="small" type="danger" plain @click="deleteStyle(style)">删除</el-button>
            </div>
          </div>
        </div>
        <el-empty v-else description="还没有保存的个人风格" :image-size="72" />
      </section>
    </div>
  </el-card>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import api from '@/api'
import { applyAppearanceStyle, appearancePresets, normalizeAppearanceConfig } from '@/utils/theme'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()

const colorOptions = [
  { value: 'blue', label: 'Blue' },
  { value: 'green', label: 'Green' },
  { value: 'amber', label: 'Amber' },
  { value: 'gray', label: 'Gray' },
  { value: 'navy', label: 'Navy' },
  { value: 'slate', label: 'Slate' },
  { value: 'cyan', label: 'Cyan' },
  { value: 'teal', label: 'Teal' },
  { value: 'violet', label: 'Violet' },
  { value: 'red', label: 'Red' }
]

const colorMap = {
  blue: { 600: '#2563eb', 50: '#eff6ff' },
  green: { 600: '#059669', 50: '#ecfdf5' },
  amber: { 600: '#d97706', 50: '#fffbeb' },
  gray: { 600: '#475569', 50: '#f8fafc' },
  navy: { 600: '#1d4ed8', 50: '#eff6ff' },
  slate: { 600: '#334155', 50: '#f8fafc' },
  cyan: { 600: '#0891b2', 50: '#ecfeff' },
  teal: { 600: '#0d9488', 50: '#f0fdfa' },
  violet: { 600: '#7c3aed', 50: '#f5f3ff' },
  red: { 600: '#dc2626', 50: '#fef2f2' }
}

const fontFamilyOptions = [
  { value: 'system', label: '系统默认' },
  { value: 'song', label: '宋体' },
  { value: 'hei', label: '黑体 / 雅黑' },
  { value: 'kai', label: '楷体' },
  { value: 'mono', label: '等宽' }
]
const fontScaleOptions = [
  { label: '小', value: 'small' },
  { label: '中', value: 'medium' },
  { label: '大', value: 'large' }
]
const shadowOptions = [
  { label: 'Flat', value: 'flat' },
  { label: 'Soft', value: 'soft' },
  { label: 'Medium', value: 'medium' },
  { label: 'Strong', value: 'strong' }
]
const transparencyOptions = [
  { label: 'Solid', value: 'solid' },
  { label: 'Balanced', value: 'balanced' },
  { label: 'Glass', value: 'glass' }
]
const radiusOptions = [
  { label: 'Square', value: 'square' },
  { label: 'Subtle', value: 'subtle' },
  { label: 'Balanced', value: 'balanced' },
  { label: 'Soft', value: 'soft' }
]
const densityOptions = [
  { label: 'Compact', value: 'compact' },
  { label: 'Comfort', value: 'comfortable' },
  { label: 'Spacious', value: 'spacious' }
]

const presets = ref(appearancePresets)
const loading = ref(false)
const saving = ref(false)
const styleName = ref('')
const draftPresetKey = ref(null)
const draft = reactive(normalizeAppearanceConfig())

const savedStyles = computed(() => userStore.appearanceState?.saved_styles || [])
const usingSystemDefault = computed(() => !userStore.appearanceState?.selected_style)
const activePresetKey = computed(
  () => draftPresetKey.value || userStore.appearanceState?.selected_style?.preset_key || userStore.appearanceState?.system_default_preset
)

const colorFor = (name, step) => colorMap[name]?.[step] || colorMap.blue[step]

const assignDraft = config => {
  Object.assign(draft, normalizeAppearanceConfig(config))
}

const previewStyle = computed(() => ({
  '--preview-primary': colorFor(draft.primary, 600),
  '--preview-primary-soft': colorFor(draft.primary, 50),
  '--preview-accent': colorFor(draft.accent, 600),
  '--preview-accent-soft': colorFor(draft.accent, 50),
  '--preview-radius': draft.radius === 'soft' ? '18px' : draft.radius === 'balanced' ? '12px' : draft.radius === 'subtle' ? '8px' : '3px',
  '--preview-shadow':
    draft.shadow === 'flat'
      ? 'none'
      : draft.shadow === 'strong'
        ? '0 22px 48px rgba(15, 23, 42, 0.18)'
        : draft.shadow === 'medium'
          ? '0 18px 38px rgba(15, 23, 42, 0.13)'
          : '0 12px 30px rgba(15, 23, 42, 0.09)',
  '--preview-alpha': draft.transparency === 'glass' ? '0.72' : draft.transparency === 'balanced' ? '0.88' : '1'
}))

const describeConfig = config => {
  const c = normalizeAppearanceConfig(config)
  return `${c.primary} / ${c.accent} / ${c.font_family} / ${c.font_scale} / ${c.shadow} / ${c.radius}`
}

const refresh = async () => {
  loading.value = true
  try {
    const [presetRows, state] = await Promise.all([api.appearance.listPresets(), userStore.fetchAppearanceState()])
    presets.value = Array.isArray(presetRows) && presetRows.length ? presetRows : appearancePresets
    const selectedConfig = state?.selected_style?.config
    const systemPreset = presets.value.find(item => item.key === state?.system_default_preset)
    draftPresetKey.value = state?.selected_style?.preset_key || systemPreset?.key || null
    assignDraft(selectedConfig || systemPreset?.config || appearancePresets[0].config)
  } finally {
    loading.value = false
  }
}

const applyPreset = preset => {
  assignDraft(preset.config)
  draftPresetKey.value = preset.key
  styleName.value = preset.name
  applyAppearanceStyle(draft)
}

const applyUnsaved = () => {
  applyAppearanceStyle(draft)
  ElMessage.success('已应用到当前页面预览')
}

const useSystemDefault = async () => {
  saving.value = true
  try {
    const state = await api.appearance.useSystem()
    userStore.setAppearanceState(state)
    ElMessage.success('已恢复为全站默认')
  } finally {
    saving.value = false
  }
}

const saveStyle = async () => {
  const name = (styleName.value || '').trim()
  if (!name) {
    ElMessage.warning('请先填写风格名称')
    return
  }

  saving.value = true
  try {
    await api.appearance.createStyle({
      name,
      source: 'custom',
      preset_key: draftPresetKey.value || null,
      config: normalizeAppearanceConfig(draft),
      select_after_save: true
    })
    await refresh()
    ElMessage.success('风格已保存并应用')
  } finally {
    saving.value = false
  }
}

const selectStyle = async style => {
  saving.value = true
  try {
    const state = await api.appearance.selectStyle(style.id)
    userStore.setAppearanceState(state)
    assignDraft(style.config)
    ElMessage.success('已应用个人风格')
  } finally {
    saving.value = false
  }
}

const loadStyle = style => {
  styleName.value = style.name
  draftPresetKey.value = style.preset_key || null
  assignDraft(style.config)
  applyAppearanceStyle(draft)
}

const deleteStyle = async style => {
  await ElMessageBox.confirm(`确定删除风格「${style.name}」？`, '删除风格', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消'
  })
  await api.appearance.deleteStyle(style.id)
  await refresh()
  ElMessage.success('已删除')
}

watch(
  draft,
  () => {
    applyAppearanceStyle(draft)
  },
  { deep: true }
)

onMounted(refresh)
</script>

<style scoped>
.appearance-panel {
  margin-bottom: 20px;
}

.appearance-panel__header,
.style-section__head,
.saved-item,
.saved-item__actions {
  display: flex;
  align-items: center;
}

.appearance-panel__header,
.style-section__head {
  justify-content: center;
  flex-direction: column;
  gap: 16px;
  text-align: center;
}

.appearance-panel__body {
  display: grid;
  gap: 24px;
}

.style-section {
  display: grid;
  gap: 16px;
}

.style-section__head h3 {
  margin: 0 0 4px;
  font-size: var(--wa-font-size-lg);
  color: var(--wa-color-text);
}

.style-section__head p {
  margin: 0;
  color: var(--wa-color-text-muted);
  font-size: var(--wa-font-size-sm);
  line-height: 1.6;
}

.style-name-input {
  width: min(260px, 100%);
  margin: 0 auto;
}

.preset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}

.preset-card {
  display: grid;
  min-height: 128px;
  gap: 8px;
  padding: 14px;
  border: 1px solid var(--wa-border-subtle);
  border-radius: var(--wa-radius-lg);
  background: var(--wa-color-surface);
  color: var(--wa-color-text);
  text-align: center;
  box-shadow: var(--wa-shadow-surface);
  cursor: pointer;
  justify-items: center;
}

.preset-card--active {
  border-color: var(--wa-color-primary-500);
  box-shadow: var(--wa-focus-ring);
}

.preset-card__swatches {
  display: flex;
  gap: 6px;
  justify-content: center;
}

.preset-card__swatches i,
.option-swatch {
  display: inline-block;
  width: 18px;
  height: 18px;
  border-radius: 50%;
}

.preset-card small {
  color: var(--wa-color-text-muted);
  line-height: 1.45;
}

.control-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  max-width: 920px;
  margin: 0 auto;
}

.control-field {
  display: grid;
  gap: 8px;
  min-width: 0;
  justify-items: center;
  text-align: center;
}

.control-field > span {
  color: var(--wa-color-text-soft);
  font-size: var(--wa-font-size-sm);
}

.control-field :deep(.el-select),
.control-field :deep(.el-segmented) {
  width: 100%;
}

.option-swatch {
  margin-right: 8px;
  vertical-align: text-bottom;
}

.preview-surface {
  overflow: hidden;
  border: 1px solid var(--wa-border-subtle);
  border-radius: var(--wa-radius-lg);
  background: var(--wa-color-bg-soft);
  padding: 12px;
  max-width: 920px;
  margin: 0 auto;
}

.preview-shell {
  display: grid;
  grid-template-columns: 72px 1fr;
  min-height: 220px;
  overflow: hidden;
  border-radius: var(--preview-radius);
  background: color-mix(in srgb, var(--preview-primary-soft) 65%, white);
  box-shadow: var(--preview-shadow);
}

.preview-sidebar {
  display: grid;
  align-content: start;
  gap: 12px;
  padding: 18px 14px;
  background: linear-gradient(180deg, #0f172a, color-mix(in srgb, var(--preview-primary) 35%, #0f172a));
}

.preview-sidebar span {
  height: 26px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.22);
}

.preview-sidebar .is-active {
  background: var(--preview-primary);
}

.preview-main {
  display: grid;
  align-content: start;
  gap: 14px;
  padding: 18px;
}

.preview-toolbar,
.preview-cards article,
.preview-table {
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: calc(var(--preview-radius) * 0.75);
  background: rgba(255, 255, 255, var(--preview-alpha));
}

.preview-toolbar {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 12px;
  text-align: center;
}

.preview-toolbar button {
  border: 0;
  border-radius: 8px;
  background: var(--preview-primary);
  color: white;
  padding: 7px 12px;
}

.preview-cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.preview-cards article {
  display: grid;
  gap: 4px;
  padding: 14px;
}

.preview-cards b {
  color: var(--preview-primary);
  font-size: var(--wa-font-size-xl);
}

.preview-cards span {
  color: #64748b;
}

.preview-table {
  display: grid;
  gap: 8px;
  padding: 12px;
}

.preview-table span {
  height: 10px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--preview-accent) 22%, #e2e8f0);
}

.style-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
}

.saved-list {
  display: grid;
  gap: 10px;
}

.saved-item {
  justify-content: center;
  flex-direction: column;
  gap: 12px;
  border: 1px solid var(--wa-border-subtle);
  border-radius: var(--wa-radius-lg);
  padding: 12px;
  text-align: center;
}

.saved-item__meta {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.saved-item__meta span {
  color: var(--wa-color-text-muted);
  font-size: var(--wa-font-size-xs);
  overflow-wrap: anywhere;
}

.saved-item__actions {
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}

@media (max-width: 768px) {
  .appearance-panel__header,
  .style-section__head,
  .saved-item {
    align-items: stretch;
    flex-direction: column;
  }

  .control-grid,
  .preview-cards {
    grid-template-columns: 1fr;
  }

  .preview-shell {
    grid-template-columns: 48px 1fr;
  }

  .saved-item__actions {
    justify-content: center;
  }
}
</style>
