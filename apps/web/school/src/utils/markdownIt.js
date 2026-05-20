import MarkdownIt from 'markdown-it'

const LATEX_DELIMITER_TOKENS = [
  ['\\(', '@@WL_LATEX_INLINE_OPEN@@'],
  ['\\)', '@@WL_LATEX_INLINE_CLOSE@@'],
  ['\\[', '@@WL_LATEX_BLOCK_OPEN@@'],
  ['\\]', '@@WL_LATEX_BLOCK_CLOSE@@']
]

const LATEX_BLOCK_PATTERNS = [
  {
    left: '$$',
    right: '$$',
    pattern: /(^|\n)[ \t]*\$\$[ \t]*\n([\s\S]*?)\n[ \t]*\$\$[ \t]*(?=\n|$)/g
  },
  {
    left: '\\[',
    right: '\\]',
    pattern: /(^|\n)[ \t]*\\\[[ \t]*\n([\s\S]*?)\n[ \t]*\\\][ \t]*(?=\n|$)/g
  }
]

const MARKER_CHAR = 0x3a // :
const CARD_KINDS = new Set(['example', 'pricing', 'note', 'tip', 'warning', 'danger'])

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function blockMathToken(index, source) {
  let token = ''
  do {
    token = `@@WL_LATEX_BLOCK_MATH_${index}_${Math.random().toString(36).slice(2)}@@`
  } while (source.includes(token))
  return token
}

function escapeAttr(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function markdownCardPlugin(md) {
  function cardBlock(state, startLine, endLine, silent) {
    const start = state.bMarks[startLine] + state.tShift[startLine]
    const max = state.eMarks[startLine]
    if (start >= max || state.src.charCodeAt(start) !== MARKER_CHAR) {
      return false
    }

    let markerCount = 0
    while (start + markerCount < max && state.src.charCodeAt(start + markerCount) === MARKER_CHAR) {
      markerCount += 1
    }
    if (markerCount < 3) {
      return false
    }

    const header = state.src.slice(start + markerCount, max).trim()
    const spaceIndex = header.indexOf(' ')
    const kind = (spaceIndex === -1 ? header : header.slice(0, spaceIndex)).trim()
    if (!CARD_KINDS.has(kind)) {
      return false
    }
    const title = spaceIndex === -1 ? '' : header.slice(spaceIndex + 1).trim()

    if (silent) {
      return true
    }

    let nextLine = startLine + 1
    let found = false
    while (nextLine < endLine) {
      const nextStart = state.bMarks[nextLine] + state.tShift[nextLine]
      const nextMax = state.eMarks[nextLine]
      if (nextStart < nextMax && state.src.charCodeAt(nextStart) === MARKER_CHAR) {
        let nextCount = 0
        while (nextStart + nextCount < nextMax && state.src.charCodeAt(nextStart + nextCount) === MARKER_CHAR) {
          nextCount += 1
        }
        const tail = state.src.slice(nextStart + nextCount, nextMax).trim()
        if (nextCount >= markerCount && !tail) {
          found = true
          break
        }
      }
      nextLine += 1
    }

    if (!found) {
      return false
    }

    const open = state.push('wl_card_open', 'section', 1)
    open.block = true
    open.meta = { kind, title }
    open.map = [startLine, nextLine]

    if (title) {
      const titleOpen = state.push('wl_card_title_open', 'div', 1)
      titleOpen.block = true
      titleOpen.meta = { kind }

      const inline = state.push('inline', '', 0)
      inline.content = title
      inline.children = []

      const titleClose = state.push('wl_card_title_close', 'div', -1)
      titleClose.block = true
    }

    state.md.block.parse(state.getLines(startLine + 1, nextLine, state.tShift[startLine], true), md, state.env, state.tokens)

    const close = state.push('wl_card_close', 'section', -1)
    close.block = true
    close.meta = { kind }

    state.line = nextLine + 1
    return true
  }

  md.block.ruler.before('fence', 'wl_card', cardBlock, {
    alt: ['paragraph', 'reference', 'blockquote', 'list']
  })

  md.renderer.rules.wl_card_open = (tokens, idx) => {
    const { kind, title } = tokens[idx].meta || {}
    const classes = `md-card md-card--${escapeAttr(kind || 'note')}${title ? ' md-card--titled' : ''}`
    return `<section class="${classes}" data-card-kind="${escapeAttr(kind || 'note')}">`
  }
  md.renderer.rules.wl_card_close = () => '</section>\n'
  md.renderer.rules.wl_card_title_open = () => '<div class="md-card__title">'
  md.renderer.rules.wl_card_title_close = () => '</div>\n'
}

/** Shared Markdown-it preset for course content and feedback (no raw HTML). */
export function createCourseMarkdownIt() {
  return new MarkdownIt({
    html: false,
    linkify: true,
    breaks: true
  }).use(markdownCardPlugin)
}

/**
 * Preserve KaTeX delimiters that Markdown-it would otherwise treat as markdown escapes.
 *
 * Without this, author input like `\\(x\\)` or `\\[x\\]` is rendered as plain `(x)` / `[x]`
 * before KaTeX auto-render runs, so preview and published discussion bodies cannot detect math.
 */
export function renderCourseMarkdown(md, raw) {
  let prepared = String(raw ?? '').replace(/\r\n?/g, '\n')
  const blockMath = []
  for (const { left, right, pattern } of LATEX_BLOCK_PATTERNS) {
    prepared = prepared.replace(pattern, (match, prefix, body) => {
      const token = blockMathToken(blockMath.length, prepared)
      blockMath.push({ token, left, body, right })
      return `${prefix}${token}`
    })
  }

  for (const [delimiter, token] of LATEX_DELIMITER_TOKENS) {
    prepared = prepared.replaceAll(delimiter, token)
  }

  let html = md.render(prepared)
  for (const [delimiter, token] of LATEX_DELIMITER_TOKENS) {
    html = html.replaceAll(token, delimiter)
  }
  for (const { token, left, body, right } of blockMath) {
    html = html.split(token).join(`${escapeHtml(left)}\n${escapeHtml(body)}\n${escapeHtml(right)}`)
  }
  return html
}
