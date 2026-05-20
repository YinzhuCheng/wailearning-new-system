export const MATERIAL_PRESENTATION_STORAGE_KEY = 'wa_material_presentation_style'
export const MATERIAL_PRESENTATION_EVENT = 'wa-material-presentation-style'

export const MATERIAL_PRESENTATION_OPTIONS = [
  { value: 'academic', label: '教材感', description: '更像纸质教材，目录和正文更有层次。' },
  { value: 'reader', label: '专注阅读', description: '弱化管理感，强调正文与阅读连续性。' },
  { value: 'compact', label: '紧凑管理', description: '信息更密集，适合整理资料与快速操作。' }
]

export function normalizeMaterialPresentationStyle(value) {
  return MATERIAL_PRESENTATION_OPTIONS.some(option => option.value === value) ? value : 'academic'
}

export function getMaterialPresentationStyle() {
  return normalizeMaterialPresentationStyle(localStorage.getItem(MATERIAL_PRESENTATION_STORAGE_KEY) || 'academic')
}

export function setMaterialPresentationStyle(value) {
  const normalized = normalizeMaterialPresentationStyle(value)
  localStorage.setItem(MATERIAL_PRESENTATION_STORAGE_KEY, normalized)
  window.dispatchEvent(new CustomEvent(MATERIAL_PRESENTATION_EVENT, { detail: normalized }))
  return normalized
}
