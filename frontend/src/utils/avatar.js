/**
 * 本地 SVG 头像工具（零外部依赖）
 * 根据 agent_id 通过哈希算法生成确定性、唯一的 SVG 头像
 */

const STYLE_MAP = {
  medical: 'botttsNeutral',
  business: 'initials',
  finance: 'shapes',
  custom: 'lorelei',
  default: 'identicon',
}

const COLOR_MAP = {
  medical: '#e74c3c',
  business: '#3498db',
  finance: '#2ecc71',
  custom: '#9b59b6',
  default: '#95a5a6',
}

/**
 * 简单字符串哈希（djb2 算法变体）
 */
function hashCode(str) {
  let hash = 5381
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash + str.charCodeAt(i)) & 0xffffffff
  }
  return Math.abs(hash)
}

/**
 * HSL 转 hex
 */
function hslToHex(h, s, l) {
  s /= 100
  l /= 100
  const a = s * Math.min(l, 1 - l)
  const f = (n) => {
    const k = (n + h / 30) % 12
    const color = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1)
    return Math.round(255 * color).toString(16).padStart(2, '0')
  }
  return `#${f(0)}${f(8)}${f(4)}`
}

/**
 * 根据 agent_id 和 category 生成确定性 SVG data URL
 * @param {string} agentId - Agent ID
 * @param {string} category - 分类
 * @returns {string} data:image/svg+xml;base64,...
 */
export function getAvatarUrl(agentId, category = 'default') {
  const hash = hashCode(agentId || 'default')
  const hue = hash % 360
  const saturation = 50 + (hash % 30) // 50-80
  const lightness = 45 + (hash % 20) // 45-65

  const bg = hslToHex(hue, saturation, lightness)
  const fg = '#ffffff'

  // 用 hash 生成一个 5x5 对称像素图（identicon 风格）
  const pixels = []
  for (let row = 0; row < 5; row++) {
    for (let col = 0; col < 3; col++) {
      const bit = (hash >> (row * 3 + col)) & 1
      if (bit) {
        pixels.push(`<rect x="${col * 20}" y="${row * 20}" width="20" height="20" fill="${fg}" rx="3"/>`)
        // 对称镜像
        if (col < 2) {
          pixels.push(`<rect x="${(4 - col) * 20}" y="${row * 20}" width="20" height="20" fill="${fg}" rx="3"/>`)
        }
      }
    }
  }

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
    <rect width="100" height="100" fill="${bg}" rx="50"/>
    <g transform="translate(0,0)">${pixels.join('')}</g>
  </svg>`

  return `data:image/svg+xml;base64,${btoa(svg)}`
}

/**
 * 获取分类对应的兜底颜色
 * @param {string} category
 * @returns {string} hex color
 */
export function getCategoryColor(category) {
  return COLOR_MAP[category] || COLOR_MAP.default
}

/**
 * 获取 Agent 名称首字（用于无头像兜底）
 * @param {string} name
 * @returns {string}
 */
export function getInitial(name) {
  if (!name) return '?'
  // 中文取第一个字，英文取首字母大写
  const first = name.charAt(0)
  if (/[一-鿿]/.test(first)) return first
  return first.toUpperCase()
}
