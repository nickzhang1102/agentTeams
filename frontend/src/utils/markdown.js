/**
 * Markdown 渲染工具函数
 *
 * 提供行内 Markdown 渲染，用于摘要文本等短内容场景。
 * 与 MarkdownRenderer.vue 的全量块渲染互补，不替代。
 */
import DOMPurify from 'dompurify'

function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function sanitizeHtml(html) {
  return typeof DOMPurify?.sanitize === 'function'
    ? DOMPurify.sanitize(html)
    : html
}

function parseInlineMarkdown(escapedText) {
  // 摘要短文本不能复用 marked 的全局实例；MarkdownRenderer 会改写全局 renderer。
  // 这里只实现摘要里需要的行内语法，输入已转义，输出仍会经过 DOMPurify。
  return escapedText
    .replace(/\[([^\]\n]+?)\]\((https?:\/\/[^)\s]+)\)/gi, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/`([^`\n]+?)`/g, '<code>$1</code>')
    .replace(/\*\*([^*\n]+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*\n]+?)\*/g, '<em>$1</em>')
    .replace(/\n/g, '<br>')
}

/**
 * 行内 Markdown 渲染（加粗/斜体/代码/链接）
 *
 * 安全策略：
 * - 原始 HTML 先转义再交给 marked，避免标签透传到 v-html
 * - 额外过滤 javascript: URI，阻断链接型 XSS
 *
 * @param {string} text - 待渲染的行内 Markdown 文本
 * @returns {string} 渲染后的 HTML 字符串
 */
export function renderInlineMd(text) {
  if (!text || typeof text !== 'string') return text || ''
  const html = parseInlineMarkdown(escapeHtml(text))
  // 阻断 javascript: / vbscript: / data:text/html 等危险 URI
  const safeUriHtml = html.replace(/\b(javascript|vbscript|data:text\/html)\s*:/gi, '')
  return sanitizeHtml(safeUriHtml)
}
