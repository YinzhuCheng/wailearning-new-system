import { http } from '@/api'

export const MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024

const BLOCKED_ATTACHMENT_EXTENSIONS = ['.apk', '.app', '.bat', '.cmd', '.com', '.exe', '.msi', '.ps1', '.scr']

/** Mirrors server allow-list (attachment_compliance.py); final checks run on upload. */
const ALLOWED_GENERIC_EXTENSIONS = new Set([
  '.pdf',
  '.txt',
  '.docx',
  '.doc',
  '.xlsx',
  '.xls',
  '.ipynb',
  '.png',
  '.jpg',
  '.jpeg',
  '.gif',
  '.webp',
  '.bmp',
  '.zip',
  '.rar',
  '.c',
  '.cc',
  '.cpp',
  '.csv',
  '.go',
  '.h',
  '.hpp',
  '.html',
  '.java',
  '.js',
  '.json',
  '.jsx',
  '.md',
  '.py',
  '.rb',
  '.rs',
  '.sql',
  '.tex',
  '.ts',
  '.tsx',
  '.vue',
  '.xml',
  '.yaml',
  '.yml'
])

const MARKDOWN_IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp'])

export const attachmentHintText =
  '支持 Office 文档、PDF、TXT、图片、Jupyter 笔记本（.ipynb）等常见格式，禁止 .exe。可用压缩包包含多个文件，最大 20 MB。上传后会进行格式合规性检测。'

/**
 * @param {File | null | undefined} file
 * @param {{ imageOnly?: boolean }} [opts]
 * @returns {{ valid: boolean, message?: string }}
 */
export const validateAttachmentFile = (file, opts = {}) => {
  if (!file) {
    return { valid: false, message: '请选择一个附件文件。' }
  }

  const fileName = file.name || ''
  const extension = fileName.includes('.') ? fileName.slice(fileName.lastIndexOf('.')).toLowerCase() : ''

  if (BLOCKED_ATTACHMENT_EXTENSIONS.includes(extension)) {
    return { valid: false, message: '不支持上传可执行文件。' }
  }

  if (file.size > MAX_ATTACHMENT_SIZE) {
    return { valid: false, message: '附件大小不能超过 20 MB。' }
  }

  if (opts.imageOnly) {
    if (!MARKDOWN_IMAGE_EXTENSIONS.has(extension)) {
      return { valid: false, message: '请上传 JPG、PNG、GIF 或 WebP 图片。' }
    }
    return { valid: true }
  }

  if (!ALLOWED_GENERIC_EXTENSIONS.has(extension)) {
    return {
      valid: false,
      message:
        '附件格式不在允许列表内。支持 Office（.doc/.docx/.xls/.xlsx）、PDF、TXT、常见图片、Jupyter（.ipynb）、以及 .zip/.rar；压缩包内需至少包含一个上述类型的文件。'
    }
  }

  return { valid: true }
}

const resolveAttachmentName = (attachmentUrl, attachmentName) => {
  const normalizedName = (attachmentName || '').trim().split(/[\\/]/).pop()
  if (normalizedName) {
    return normalizedName
  }

  try {
    const url = new URL(attachmentUrl, window.location.origin)
    const pathname = url.pathname || ''
    const storedName = pathname.split('/').filter(Boolean).pop()
    return storedName ? decodeURIComponent(storedName) : 'attachment'
  } catch {
    return 'attachment'
  }
}

export const downloadAttachment = async (attachmentUrl, attachmentName) => {
  if (!attachmentUrl) {
    return
  }

  const blob = await http.get('/files/download', {
    params: {
      attachment_url: attachmentUrl,
      ...(attachmentName ? { attachment_name: attachmentName } : {})
    },
    responseType: 'blob',
    timeout: 0
  })

  const objectUrl = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = resolveAttachmentName(attachmentUrl, attachmentName)
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 1000)
}

/** Authorization header applied via http interceptor; returns a blob: URL to revoke when done. */
export const fetchAttachmentBlobUrl = async attachmentUrl => {
  if (!attachmentUrl) {
    return ''
  }
  const blob = await http.get('/files/download', {
    params: { attachment_url: attachmentUrl },
    responseType: 'blob',
    timeout: 0
  })
  return URL.createObjectURL(blob)
}
