/**
 * Markdown 渲染工具函数
 *
 * 提供行内 Markdown 渲染，用于摘要文本等短内容场景。
 * 与 MarkdownRenderer.vue 的全量块渲染互补，不替代。
 */
import DOMPurify from 'dompurify'

function escapeHtml(text) {
  return String(text)
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

// 显式证据引用标记：[evidence_id:xxx]
const EVIDENCE_REF_PATTERN = /\[evidence_id:([^\]\s]+)\]/g

function buildEvidenceLookup(evidenceMap) {
  const evidence = Array.isArray(evidenceMap)
    ? evidenceMap
    : Object.values(evidenceMap || {})
  const lookup = new Map()
  evidence.forEach((item, index) => {
    const id = item && typeof item === 'object' ? String(item.evidence_id || '').trim() : ''
    if (id && !lookup.has(id)) {
      lookup.set(id, { number: index + 1, title: item.title || '' })
    }
  })
  return lookup
}

// 把摘要中的证据标记收敛为短标签（证据N），避免泄漏原始长 evidence_id。
// 命中证据表时输出带 data-evidence-id 的可点击引用（由容器做事件委托）；
// 未命中或没有证据表时输出不可点击的短标签。
function applyEvidenceRefs(html, evidenceMap, evidenceLabel) {
  const lookup = evidenceMap ? buildEvidenceLookup(evidenceMap) : null
  return html.replace(EVIDENCE_REF_PATTERN, (match, evidenceId) => {
    const hit = lookup?.get(evidenceId)
    if (hit) {
      const label = `${evidenceLabel}${hit.number}`
      const title = hit.title || label
      return `<button type="button" class="evidence-ref" data-evidence-id="${escapeHtml(evidenceId)}" title="${escapeHtml(title)}">${escapeHtml(label)}</button>`
    }
    // 未命中：直接移除标记，不回显原始长 ID，也不渲染任何占位标签
    return ''
  })
}

/**
 * 行内 Markdown 渲染（加粗/斜体/代码/链接/证据引用）
 *
 * 安全策略：
 * - 原始 HTML 先转义再交给 marked，避免标签透传到 v-html
 * - 额外过滤 javascript: URI，阻断链接型 XSS
 *
 * @param {string} text - 待渲染的行内 Markdown 文本
 * @param {object} [options] - 证据引用配置
 * @param {Array|object} [options.evidenceMap] - 证据表（evidence_id/title），
 *   命中时把 [evidence_id:xxx] 渲染为可点击短标签
 * @param {string} [options.evidenceLabel] - 短标签前缀，默认 'evidence'
 * @returns {string} 渲染后的 HTML 字符串
 */
export function renderInlineMd(text, options = {}) {
  if (!text || typeof text !== 'string') return text || ''
  const { evidenceMap = null, evidenceLabel = 'evidence' } = options
  let html = parseInlineMarkdown(escapeHtml(text))
  html = applyEvidenceRefs(html, evidenceMap, evidenceLabel)
  // 阻断 javascript: / vbscript: / data:text/html 等危险 URI
  const safeUriHtml = html.replace(/\b(javascript|vbscript|data:text\/html)\s*:/gi, '')
  return sanitizeHtml(safeUriHtml)
}
