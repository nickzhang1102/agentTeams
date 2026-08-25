<template>
  <div class="tool-call-viz">
    <div v-for="(call, idx) in calls" :key="idx" class="tool-call-item">
      <!-- web_search: 超链接列表 -->
      <template v-if="call.tool === 'web_search'">
        <div class="search-results" v-if="parseSearchResults(call.result_summary).length > 0">
          <div class="search-header">
            <el-icon><Search /></el-icon>
            <span>{{ t('leader.tools.searchResults') }}</span>
            <span class="search-meta">{{ call.timestamp }}</span>
          </div>
          <div class="search-links">
            <a
              v-for="(link, i) in parseSearchResults(call.result_summary)"
              :key="i"
              :href="link.url"
              target="_blank"
              rel="noopener noreferrer"
              class="search-link"
            >
              <span class="link-index">{{ i + 1 }}</span>
              <div class="link-body">
                <span class="link-title">{{ link.title }}</span>
              </div>
            </a>
          </div>
        </div>
        <!-- 搜索中或结果为空时显示搜索词 -->
        <div class="search-pending" v-else>
          <el-icon><Search /></el-icon>
          <span>{{ t('leader.tools.searching', { query: getSearchQuery(call.params) }) }}</span>
          <span class="search-meta">{{ call.timestamp }}</span>
        </div>
      </template>

      <!-- file_read / file_write / file_edit: 文件操作 -->
      <template v-else-if="isFileTool(call.tool)">
        <div class="file-operation">
          <el-icon><Document /></el-icon>
          <span class="file-label">{{ getFileLabel(call.tool) }}</span>
          <code class="file-path">{{ extractFilePath(call.params, call.result_summary) }}</code>
          <span class="file-meta">{{ call.timestamp }}</span>
        </div>
      </template>

      <!-- 其他工具: 简洁展示 -->
      <template v-else>
        <div class="generic-tool">
          <el-tag size="small" :type="getToolType(call.tool)">{{ call.tool }}</el-tag>
          <span class="tool-result-text">{{ truncate(call.result_summary, 150) }}</span>
          <span class="tool-meta">{{ call.timestamp }}</span>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { Search, Document } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps({
  calls: {
    type: Array,
    default: () => [],
    validator: (value) => {
      return value.every(call =>
        call && typeof call === 'object' && 'tool' in call
      )
    }
  }
})

/**
 * 解析搜索结果文本，提取 {title, url, snippet} 列表
 *
 * 支持格式：
 *   1. Title\n   URL: https://...\n   Snippet
 *   2. [Title](URL)  (Markdown 格式)
 *   3. 纯 URL 行
 */
function parseSearchResults(text) {
  if (!text) return []

  const results = []

  // 尝试 Markdown 链接格式: [title](url)
  const mdLinkRegex = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g
  let mdMatch
  let hasMdLinks = false
  while ((mdMatch = mdLinkRegex.exec(text)) !== null) {
    hasMdLinks = true
    results.push({ title: mdMatch[1], url: mdMatch[2], snippet: '' })
  }
  if (hasMdLinks && results.length > 0) return results

  // 逐行解析: "1. Title\n   URL: https://...\n   Snippet"
  const lines = text.split('\n')
  let current = null

  for (const line of lines) {
    const trimmed = line.trim()

    // 编号标题行: "1. Title" 或 "1) Title"
    const titleMatch = trimmed.match(/^\d+[\.\)]\s+(.+)$/)
    if (titleMatch) {
      if (current) results.push(current)
      current = { title: titleMatch[1], url: '', snippet: '' }
      continue
    }

    // URL 行: "URL: https://..." 或纯 "https://..."
    const urlMatch = trimmed.match(/^(?:URL:\s*)?(https?:\/\/\S+)$/i)
    if (urlMatch) {
      if (current) current.url = urlMatch[1]
      continue
    }

    // 摘要行（非空、非标题行、非 URL 行）
    if (trimmed && current && !trimmed.startsWith('Search results')) {
      if (!current.snippet) {
        current.snippet = trimmed
      }
    }
  }
  if (current) results.push(current)

  return results
}

function isFileTool(toolName) {
  return ['file_read', 'file_write', 'file_edit'].includes(toolName)
}

/** 从搜索参数中提取查询词 */
function getSearchQuery(params) {
  if (!params) return ''
  const p = typeof params === 'string' ? {} : params
  return p.query || p.q || p.search || ''
}

function getFileLabel(toolName) {
  const labels = {
    file_read: 'leader.tools.fileRead',
    file_write: 'leader.tools.fileWrite',
    file_edit: 'leader.tools.fileEdit',
  }
  return labels[toolName] ? t(labels[toolName]) : toolName
}

/** 从参数或结果中提取文件路径 */
function extractFilePath(params, result) {
  if (params) {
    // 优先从参数中取 path/file_path/filepath
    const p = typeof params === 'string' ? {} : params
    if (p.path) return p.path
    if (p.file_path) return p.file_path
    if (p.filepath) return p.filepath
    if (p.filename) return p.filename
  }
  // 从结果中提取路径
  if (result) {
    const pathMatch = result.match(/(?:file|path)[:\s]+([^\s,]+)/i)
    if (pathMatch) return pathMatch[1]
  }
  return ''
}

function truncate(text, max) {
  if (!text) return ''
  return text.length > max ? text.slice(0, max) + '...' : text
}

const getToolType = (toolName) => {
  const typeMap = {
    'web_search': 'primary',
    'file_read': 'success',
    'file_write': 'warning',
    'file_edit': 'warning',
    'bash': 'danger'
  }
  return typeMap[toolName] || 'info'
}
</script>

<style scoped>
.tool-call-viz {
  margin: 4px 0;
}

.tool-call-item {
  margin-bottom: 8px;
}

.tool-call-item:last-child {
  margin-bottom: 0;
}

/* ---- 搜索结果 ---- */
.search-results {
  background: #f0f9ff;
  border: 1px solid #bfdbfe;
  border-radius: 6px;
  padding: 8px 10px;
}

.search-pending {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  font-size: 12px;
  color: #6b7280;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
}

.search-header {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  color: #1d4ed8;
  margin-bottom: 6px;
}

.search-meta {
  margin-left: auto;
  color: #94a3b8;
  font-weight: normal;
  font-size: 11px;
}

.search-links {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.search-link {
  display: flex;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 4px;
  text-decoration: none;
  color: inherit;
  transition: background 0.2s;
}

.search-link:hover {
  background: #dbeafe;
}

.link-index {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  line-height: 20px;
  text-align: center;
  border-radius: 50%;
  background: #3b82f6;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  margin-top: 2px;
}

.link-body {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.link-title {
  font-size: 13px;
  font-weight: 500;
  color: #1e40af;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.search-link:hover .link-title {
  text-decoration: underline;
}

/* ---- 文件操作 ---- */
.file-operation {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 4px;
  font-size: 12px;
}

.file-operation .el-icon {
  color: #16a34a;
}

.file-label {
  color: #16a34a;
  font-weight: 500;
}

.file-path {
  background: #dcfce7;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 12px;
  color: #15803d;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-meta {
  margin-left: auto;
  color: #94a3b8;
  font-size: 11px;
}

/* ---- 其他工具 ---- */
.generic-tool {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  font-size: 12px;
  color: #6b7280;
}

.tool-result-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-meta {
  flex-shrink: 0;
  color: #94a3b8;
  font-size: 11px;
}
</style>
