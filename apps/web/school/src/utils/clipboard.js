export function copyWithTextareaFallback(text, doc = globalThis.document) {
  if (!doc?.body?.appendChild || typeof doc.createElement !== 'function') {
    return false
  }
  const textarea = doc.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.top = '-1000px'
  textarea.style.left = '-1000px'
  textarea.style.opacity = '0'
  doc.body.appendChild(textarea)
  textarea.focus()
  textarea.select()
  textarea.setSelectionRange(0, textarea.value.length)
  let ok = false
  try {
    ok = Boolean(doc.execCommand?.('copy'))
  } catch {
    ok = false
  } finally {
    doc.body.removeChild(textarea)
  }
  return ok
}

export async function copyText(text, options = {}) {
  const nav = options.navigatorObject ?? globalThis.navigator
  const doc = options.documentObject ?? globalThis.document
  if (nav?.clipboard?.writeText) {
    try {
      await nav.clipboard.writeText(text)
      return true
    } catch {
      // Fall through to the legacy DOM copy path.
    }
  }
  return copyWithTextareaFallback(text, doc)
}
