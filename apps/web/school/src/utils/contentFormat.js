/** Align with backend `normalize_content_format`: unknown → markdown. */
export const normalizeContentFormat = value => {
  const v = String(value || '')
    .trim()
    .toLowerCase()
  return v === 'plain' ? 'plain' : 'markdown'
}

export const isMarkdownFormat = fmt => normalizeContentFormat(fmt) === 'markdown'
