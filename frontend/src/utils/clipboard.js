/**
 * 剪贴板复制工具
 *
 * 统一管理复制逻辑：
 * - 优先使用现代 Clipboard API（仅安全上下文 HTTPS/localhost 可用）
 * - 降级使用 textarea + document.execCommand('copy')
 * - 返回 boolean 表示是否成功，由调用方决定提示文案
 *
 * 供管理后台各复制按钮复用（避免各自实现重复降级逻辑）。
 */

/**
 * 复制文本到剪贴板
 * @param {string} text - 要复制的文本
 * @returns {Promise<boolean>} 是否复制成功
 */
export async function copyToClipboard(text) {
  // 现代 API 只在安全上下文存在
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch (err) {
      // 权限被拒等，继续走降级方案
    }
  }

  // 降级方案：隐藏 textarea + execCommand
  const textArea = document.createElement('textarea')
  textArea.value = text
  // 防止页面滚动
  textArea.style.position = 'fixed'
  textArea.style.left = '-999999px'
  textArea.style.top = '-999999px'
  document.body.appendChild(textArea)
  textArea.focus()
  textArea.select()

  try {
    const successful = document.execCommand('copy')
    return Boolean(successful)
  } finally {
    document.body.removeChild(textArea)
  }
}
