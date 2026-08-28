// 嵌入挂载前缀推导。
// 嵌入路由本身是 /embed/conversation/:token；当本 SPA 被宿主站点（如 OncoPath）
// 以同站反代方式挂载时，浏览器地址会带宿主前缀（如 /agentteams/embed/...）。
// 前缀由宿主部署决定，不写死：按路径中 embed 段出现的位置动态推导，
// 换任何宿主前缀都能工作。
export function resolveEmbedPrefix(pathname) {
  if (typeof pathname !== 'string' || !pathname) return null
  const segments = pathname.split('/')
  const index = segments.indexOf('embed')
  // index 为 -1 表示不在嵌入路径上；由于路径以 / 开头，embed 不可能是首段
  if (index < 1) return null
  const prefixSegments = segments.slice(1, index)
  return prefixSegments.length ? `/${prefixSegments.join('/')}` : ''
}

// 路由 history base：嵌入挂载时为 '<前缀>/'，独立部署为 '/'。
export function resolveHistoryBase() {
  if (typeof window === 'undefined') return '/'
  const prefix = resolveEmbedPrefix(window.location.pathname)
  return prefix ? `${prefix}/` : '/'
}

// 嵌入页 API 前缀：与路由 base 保持一致，使宿主只需一条 /<前缀>/ 的
// 反代规则即可同时服务页面与 API，无需为根路径 API 逐条镜像。
export function embedApiPrefix() {
  if (typeof window === 'undefined') return ''
  return resolveEmbedPrefix(window.location.pathname) || ''
}
